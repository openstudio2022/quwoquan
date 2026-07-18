import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class PostPublicationQueuedException implements Exception {
  const PostPublicationQueuedException(this.publishIntentId);

  final String publishIntentId;
}

final class LocalPostPublicationIntent {
  const LocalPostPublicationIntent({
    required this.command,
    required this.authorPersonaId,
    required this.circleIds,
    required this.createdAt,
    required this.nextAttemptAt,
    this.retryCount = 0,
    this.postId,
    this.committedVersion,
    this.acceptedAt,
    this.lastErrorCode,
    this.blocked = false,
  });

  final SubmitContentPostPublicationCommand command;
  final String authorPersonaId;
  final List<String> circleIds;
  final DateTime createdAt;
  final DateTime nextAttemptAt;
  final int retryCount;
  final String? postId;
  final int? committedVersion;
  final DateTime? acceptedAt;
  final String? lastErrorCode;
  final bool blocked;

  bool get publicationAccepted =>
      postId?.trim().isNotEmpty == true && acceptedAt != null;

  LocalPostPublicationIntent copyWith({
    List<String>? circleIds,
    DateTime? nextAttemptAt,
    int? retryCount,
    String? postId,
    int? committedVersion,
    DateTime? acceptedAt,
    String? lastErrorCode,
    bool clearLastErrorCode = false,
    bool? blocked,
  }) {
    return LocalPostPublicationIntent(
      command: command,
      authorPersonaId: authorPersonaId,
      circleIds: circleIds ?? this.circleIds,
      createdAt: createdAt,
      nextAttemptAt: nextAttemptAt ?? this.nextAttemptAt,
      retryCount: retryCount ?? this.retryCount,
      postId: postId ?? this.postId,
      committedVersion: committedVersion ?? this.committedVersion,
      acceptedAt: acceptedAt ?? this.acceptedAt,
      lastErrorCode: clearLastErrorCode
          ? null
          : (lastErrorCode ?? this.lastErrorCode),
      blocked: blocked ?? this.blocked,
    );
  }

  factory LocalPostPublicationIntent.fromStorageMap(Map<String, Object?> map) {
    final command = decodeSubmitContentPostPublicationCommand(
      map['commandBody'],
    );
    return LocalPostPublicationIntent(
      command: command,
      authorPersonaId: (map['authorPersonaId'] ?? '').toString().trim(),
      circleIds: (map['circleIds'] as List? ?? const <Object?>[])
          .map((value) => value.toString().trim())
          .where((value) => value.isNotEmpty)
          .toList(growable: false),
      createdAt:
          DateTime.tryParse(map['createdAt']?.toString() ?? '')?.toUtc() ??
          DateTime.now().toUtc(),
      nextAttemptAt:
          DateTime.tryParse(map['nextAttemptAt']?.toString() ?? '')?.toUtc() ??
          DateTime.now().toUtc(),
      retryCount: (map['retryCount'] as num?)?.toInt() ?? 0,
      postId: _optionalStorageText(map['postId']),
      committedVersion: (map['committedVersion'] as num?)?.toInt(),
      acceptedAt: DateTime.tryParse(
        map['acceptedAt']?.toString() ?? '',
      )?.toUtc(),
      lastErrorCode: _optionalStorageText(map['lastErrorCode']),
      blocked: map['blocked'] == true,
    );
  }

  Map<String, Object?> toStorageMap() {
    return <String, Object?>{
      'commandBody': encodeSubmitContentPostPublicationCommand(command).body,
      'authorPersonaId': authorPersonaId,
      'circleIds': circleIds,
      'createdAt': createdAt.toUtc().toIso8601String(),
      'nextAttemptAt': nextAttemptAt.toUtc().toIso8601String(),
      'retryCount': retryCount,
      'postId': postId,
      'committedVersion': committedVersion,
      'acceptedAt': acceptedAt?.toUtc().toIso8601String(),
      'lastErrorCode': lastErrorCode,
      'blocked': blocked,
    };
  }
}

final class PostPublicationIntentQueueState {
  const PostPublicationIntentQueueState({
    this.intents = const <LocalPostPublicationIntent>[],
    this.hydrated = false,
  });

  final List<LocalPostPublicationIntent> intents;
  final bool hydrated;
}

final class PostPublicationIntentQueueNotifier
    extends Notifier<PostPublicationIntentQueueState> {
  Timer? _retryTimer;
  bool _flushing = false;
  late Completer<void> _hydrated;
  late String _activeScopeKey;

  @override
  PostPublicationIntentQueueState build() {
    _activeScopeKey = _publicationQueueScopeKey(
      ref.watch(currentUserIdProvider),
    );
    _retryTimer?.cancel();
    _hydrated = Completer<void>();
    unawaited(_hydrate(_activeScopeKey, _hydrated));
    ref.onDispose(() => _retryTimer?.cancel());
    return const PostPublicationIntentQueueState();
  }

  Future<ContentPostPublicationReceipt> submit({
    required SubmitContentPostPublicationCommand command,
    required String authorPersonaId,
    Iterable<String> circleIds = const <String>[],
  }) async {
    await _hydrated.future;
    final normalizedPersonaId = authorPersonaId.trim();
    if (normalizedPersonaId.isEmpty) {
      throw ArgumentError.value(
        authorPersonaId,
        'authorPersonaId',
        'must not be empty',
      );
    }
    var intent = _intentForDraft(command.localDraftId);
    if (intent == null) {
      intent = LocalPostPublicationIntent(
        command: command,
        authorPersonaId: normalizedPersonaId,
        circleIds: circleIds
            .map((value) => value.trim())
            .where((value) => value.isNotEmpty)
            .toSet()
            .toList(growable: false),
        createdAt: DateTime.now().toUtc(),
        nextAttemptAt: DateTime.now().toUtc(),
      );
      _replace(intent);
      await _persist();
    }
    if (intent.publicationAccepted) {
      return _receiptFromIntent(intent);
    }
    try {
      return await _submitPublication(intent);
    } on CloudException catch (error) {
      final retryable = _isRetryable(error);
      await _markFailed(
        intent,
        error.code ?? error.runtimeFailure.code,
        retryable,
      );
      if (retryable) {
        throw PostPublicationQueuedException(intent.command.publishIntentId);
      }
      rethrow;
    } catch (error, stackTrace) {
      developer.log(
        'Post publication queued after transient failure',
        name: 'PostPublicationIntentQueue',
        error: error,
        stackTrace: stackTrace,
      );
      await _markFailed(intent, error.runtimeType.toString(), true);
      throw PostPublicationQueuedException(intent.command.publishIntentId);
    }
  }

  Future<void> flushNow() async {
    await _hydrated.future;
    if (_flushing) {
      return;
    }
    _flushing = true;
    try {
      final due = state.intents
          .where(
            (intent) =>
                !intent.blocked &&
                !intent.nextAttemptAt.isAfter(DateTime.now().toUtc()),
          )
          .toList(growable: false);
      for (final intent in due) {
        try {
          if (intent.publicationAccepted) {
            await _finishAcceptedIntent(intent);
          } else {
            await _submitPublication(intent);
          }
        } on CloudException catch (error) {
          await _markFailed(
            intent,
            error.code ?? error.runtimeFailure.code,
            _isRetryable(error),
          );
        } catch (error, stackTrace) {
          developer.log(
            'Post publication background retry failed',
            name: 'PostPublicationIntentQueue',
            error: error,
            stackTrace: stackTrace,
          );
          await _markFailed(intent, error.runtimeType.toString(), true);
        }
      }
    } finally {
      _flushing = false;
      _scheduleRetry();
    }
  }

  Future<void> _hydrate(String scopeKey, Completer<void> hydration) async {
    try {
      final preferences = await SharedPreferences.getInstance();
      final raw = preferences.getString(scopeKey);
      final decoded = raw == null || raw.isEmpty ? null : jsonDecode(raw);
      final intents = decoded is List
          ? decoded
                .whereType<Map>()
                .map(
                  (value) => LocalPostPublicationIntent.fromStorageMap(
                    value.map((key, item) => MapEntry(key.toString(), item)),
                  ),
                )
                .toList(growable: false)
          : const <LocalPostPublicationIntent>[];
      if (ref.mounted && scopeKey == _activeScopeKey) {
        state = PostPublicationIntentQueueState(
          intents: intents,
          hydrated: true,
        );
      }
    } catch (error, stackTrace) {
      developer.log(
        'Post publication queue hydration failed',
        name: 'PostPublicationIntentQueue',
        error: error,
        stackTrace: stackTrace,
      );
      if (ref.mounted && scopeKey == _activeScopeKey) {
        state = const PostPublicationIntentQueueState(hydrated: true);
      }
    } finally {
      if (!hydration.isCompleted) {
        hydration.complete();
      }
      if (scopeKey == _activeScopeKey) {
        _scheduleRetry(immediate: true);
      }
    }
  }

  Future<ContentPostPublicationReceipt> _submitPublication(
    LocalPostPublicationIntent intent,
  ) async {
    final activePersona = await ref.read(activePersonaContextProvider.future);
    if (activePersona.subAccountId.trim() != intent.authorPersonaId) {
      throw StateError('publication waits for its original persona context');
    }
    final receipt = await ref
        .read(createContentPostPublicationWriterProvider)
        .submitPostPublication(intent.command);
    final accepted = intent.copyWith(
      postId: receipt.postId,
      committedVersion: receipt.committedVersion,
      acceptedAt: receipt.acceptedAt,
      retryCount: 0,
      nextAttemptAt: DateTime.now().toUtc(),
      clearLastErrorCode: true,
      blocked: false,
    );
    _replace(accepted);
    await _persist();
    await _finishAcceptedIntent(accepted);
    return receipt;
  }

  Future<void> _finishAcceptedIntent(LocalPostPublicationIntent intent) async {
    try {
      await ref
          .read(createDraftStoreProvider.notifier)
          .deleteDraft(intent.command.localDraftId);
    } catch (error, stackTrace) {
      developer.log(
        'Published Post draft cleanup queued for retry',
        name: 'PostPublicationIntentQueue',
        error: error,
        stackTrace: stackTrace,
      );
      _replace(
        intent.copyWith(
          nextAttemptAt: DateTime.now().toUtc().add(const Duration(minutes: 1)),
        ),
      );
      await _persist();
      return;
    }
    final remainingCircles = <String>[];
    for (final circleId in intent.circleIds) {
      try {
        await ref
            .read(createWorkspaceCirclePostPlacementWriterProvider)
            .placePost(
              PlaceCirclePostCommand(
                circleId: circleId,
                postId: intent.postId!,
              ),
            );
      } catch (error, stackTrace) {
        developer.log(
          'Published Post circle placement queued for retry',
          name: 'PostPublicationIntentQueue',
          error: error,
          stackTrace: stackTrace,
        );
        remainingCircles.add(circleId);
      }
    }
    if (remainingCircles.isEmpty) {
      _remove(intent.command.localDraftId);
    } else {
      _replace(
        intent.copyWith(
          circleIds: remainingCircles,
          nextAttemptAt: DateTime.now().toUtc().add(const Duration(minutes: 1)),
        ),
      );
    }
    await _persist();
  }

  Future<void> _markFailed(
    LocalPostPublicationIntent intent,
    String errorCode,
    bool retryable,
  ) async {
    final retryCount = intent.retryCount + 1;
    final exponent = retryCount.clamp(0, 6).toInt();
    final delaySeconds = 1 << exponent;
    _replace(
      intent.copyWith(
        retryCount: retryCount,
        nextAttemptAt: DateTime.now().toUtc().add(
          Duration(seconds: delaySeconds.clamp(2, 60).toInt()),
        ),
        lastErrorCode: errorCode,
        blocked: !retryable,
      ),
    );
    await _persist();
    _scheduleRetry();
  }

  Future<void> _persist() async {
    final preferences = await SharedPreferences.getInstance();
    final persisted = await preferences.setString(
      _activeScopeKey,
      jsonEncode(
        state.intents
            .map((intent) => intent.toStorageMap())
            .toList(growable: false),
      ),
    );
    if (!persisted) {
      throw StateError('post publication intent persistence failed');
    }
  }

  LocalPostPublicationIntent? _intentForDraft(String localDraftId) {
    final normalized = localDraftId.trim();
    for (final intent in state.intents) {
      if (intent.command.localDraftId == normalized) {
        return intent;
      }
    }
    return null;
  }

  void _replace(LocalPostPublicationIntent intent) {
    state = PostPublicationIntentQueueState(
      intents: <LocalPostPublicationIntent>[
        ...state.intents.where(
          (item) => item.command.localDraftId != intent.command.localDraftId,
        ),
        intent,
      ],
      hydrated: true,
    );
  }

  void _remove(String localDraftId) {
    state = PostPublicationIntentQueueState(
      intents: state.intents
          .where((intent) => intent.command.localDraftId != localDraftId)
          .toList(growable: false),
      hydrated: true,
    );
  }

  void _scheduleRetry({bool immediate = false}) {
    _retryTimer?.cancel();
    final pending = state.intents.where((intent) => !intent.blocked).toList();
    if (pending.isEmpty) {
      return;
    }
    final nextAttemptAt = pending
        .map((intent) => intent.nextAttemptAt)
        .reduce((left, right) => left.isBefore(right) ? left : right);
    final delay = immediate
        ? Duration.zero
        : nextAttemptAt.difference(DateTime.now().toUtc());
    _retryTimer = Timer(delay.isNegative ? Duration.zero : delay, () {
      unawaited(flushNow());
    });
  }

  ContentPostPublicationReceipt _receiptFromIntent(
    LocalPostPublicationIntent intent,
  ) {
    return ContentPostPublicationReceipt(
      publishIntentId: intent.command.publishIntentId,
      localDraftId: intent.command.localDraftId,
      postId: intent.postId!,
      state: 'published',
      committedVersion: intent.committedVersion!,
      acceptedAt: intent.acceptedAt!,
    );
  }

  bool _isRetryable(CloudException error) {
    return switch (error.type) {
      CloudErrorType.timeout ||
      CloudErrorType.cancelled ||
      CloudErrorType.network ||
      CloudErrorType.rateLimited ||
      CloudErrorType.server ||
      CloudErrorType.invalidResponse ||
      CloudErrorType.unauthorized ||
      CloudErrorType.unknown => true,
      CloudErrorType.forbidden || CloudErrorType.notFound => false,
    };
  }
}

final postPublicationIntentQueueProvider =
    NotifierProvider<
      PostPublicationIntentQueueNotifier,
      PostPublicationIntentQueueState
    >(PostPublicationIntentQueueNotifier.new);

String _publicationQueueScopeKey(String? currentUserId) {
  final normalized = currentUserId?.trim() ?? '';
  return 'post_publication_intents_v1:${normalized.isEmpty ? 'guest' : normalized}';
}

String? _optionalStorageText(Object? value) {
  final normalized = value?.toString().trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
