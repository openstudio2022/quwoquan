import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/application/content/post/post_publication_status_reader.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class PostPublicationQueuedException implements Exception {
  const PostPublicationQueuedException(this.publishIntentId);

  final String publishIntentId;
}

final class PostPublicationTaskBlockedException implements Exception {
  const PostPublicationTaskBlockedException(this.localDraftId);

  final String localDraftId;
}

final class _PostPublicationPersonaMismatchException implements Exception {
  const _PostPublicationPersonaMismatchException();
}

final class _PostPublicationPermanentException implements Exception {
  const _PostPublicationPermanentException();
}

enum LocalPostPublicationBlockReason {
  personaChanged,
  invalidReceipt,
  rejected,
  remoteFailure,
}

enum LocalPostPublicationStage { preparingMedia, submitting }

final class LocalPostPublicationIntent {
  const LocalPostPublicationIntent({
    required this.command,
    required this.authorPersonaId,
    required this.circleIds,
    required this.createdAt,
    required this.nextAttemptAt,
    this.stage = LocalPostPublicationStage.submitting,
    this.retryCount = 0,
    this.postId,
    this.committedVersion,
    this.acceptedAt,
    this.publicationState,
    this.lastErrorCode,
    this.blockReason,
    this.blocked = false,
  });

  final SubmitContentPostPublicationCommand command;
  final String authorPersonaId;
  final List<String> circleIds;
  final DateTime createdAt;
  final DateTime nextAttemptAt;
  final LocalPostPublicationStage stage;
  final int retryCount;
  final String? postId;
  final int? committedVersion;
  final DateTime? acceptedAt;
  final ContentPostPublicationState? publicationState;
  final String? lastErrorCode;
  final LocalPostPublicationBlockReason? blockReason;
  final bool blocked;

  bool get publicationAccepted =>
      postId?.trim().isNotEmpty == true &&
      committedVersion != null &&
      acceptedAt != null &&
      (publicationState == ContentPostPublicationState.pendingReview ||
          publicationState == ContentPostPublicationState.published);
  bool get requiresMediaPreparation =>
      stage == LocalPostPublicationStage.preparingMedia;

  LocalPostPublicationIntent copyWith({
    SubmitContentPostPublicationCommand? command,
    List<String>? circleIds,
    DateTime? nextAttemptAt,
    LocalPostPublicationStage? stage,
    int? retryCount,
    String? postId,
    int? committedVersion,
    DateTime? acceptedAt,
    ContentPostPublicationState? publicationState,
    String? lastErrorCode,
    bool clearLastErrorCode = false,
    LocalPostPublicationBlockReason? blockReason,
    bool clearBlockReason = false,
    bool? blocked,
  }) {
    return LocalPostPublicationIntent(
      command: command ?? this.command,
      authorPersonaId: authorPersonaId,
      circleIds: circleIds ?? this.circleIds,
      createdAt: createdAt,
      nextAttemptAt: nextAttemptAt ?? this.nextAttemptAt,
      stage: stage ?? this.stage,
      retryCount: retryCount ?? this.retryCount,
      postId: postId ?? this.postId,
      committedVersion: committedVersion ?? this.committedVersion,
      acceptedAt: acceptedAt ?? this.acceptedAt,
      publicationState: publicationState ?? this.publicationState,
      lastErrorCode: clearLastErrorCode
          ? null
          : (lastErrorCode ?? this.lastErrorCode),
      blockReason: clearBlockReason ? null : (blockReason ?? this.blockReason),
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
      stage: _optionalPublicationStage(map['stage']),
      retryCount: (map['retryCount'] as num?)?.toInt() ?? 0,
      postId: _optionalStorageText(map['postId']),
      committedVersion: (map['committedVersion'] as num?)?.toInt(),
      acceptedAt: DateTime.tryParse(
        map['acceptedAt']?.toString() ?? '',
      )?.toUtc(),
      publicationState: _optionalPublicationState(map['publicationState']),
      lastErrorCode: _optionalStorageText(map['lastErrorCode']),
      blockReason: _optionalBlockReason(map['blockReason']),
      blocked:
          map['blocked'] == true ||
          _hasUnsupportedPublicationState(map['publicationState']),
    );
  }

  Map<String, Object?> toStorageMap() {
    return <String, Object?>{
      'commandBody': encodeSubmitContentPostPublicationCommand(command).body,
      'authorPersonaId': authorPersonaId,
      'circleIds': circleIds,
      'createdAt': createdAt.toUtc().toIso8601String(),
      'nextAttemptAt': nextAttemptAt.toUtc().toIso8601String(),
      'stage': stage.name,
      'retryCount': retryCount,
      'postId': postId,
      'committedVersion': committedVersion,
      'acceptedAt': acceptedAt?.toUtc().toIso8601String(),
      'publicationState': publicationState?.wireValue,
      'lastErrorCode': lastErrorCode,
      'blockReason': blockReason?.name,
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

  Future<void> beginMediaPreparation({
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
    final existing = _intentForDraft(command.localDraftId);
    if (existing != null) {
      if (existing.authorPersonaId != normalizedPersonaId) {
        throw PostPublicationTaskBlockedException(command.localDraftId);
      }
      if (!existing.requiresMediaPreparation) {
        throw PostPublicationQueuedException(command.publishIntentId);
      }
    }
    final now = DateTime.now().toUtc();
    final intent = LocalPostPublicationIntent(
      command: command,
      authorPersonaId: normalizedPersonaId,
      circleIds: _normalizedCircleIds(circleIds),
      createdAt: existing?.createdAt ?? now,
      nextAttemptAt: now,
      stage: LocalPostPublicationStage.preparingMedia,
    );
    _replace(intent);
    await _persist();
    _scheduleRetry();
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
        circleIds: _normalizedCircleIds(circleIds),
        createdAt: DateTime.now().toUtc(),
        nextAttemptAt: DateTime.now().toUtc(),
      );
      _replace(intent);
      await _persist();
    } else if (intent.requiresMediaPreparation) {
      if (intent.authorPersonaId != normalizedPersonaId) {
        throw PostPublicationTaskBlockedException(command.localDraftId);
      }
      intent = intent.copyWith(
        command: command,
        circleIds: _normalizedCircleIds(circleIds),
        stage: LocalPostPublicationStage.submitting,
        nextAttemptAt: DateTime.now().toUtc(),
        retryCount: 0,
        blocked: false,
        clearLastErrorCode: true,
        clearBlockReason: true,
      );
      _replace(intent);
      await _persist();
    }
    if (intent.publicationAccepted) {
      return _receiptFromIntent(intent);
    }
    if (intent.publicationState == ContentPostPublicationState.rejected) {
      throw PostPublicationTaskBlockedException(intent.command.localDraftId);
    }
    try {
      return await _submitPublication(intent);
    } on _PostPublicationPersonaMismatchException {
      await _markFailed(
        intent,
        null,
        false,
        blockReason: LocalPostPublicationBlockReason.personaChanged,
      );
      throw PostPublicationTaskBlockedException(intent.command.localDraftId);
    } on _PostPublicationPermanentException {
      await _markFailed(
        intent,
        null,
        false,
        blockReason: LocalPostPublicationBlockReason.invalidReceipt,
      );
      throw PostPublicationTaskBlockedException(intent.command.localDraftId);
    } on CloudException catch (error) {
      final retryable = _isRetryable(error);
      await _markFailed(
        intent,
        error.code ?? error.runtimeFailure.code,
        retryable,
        retryAfter: _retryAfter(error),
        blockReason: retryable
            ? null
            : LocalPostPublicationBlockReason.remoteFailure,
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

  /// 取消尚未被服务端接受的发布意图，或清除已拒绝的本地终态任务。
  /// pending_review/published 不能伪装成本地取消，必须走远端生命周期命令。
  Future<void> cancelPending(String localDraftId) async {
    await _hydrated.future;
    final intent = _intentForDraft(localDraftId);
    if (intent == null) {
      return;
    }
    if (intent.publicationAccepted) {
      throw StateError('accepted publication cannot be cancelled locally');
    }
    _remove(intent.command.localDraftId);
    await _persist();
    _scheduleRetry();
  }

  Future<void> retryPending(String localDraftId) async {
    await _hydrated.future;
    final intent = _intentForDraft(localDraftId);
    if (intent == null ||
        intent.requiresMediaPreparation ||
        intent.publicationState == ContentPostPublicationState.rejected ||
        intent.publicationState == ContentPostPublicationState.published) {
      return;
    }
    _replace(
      intent.copyWith(
        retryCount: 0,
        nextAttemptAt: DateTime.now().toUtc(),
        blocked: false,
        clearLastErrorCode: true,
        clearBlockReason: true,
      ),
    );
    await _persist();
    await flushNow();
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
                !intent.requiresMediaPreparation &&
                !intent.nextAttemptAt.isAfter(DateTime.now().toUtc()),
          )
          .toList(growable: false);
      for (final intent in due) {
        try {
          if (intent.publicationState ==
              ContentPostPublicationState.pendingReview) {
            await _refreshPendingIntent(intent);
          } else if (intent.publicationAccepted) {
            await _finishAcceptedIntent(intent);
          } else {
            await _submitPublication(intent);
          }
        } on _PostPublicationPersonaMismatchException {
          await _markFailed(
            intent,
            null,
            false,
            blockReason: LocalPostPublicationBlockReason.personaChanged,
          );
        } on _PostPublicationPermanentException {
          await _markFailed(
            intent,
            null,
            false,
            blockReason: LocalPostPublicationBlockReason.invalidReceipt,
          );
        } on CloudException catch (error) {
          final retryable = _isRetryable(error);
          await _markFailed(
            intent,
            error.code ?? error.runtimeFailure.code,
            retryable,
            retryAfter: _retryAfter(error),
            blockReason: retryable
                ? null
                : LocalPostPublicationBlockReason.remoteFailure,
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
      throw const _PostPublicationPersonaMismatchException();
    }
    final receipt = await ref
        .read(createContentPostPublicationWriterProvider)
        .submitPostPublication(intent.command);
    final publicationState = _acceptedPublicationState(receipt, intent);
    final accepted = intent.copyWith(
      postId: receipt.postId,
      committedVersion: receipt.committedVersion,
      acceptedAt: receipt.acceptedAt,
      publicationState: publicationState,
      retryCount: 0,
      nextAttemptAt:
          publicationState == ContentPostPublicationState.pendingReview
          ? DateTime.now().toUtc().add(const Duration(seconds: 15))
          : DateTime.now().toUtc(),
      clearLastErrorCode: true,
      clearBlockReason: true,
      blocked: false,
    );
    _replace(accepted);
    await _persist();
    if (publicationState == ContentPostPublicationState.published) {
      await _finishAcceptedIntent(accepted);
    } else {
      _scheduleRetry();
    }
    return receipt;
  }

  Future<void> _refreshPendingIntent(LocalPostPublicationIntent intent) async {
    final postId = intent.postId?.trim() ?? '';
    if (postId.isEmpty) {
      throw const _PostPublicationPermanentException();
    }
    final status = await ref
        .read(createWorkspaceContentPostPublicationStatusReaderProvider)
        .getPostPublicationStatus(postId);
    if (status.postId.trim() != postId) {
      throw const _PostPublicationPermanentException();
    }
    switch (status.state) {
      case ContentPostPublicationState.pendingReview:
        _replace(
          intent.copyWith(
            nextAttemptAt: DateTime.now().toUtc().add(
              const Duration(seconds: 15),
            ),
            retryCount: 0,
            clearLastErrorCode: true,
            clearBlockReason: true,
            blocked: false,
          ),
        );
        await _persist();
        return;
      case ContentPostPublicationState.published:
        final published = intent.copyWith(
          publicationState: ContentPostPublicationState.published,
          nextAttemptAt: DateTime.now().toUtc(),
          retryCount: 0,
          clearLastErrorCode: true,
          clearBlockReason: true,
          blocked: false,
        );
        _replace(published);
        await _persist();
        await _finishAcceptedIntent(published);
        return;
      case ContentPostPublicationState.rejected:
        _replace(
          intent.copyWith(
            publicationState: ContentPostPublicationState.rejected,
            lastErrorCode: ContentErrorCode.publicationRejected.code,
            blockReason: LocalPostPublicationBlockReason.rejected,
            blocked: true,
          ),
        );
        await _persist();
        return;
    }
  }

  Future<void> _finishAcceptedIntent(LocalPostPublicationIntent intent) async {
    if (intent.publicationState != ContentPostPublicationState.published) {
      throw const _PostPublicationPermanentException();
    }
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
    String? errorCode,
    bool retryable, {
    Duration? retryAfter,
    LocalPostPublicationBlockReason? blockReason,
  }) async {
    final retryCount = intent.retryCount + 1;
    final exponent = retryCount.clamp(0, 6).toInt();
    final fallbackDelaySeconds = 1 << exponent;
    final directedDelaySeconds = retryAfter?.inSeconds ?? 0;
    final delaySeconds = directedDelaySeconds > 0
        ? directedDelaySeconds.clamp(1, 3600).toInt()
        : fallbackDelaySeconds.clamp(2, 60).toInt();
    _replace(
      intent.copyWith(
        retryCount: retryCount,
        nextAttemptAt: DateTime.now().toUtc().add(
          Duration(seconds: delaySeconds),
        ),
        lastErrorCode: errorCode,
        clearLastErrorCode: errorCode == null,
        blockReason: blockReason,
        clearBlockReason: retryable && blockReason == null,
        blocked: !retryable,
      ),
    );
    await _persist();
    _scheduleRetry();
  }

  Duration? _retryAfter(CloudException error) {
    final transportRetryAfter = error.retryAfter;
    if (transportRetryAfter != null && transportRetryAfter > Duration.zero) {
      return transportRetryAfter;
    }
    final afterSeconds = error.runtimeFailure.recovery.afterSeconds;
    return afterSeconds > 0 ? Duration(seconds: afterSeconds) : null;
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
      state: intent.publicationState!.wireValue,
      committedVersion: intent.committedVersion!,
      acceptedAt: intent.acceptedAt!,
    );
  }

  ContentPostPublicationState _acceptedPublicationState(
    ContentPostPublicationReceipt receipt,
    LocalPostPublicationIntent intent,
  ) {
    final state = switch (receipt.state.trim()) {
      'pending_review' => ContentPostPublicationState.pendingReview,
      'published' => ContentPostPublicationState.published,
      _ => throw const _PostPublicationPermanentException(),
    };
    if (receipt.publishIntentId.trim() != intent.command.publishIntentId ||
        receipt.localDraftId.trim() != intent.command.localDraftId ||
        receipt.postId.trim().isEmpty ||
        receipt.committedVersion < 1 ||
        receipt.acceptedAt.millisecondsSinceEpoch <= 0) {
      throw const _PostPublicationPermanentException();
    }
    return state;
  }

  bool _isRetryable(CloudException error) {
    // 恢复动作由 errors.yaml -> RuntimeFailure 生成，是发布队列是否自动重试的
    // 唯一业务语义；HTTP 分类只在旧/畸形响应缺少 recovery 时兜底。
    final recoveryAction = error.runtimeFailure.recovery.action
        .trim()
        .toLowerCase();
    if (recoveryAction.isNotEmpty) {
      return recoveryAction == 'retry';
    }
    return switch (error.type) {
      CloudErrorType.timeout ||
      CloudErrorType.cancelled ||
      CloudErrorType.network ||
      CloudErrorType.rateLimited ||
      CloudErrorType.server ||
      CloudErrorType.invalidResponse ||
      CloudErrorType.unknown => true,
      CloudErrorType.unauthorized ||
      CloudErrorType.forbidden ||
      CloudErrorType.notFound => false,
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

ContentPostPublicationState? _optionalPublicationState(Object? value) {
  final normalized = value?.toString().trim() ?? '';
  if (normalized.isEmpty) {
    return null;
  }
  try {
    return ContentPostPublicationState.fromWire(normalized);
  } on FormatException {
    return null;
  }
}

bool _hasUnsupportedPublicationState(Object? value) {
  final normalized = value?.toString().trim() ?? '';
  return normalized.isNotEmpty && _optionalPublicationState(normalized) == null;
}

LocalPostPublicationBlockReason? _optionalBlockReason(Object? value) {
  final normalized = value?.toString().trim() ?? '';
  for (final reason in LocalPostPublicationBlockReason.values) {
    if (reason.name == normalized) {
      return reason;
    }
  }
  return normalized.isEmpty
      ? null
      : LocalPostPublicationBlockReason.invalidReceipt;
}
