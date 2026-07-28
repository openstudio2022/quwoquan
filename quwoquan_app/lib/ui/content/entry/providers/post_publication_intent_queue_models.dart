part of 'post_publication_intent_queue_provider.dart';

enum LocalPostPublicationBlockReason {
  personaChanged,
  invalidReceipt,
  rejected,
  remoteFailure,
}

enum LocalPostPublicationStage { preparingMedia, submitting, cancellingMedia }

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
    this.preparedMediaAssets = const <ContentMediaPreparationCheckpoint>[],
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
  final List<ContentMediaPreparationCheckpoint> preparedMediaAssets;

  bool get publicationAccepted =>
      postId?.trim().isNotEmpty == true &&
      committedVersion != null &&
      acceptedAt != null &&
      (publicationState == ContentPostPublicationState.pendingReview ||
          publicationState == ContentPostPublicationState.published);
  bool get serverAccepted =>
      postId?.trim().isNotEmpty == true &&
      committedVersion != null &&
      acceptedAt != null;
  bool get requiresMediaPreparation =>
      stage == LocalPostPublicationStage.preparingMedia;
  bool get requiresMediaCancellation =>
      stage == LocalPostPublicationStage.cancellingMedia;

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
    List<ContentMediaPreparationCheckpoint>? preparedMediaAssets,
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
      preparedMediaAssets: preparedMediaAssets ?? this.preparedMediaAssets,
    );
  }

  factory LocalPostPublicationIntent.fromStorageMap(Map<String, Object?> map) {
    final command = decodeSubmitContentPostPublicationCommand(
      map['commandBody'],
    );
    return LocalPostPublicationIntent(
      command: command,
      authorPersonaId: (map['authorPersonaId'] ?? '').toString().trim(),
      circleIds: _normalizedCircleIds(
        (map['circleIds'] as List? ?? const <Object?>[]).map(
          (value) => value.toString(),
        ),
      ),
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
      preparedMediaAssets: _preparedMediaAssetsFromStorage(
        map['preparedMediaAssets'],
      ),
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
      'preparedMediaAssets': preparedMediaAssets
          .map((checkpoint) => checkpoint.toStorageMap())
          .toList(growable: false),
    };
  }
}
