part of 'content_media_upload_coordinator.dart';

enum ContentMediaPreparationPhase {
  initializing,
  uploading,
  completing,
  completed,
  cancelling,
  aborted,
  deleting,
  deleted,
}

/// Durable, path-free checkpoint for one source slot in a publication draft.
///
/// The draft owns the local path; this record owns only immutable source
/// identity and server-side upload state. It is persisted before init so a
/// restart, cancellation, or lost complete response always resumes from the
/// authoritative upload session instead of creating another MediaAsset.
final class ContentMediaPreparationCheckpoint {
  const ContentMediaPreparationCheckpoint({
    required this.slot,
    required this.mediaType,
    required this.sha256Digest,
    required this.assetId,
    required this.initIdempotencyKey,
    required this.completeIdempotencyKey,
    required this.abortIdempotencyKey,
    required this.discardIdempotencyKey,
    this.expiresAt,
    this.sessionId = '',
    this.phase = ContentMediaPreparationPhase.initializing,
    this.attempt = 0,
  });

  final String slot;
  final MediaType mediaType;
  final String sha256Digest;
  final String assetId;
  final String initIdempotencyKey;
  final String completeIdempotencyKey;
  final String abortIdempotencyKey;
  final String discardIdempotencyKey;
  final DateTime? expiresAt;
  final String sessionId;
  final ContentMediaPreparationPhase phase;
  final int attempt;

  bool get isCompleted =>
      phase == ContentMediaPreparationPhase.completed && assetId.isNotEmpty;

  factory ContentMediaPreparationCheckpoint.forSource({
    required String preparationIdentity,
    required String slot,
    required MediaType mediaType,
    required String sha256Digest,
    int attempt = 0,
  }) {
    final identity =
        '$preparationIdentity|$slot|${mediaType.name}|$sha256Digest|$attempt';
    String commandKey(String transition) {
      final digest = sha256.convert(utf8.encode('$transition|$identity'));
      return 'media-upload-$transition-$digest';
    }

    return ContentMediaPreparationCheckpoint(
      slot: slot,
      mediaType: mediaType,
      sha256Digest: sha256Digest,
      assetId: '',
      initIdempotencyKey: commandKey('init'),
      completeIdempotencyKey: commandKey('complete'),
      abortIdempotencyKey: commandKey('abort'),
      discardIdempotencyKey: commandKey('discard'),
      attempt: attempt,
    );
  }

  bool matches({
    required String expectedSlot,
    required MediaType expectedMediaType,
    required String expectedSha256Digest,
  }) {
    return slot == expectedSlot &&
        mediaType == expectedMediaType &&
        sha256Digest == expectedSha256Digest;
  }

  ContentMediaPreparationCheckpoint copyWith({
    String? assetId,
    String? sessionId,
    DateTime? expiresAt,
    ContentMediaPreparationPhase? phase,
    int? attempt,
  }) {
    return ContentMediaPreparationCheckpoint(
      slot: slot,
      mediaType: mediaType,
      sha256Digest: sha256Digest,
      assetId: assetId ?? this.assetId,
      initIdempotencyKey: initIdempotencyKey,
      completeIdempotencyKey: completeIdempotencyKey,
      abortIdempotencyKey: abortIdempotencyKey,
      discardIdempotencyKey: discardIdempotencyKey,
      expiresAt: expiresAt ?? this.expiresAt,
      sessionId: sessionId ?? this.sessionId,
      phase: phase ?? this.phase,
      attempt: attempt ?? this.attempt,
    );
  }

  ContentMediaPreparationCheckpoint restartAfterAbort() {
    final nextAttempt = attempt + 1;
    String retryKey(String currentKey) {
      final digest = sha256.convert(
        utf8.encode('retry|$nextAttempt|$currentKey'),
      );
      return 'media-upload-retry-$digest';
    }

    return ContentMediaPreparationCheckpoint(
      slot: slot,
      mediaType: mediaType,
      sha256Digest: sha256Digest,
      assetId: '',
      initIdempotencyKey: retryKey(initIdempotencyKey),
      completeIdempotencyKey: retryKey(completeIdempotencyKey),
      abortIdempotencyKey: retryKey(abortIdempotencyKey),
      discardIdempotencyKey: retryKey(discardIdempotencyKey),
      expiresAt: null,
      phase: ContentMediaPreparationPhase.initializing,
      attempt: nextAttempt,
    );
  }

  Map<String, Object?> toStorageMap() => <String, Object?>{
    'slot': slot,
    'mediaType': mediaType.name,
    'sha256Digest': sha256Digest,
    'assetId': assetId,
    'initIdempotencyKey': initIdempotencyKey,
    'completeIdempotencyKey': completeIdempotencyKey,
    'abortIdempotencyKey': abortIdempotencyKey,
    'discardIdempotencyKey': discardIdempotencyKey,
    'expiresAt': expiresAt?.toUtc().toIso8601String(),
    'sessionId': sessionId,
    'phase': phase.name,
    'attempt': attempt,
  };

  static ContentMediaPreparationCheckpoint? tryParse(Object? value) {
    if (value is! Map) {
      return null;
    }
    final slot = value['slot']?.toString().trim() ?? '';
    final digest = value['sha256Digest']?.toString().trim() ?? '';
    final assetId = value['assetId']?.toString().trim() ?? '';
    final initIdempotencyKey =
        value['initIdempotencyKey']?.toString().trim() ?? '';
    final completeIdempotencyKey =
        value['completeIdempotencyKey']?.toString().trim() ?? '';
    final abortIdempotencyKey =
        value['abortIdempotencyKey']?.toString().trim() ?? '';
    final discardIdempotencyKey =
        value['discardIdempotencyKey']?.toString().trim() ?? '';
    final sessionId = value['sessionId']?.toString().trim() ?? '';
    final expiresAt = DateTime.tryParse(
      value['expiresAt']?.toString().trim() ?? '',
    )?.toUtc();
    final mediaType = MediaType.values.where(
      (candidate) => candidate.name == value['mediaType']?.toString(),
    );
    final phase = ContentMediaPreparationPhase.values.where(
      (candidate) => candidate.name == value['phase']?.toString(),
    );
    if (slot.isEmpty ||
        digest.isEmpty ||
        mediaType.isEmpty ||
        initIdempotencyKey.isEmpty ||
        completeIdempotencyKey.isEmpty ||
        abortIdempotencyKey.isEmpty ||
        discardIdempotencyKey.isEmpty ||
        phase.isEmpty) {
      return null;
    }
    return ContentMediaPreparationCheckpoint(
      slot: slot,
      mediaType: mediaType.first,
      sha256Digest: digest,
      assetId: assetId,
      initIdempotencyKey: initIdempotencyKey,
      completeIdempotencyKey: completeIdempotencyKey,
      abortIdempotencyKey: abortIdempotencyKey,
      discardIdempotencyKey: discardIdempotencyKey,
      expiresAt: expiresAt,
      sessionId: sessionId,
      phase: phase.first,
      attempt: (value['attempt'] as num?)?.toInt() ?? 0,
    );
  }
}
