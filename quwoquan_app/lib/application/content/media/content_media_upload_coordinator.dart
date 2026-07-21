import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/application/content/media/generated/content_media_upload_policy.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

typedef ContentMediaStreamObjectUpload =
    Future<void> Function(
      Uri uploadUri,
      Stream<List<int>> bytes, {
      required int contentLength,
      required String contentType,
      required String expectedSha256,
      Future<void>? abortTrigger,
    });

typedef ContentMediaUploadProgressCallback =
    void Function(int uploadedBytes, int totalBytes);

final class ContentMediaUploadCancellationSignal {
  final Completer<void> _cancelled = Completer<void>();

  bool get isCancelled => _cancelled.isCompleted;
  Future<void> get whenCancelled => _cancelled.future;

  void cancel() {
    if (!_cancelled.isCompleted) {
      _cancelled.complete();
    }
  }

  void throwIfCancelled() {
    if (isCancelled) {
      throw const ContentMediaUploadCancelledException();
    }
  }

  Future<void> waitOrCancel(Duration duration) async {
    throwIfCancelled();
    await Future.any<void>(<Future<void>>[
      Future<void>.delayed(duration),
      whenCancelled,
    ]);
    throwIfCancelled();
  }
}

final class ContentMediaUploadCancelledException implements Exception {
  const ContentMediaUploadCancelledException();
}

final class ContentMediaObjectUploadException implements Exception {
  const ContentMediaObjectUploadException({
    required this.retryable,
    this.statusCode,
    this.cause,
  });

  final bool retryable;
  final int? statusCode;
  final Object? cause;

  @override
  String toString() =>
      'ContentMediaObjectUploadException('
      'retryable: $retryable, statusCode: $statusCode)';
}

final class PreparedContentMediaSource {
  const PreparedContentMediaSource({
    required this.fileSize,
    required this.sha256Digest,
    required this.openRead,
  });

  final int fileSize;
  final String sha256Digest;
  final Stream<List<int>> Function() openRead;
}

enum ContentMediaPreparationPhase {
  initializing,
  uploading,
  completing,
  completed,
  cancelling,
  aborted,
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
    this.sessionId = '',
    this.phase = ContentMediaPreparationPhase.initializing,
    this.attempt = 0,
  });

  final String slot;
  final ContentMediaType mediaType;
  final String sha256Digest;
  final String assetId;
  final String initIdempotencyKey;
  final String completeIdempotencyKey;
  final String abortIdempotencyKey;
  final String sessionId;
  final ContentMediaPreparationPhase phase;
  final int attempt;

  bool get isCompleted =>
      phase == ContentMediaPreparationPhase.completed && assetId.isNotEmpty;

  factory ContentMediaPreparationCheckpoint.forSource({
    required String preparationIdentity,
    required String slot,
    required ContentMediaType mediaType,
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
      attempt: attempt,
    );
  }

  bool matches({
    required String expectedSlot,
    required ContentMediaType expectedMediaType,
    required String expectedSha256Digest,
  }) {
    return slot == expectedSlot &&
        mediaType == expectedMediaType &&
        sha256Digest == expectedSha256Digest;
  }

  ContentMediaPreparationCheckpoint copyWith({
    String? assetId,
    String? sessionId,
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
    final sessionId = value['sessionId']?.toString().trim() ?? '';
    final mediaType = ContentMediaType.values.where(
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
      sessionId: sessionId,
      phase: phase.first,
      attempt: (value['attempt'] as num?)?.toInt() ?? 0,
    );
  }
}

abstract interface class ContentMediaSourceReader {
  Future<PreparedContentMediaSource> prepare(String localPath);
}

Future<PreparedContentMediaSource> prepareContentMediaSource({
  required int fileSize,
  required Stream<List<int>> Function() openRead,
}) async {
  if (fileSize <= 0) {
    throw StateError('media source is empty');
  }
  final digest = await sha256.bind(openRead()).single;
  return PreparedContentMediaSource(
    fileSize: fileSize,
    sha256Digest: digest.toString(),
    openRead: openRead,
  );
}

final class UploadedContentMedia {
  const UploadedContentMedia({
    required this.sessionId,
    required this.assetId,
    required this.cdnUrl,
  });

  final String sessionId;
  final String assetId;
  final Uri? cdnUrl;
}

/// Application coordinator for the upload-session aggregate and its external
/// object-storage grant. It computes the immutable byte contract before
/// opening the session, retries only repeatable object writes, and reconciles a
/// possibly committed complete response before deciding whether abort is safe.
final class ContentMediaUploadCoordinator {
  const ContentMediaUploadCoordinator({
    required this.media,
    this.telemetry,
    this.maxObjectUploadAttempts = 3,
    this.maxCompleteAttempts = 2,
    this.objectUploadRetryBaseDelay = const Duration(milliseconds: 250),
  });

  /// 上传三段式（init/直传/complete）的 operation_result + performance_sample
  /// 观测锚点（R22 端侧性能打点）。
  static const String uploadOperationId =
      'content.media_upload_session.UploadMedia';

  final ContentMediaFacet media;
  final AppTelemetryRecorder? telemetry;
  final int maxObjectUploadAttempts;
  final int maxCompleteAttempts;
  final Duration objectUploadRetryBaseDelay;

  Future<UploadedContentMedia> uploadPreparedSource({
    required PreparedContentMediaSource source,
    required ContentMediaType mediaType,
    required String contentType,
    required ContentMediaStreamObjectUpload uploadStream,
    ContentMediaAccessPolicy accessPolicy = ContentMediaAccessPolicy.ownerOnly,
    ContentMediaUploadProgressCallback? onProgress,
    ContentMediaUploadCancellationSignal? cancellationSignal,
    ContentMediaPreparationCheckpoint? checkpoint,
    Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
    onCheckpoint,
  }) async {
    if (source.fileSize <= 0) throw StateError('media source is empty');
    validateContentMediaUploadPolicy(
      mediaType: mediaType,
      contentType: contentType,
      fileSize: source.fileSize,
    );
    cancellationSignal?.throwIfCancelled();
    return _upload(
      mediaType: mediaType,
      contentType: contentType,
      fileSize: source.fileSize,
      expectedSha256: source.sha256Digest,
      accessPolicy: accessPolicy,
      cancellationSignal: cancellationSignal,
      checkpoint:
          checkpoint ??
          ContentMediaPreparationCheckpoint.forSource(
            preparationIdentity: 'standalone',
            slot: 'standalone',
            mediaType: mediaType,
            sha256Digest: source.sha256Digest,
          ),
      onCheckpoint: onCheckpoint,
      writeObject: (uploadUrl, digest) => _writeObjectWithRetry(
        writeObject: () => uploadStream(
          uploadUrl,
          _trackedUploadStream(
            source.openRead(),
            contentLength: source.fileSize,
            onProgress: onProgress,
            cancellationSignal: cancellationSignal,
          ),
          contentLength: source.fileSize,
          contentType: contentType,
          expectedSha256: digest,
          abortTrigger: cancellationSignal?.whenCancelled,
        ),
        cancellationSignal: cancellationSignal,
      ),
    );
  }

  /// Reconciles a persisted cancellation before its draft may be discarded.
  ///
  /// A locally cancelled request is not authoritative: the server session may
  /// already have completed. Callers must retain the returned checkpoint when
  /// the transition remains [ContentMediaPreparationPhase.cancelling].
  Future<ContentMediaPreparationCheckpoint> cancelPreparedCheckpoint(
    ContentMediaPreparationCheckpoint checkpoint,
  ) async {
    var resolved = checkpoint;
    await _reconcileAndAbortPendingSession(
      checkpoint,
      onCheckpoint: (updated) async {
        resolved = updated;
      },
    );
    return resolved;
  }

  Future<UploadedContentMedia> _upload({
    required ContentMediaType mediaType,
    required String contentType,
    required int fileSize,
    required String expectedSha256,
    required ContentMediaAccessPolicy accessPolicy,
    required ContentMediaPreparationCheckpoint checkpoint,
    Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
    onCheckpoint,
    required Future<void> Function(Uri uploadUrl, String expectedSha256)
    writeObject,
    ContentMediaUploadCancellationSignal? cancellationSignal,
  }) async {
    final startedAt = DateTime.now();
    try {
      final uploaded = await _uploadWithoutTelemetry(
        mediaType: mediaType,
        contentType: contentType,
        fileSize: fileSize,
        expectedSha256: expectedSha256,
        accessPolicy: accessPolicy,
        checkpoint: checkpoint,
        onCheckpoint: onCheckpoint,
        writeObject: writeObject,
        cancellationSignal: cancellationSignal,
      );
      await _recordUploadOutcome(
        result: 'success',
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
      );
      return uploaded;
    } on ContentMediaUploadCancelledException {
      await _recordUploadOutcome(
        result: 'cancelled',
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
      );
      rethrow;
    } catch (error) {
      await _recordUploadOutcome(
        result: 'failure',
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        failReasonCode: error.runtimeType.toString(),
      );
      rethrow;
    }
  }

  Future<void> _recordUploadOutcome({
    required String result,
    required int durationMs,
    String? failReasonCode,
  }) async {
    final recorder = telemetry;
    if (recorder == null) return;
    // 观测失败不得影响上传结果（观测面板缺一条样本可接受，上传语义不可变）。
    try {
      await recorder.record(
        AppTelemetryPayload.operationResult(
          operationId: uploadOperationId,
          result: result,
          durationMs: durationMs,
          failReasonCode: failReasonCode,
        ),
      );
      await recorder.record(
        AppTelemetryPayload.performanceSample(
          operationId: uploadOperationId,
          durationMs: durationMs,
          result: result,
          failReasonCode: failReasonCode,
        ),
      );
    } catch (error, stackTrace) {
      developer.log(
        'Media upload telemetry recording failed',
        name: 'ContentMediaUploadCoordinator',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  Future<UploadedContentMedia> _uploadWithoutTelemetry({
    required ContentMediaType mediaType,
    required String contentType,
    required int fileSize,
    required String expectedSha256,
    required ContentMediaAccessPolicy accessPolicy,
    required ContentMediaPreparationCheckpoint checkpoint,
    Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
    onCheckpoint,
    required Future<void> Function(Uri uploadUrl, String expectedSha256)
    writeObject,
    ContentMediaUploadCancellationSignal? cancellationSignal,
  }) async {
    cancellationSignal?.throwIfCancelled();
    final operationCancellation = _operationCancellation(cancellationSignal);
    var durable = checkpoint;

    Future<void> persist(ContentMediaPreparationCheckpoint next) async {
      durable = next;
      await onCheckpoint?.call(next);
    }

    final recovered = await _recoverCompletedSession(
      durable,
      onCheckpoint: persist,
    );
    if (recovered != null) {
      return recovered;
    }

    final init = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: mediaType,
        contentType: contentType,
        fileSize: fileSize,
        expectedSha256: expectedSha256,
      ),
      ContentMediaUploadCommandContext(
        idempotencyKey: durable.initIdempotencyKey,
        cancellation: operationCancellation,
      ),
    );
    final sessionId = init.sessionId.trim();
    if (sessionId.isEmpty) throw StateError('media upload session is missing');
    if (init.status == ContentMediaUploadStatus.completed) {
      final completed = _uploadedFromCompletedResult(sessionId, init);
      await persist(
        durable.copyWith(
          sessionId: completed.sessionId,
          assetId: completed.assetId,
          phase: ContentMediaPreparationPhase.completed,
        ),
      );
      return completed;
    }
    await persist(
      durable.copyWith(
        sessionId: sessionId,
        phase: ContentMediaPreparationPhase.uploading,
      ),
    );
    final uploadUrl = init.uploadUrl;
    if (uploadUrl == null) {
      await _reconcileAndAbortPendingSession(durable, onCheckpoint: persist);
      throw StateError('media upload session is missing object upload URL');
    }
    try {
      cancellationSignal?.throwIfCancelled();
      await writeObject(uploadUrl, expectedSha256);
      cancellationSignal?.throwIfCancelled();
    } catch (error, stackTrace) {
      await _reconcileAndAbortPendingSession(durable, onCheckpoint: persist);
      Error.throwWithStackTrace(error, stackTrace);
    }
    await persist(
      durable.copyWith(phase: ContentMediaPreparationPhase.completing),
    );
    try {
      final completed = await _completeWithReconciliation(
        sessionId: sessionId,
        accessPolicy: accessPolicy,
        completeIdempotencyKey: durable.completeIdempotencyKey,
        operationCancellation: operationCancellation,
        cancellationSignal: cancellationSignal,
      );
      await persist(
        durable.copyWith(
          sessionId: completed.sessionId,
          assetId: completed.assetId,
          phase: ContentMediaPreparationPhase.completed,
        ),
      );
      return completed;
    } on ContentMediaUploadCancelledException {
      await _reconcileAndAbortPendingSession(durable, onCheckpoint: persist);
      rethrow;
    } catch (error, stackTrace) {
      await _reconcileAndAbortPendingSession(durable, onCheckpoint: persist);
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  Future<UploadedContentMedia> _completeWithReconciliation({
    required String sessionId,
    required ContentMediaAccessPolicy accessPolicy,
    required String completeIdempotencyKey,
    CloudOperationCancellationSignal? operationCancellation,
    ContentMediaUploadCancellationSignal? cancellationSignal,
  }) async {
    final attempts = maxCompleteAttempts < 1 ? 1 : maxCompleteAttempts;
    Object? lastError;
    StackTrace? lastStackTrace;
    for (var attempt = 1; attempt <= attempts; attempt++) {
      cancellationSignal?.throwIfCancelled();
      try {
        final completed = await media.completeUpload(
          CompleteContentMediaUploadCommand(
            sessionId: sessionId,
            accessPolicy: accessPolicy,
          ),
          ContentMediaUploadCommandContext(
            idempotencyKey: completeIdempotencyKey,
            cancellation: operationCancellation,
          ),
        );
        return _uploadedFromCompletedResult(sessionId, completed);
      } catch (error, stackTrace) {
        lastError = error;
        lastStackTrace = stackTrace;
      }

      final session = await _readUploadSessionForReconciliation(sessionId);
      if (session == null) {
        Error.throwWithStackTrace(lastError, lastStackTrace);
      }
      if (session.status == ContentMediaUploadStatus.completed) {
        final assetId = (session.assetId ?? '').trim();
        if (assetId.isEmpty) {
          throw StateError(
            'completed media upload session is missing recoverable assetId',
          );
        }
        return UploadedContentMedia(
          sessionId: sessionId,
          assetId: assetId,
          cdnUrl: null,
        );
      }
      if (session.status == ContentMediaUploadStatus.aborted) {
        Error.throwWithStackTrace(lastError, lastStackTrace);
      }
      if (attempt < attempts) {
        final delay = objectUploadRetryBaseDelay * (1 << (attempt - 1));
        if (cancellationSignal == null) {
          await Future<void>.delayed(delay);
        } else {
          await cancellationSignal.waitOrCancel(delay);
        }
      }
    }
    Error.throwWithStackTrace(lastError!, lastStackTrace!);
  }

  UploadedContentMedia _uploadedFromCompletedResult(
    String sessionId,
    ContentMediaUploadSessionCommandResult completed,
  ) {
    final assetId = (completed.assetId ?? '').trim();
    if (assetId.isEmpty) {
      throw StateError('completed media upload is missing assetId');
    }
    return UploadedContentMedia(
      sessionId: sessionId,
      assetId: assetId,
      cdnUrl: completed.cdnUrl,
    );
  }

  Future<ContentMediaUploadSessionSlice?> _readUploadSessionForReconciliation(
    String sessionId,
  ) async {
    try {
      return await media.getUploadSession(
        GetContentMediaUploadSessionQuery(sessionId: sessionId),
      );
    } catch (error, stackTrace) {
      developer.log(
        'Media upload completion reconciliation failed',
        name: 'ContentMediaUploadCoordinator',
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  Future<UploadedContentMedia?> _recoverCompletedSession(
    ContentMediaPreparationCheckpoint checkpoint, {
    required Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)
    onCheckpoint,
  }) async {
    if (checkpoint.isCompleted) {
      return UploadedContentMedia(
        sessionId: checkpoint.sessionId,
        assetId: checkpoint.assetId,
        cdnUrl: null,
      );
    }
    final sessionId = checkpoint.sessionId.trim();
    if (sessionId.isEmpty) {
      return null;
    }
    final session = await _readUploadSessionForReconciliation(sessionId);
    if (session == null) {
      return null;
    }
    if (session.status == ContentMediaUploadStatus.completed) {
      final assetId = (session.assetId ?? '').trim();
      if (assetId.isEmpty) {
        throw StateError(
          'completed media upload session is missing recoverable assetId',
        );
      }
      await onCheckpoint(
        checkpoint.copyWith(
          assetId: assetId,
          phase: ContentMediaPreparationPhase.completed,
        ),
      );
      return UploadedContentMedia(
        sessionId: sessionId,
        assetId: assetId,
        cdnUrl: null,
      );
    }
    if (session.status == ContentMediaUploadStatus.aborted) {
      await onCheckpoint(checkpoint.restartAfterAbort());
    }
    return null;
  }

  Future<void> _reconcileAndAbortPendingSession(
    ContentMediaPreparationCheckpoint checkpoint, {
    required Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)
    onCheckpoint,
  }) async {
    final sessionId = checkpoint.sessionId.trim();
    if (sessionId.isEmpty) {
      return;
    }
    await onCheckpoint(
      checkpoint.copyWith(phase: ContentMediaPreparationPhase.cancelling),
    );
    final beforeAbort = await _readUploadSessionForReconciliation(sessionId);
    if (beforeAbort?.status == ContentMediaUploadStatus.completed) {
      final assetId = (beforeAbort?.assetId ?? '').trim();
      if (assetId.isNotEmpty) {
        await onCheckpoint(
          checkpoint.copyWith(
            assetId: assetId,
            phase: ContentMediaPreparationPhase.completed,
          ),
        );
      }
      return;
    }
    if (beforeAbort?.status == ContentMediaUploadStatus.aborted) {
      await onCheckpoint(
        checkpoint.copyWith(phase: ContentMediaPreparationPhase.aborted),
      );
      return;
    }
    try {
      await media.abortUpload(
        AbortContentMediaUploadCommand(sessionId: sessionId),
        ContentMediaUploadCommandContext(
          idempotencyKey: checkpoint.abortIdempotencyKey,
        ),
      );
    } catch (error, stackTrace) {
      developer.log(
        'Media upload session abort failed',
        name: 'ContentMediaUploadCoordinator',
        error: error,
        stackTrace: stackTrace,
      );
    }
    final afterAbort = await _readUploadSessionForReconciliation(sessionId);
    if (afterAbort?.status == ContentMediaUploadStatus.completed) {
      final assetId = (afterAbort?.assetId ?? '').trim();
      if (assetId.isNotEmpty) {
        await onCheckpoint(
          checkpoint.copyWith(
            assetId: assetId,
            phase: ContentMediaPreparationPhase.completed,
          ),
        );
      }
      return;
    }
    if (afterAbort?.status == ContentMediaUploadStatus.aborted) {
      await onCheckpoint(
        checkpoint.copyWith(phase: ContentMediaPreparationPhase.aborted),
      );
    }
  }

  CloudOperationCancellationSignal? _operationCancellation(
    ContentMediaUploadCancellationSignal? cancellation,
  ) {
    if (cancellation == null) {
      return null;
    }
    final signal = CloudOperationCancellationSignal();
    unawaited(cancellation.whenCancelled.then((_) => signal.cancel()));
    return signal;
  }

  Future<void> _writeObjectWithRetry({
    required Future<void> Function() writeObject,
    ContentMediaUploadCancellationSignal? cancellationSignal,
  }) async {
    final attempts = maxObjectUploadAttempts < 1 ? 1 : maxObjectUploadAttempts;
    for (var attempt = 1; attempt <= attempts; attempt++) {
      cancellationSignal?.throwIfCancelled();
      try {
        await writeObject();
        return;
      } on ContentMediaUploadCancelledException {
        rethrow;
      } on ContentMediaObjectUploadException catch (error) {
        if (!error.retryable || attempt == attempts) {
          rethrow;
        }
        final multiplier = 1 << (attempt - 1);
        final delay = objectUploadRetryBaseDelay * multiplier;
        if (cancellationSignal == null) {
          await Future<void>.delayed(delay);
        } else {
          await cancellationSignal.waitOrCancel(delay);
        }
      }
    }
  }
}

String contentMediaTypeForPath(String path, ContentMediaType mediaType) {
  final lower = path.toLowerCase();
  return switch (mediaType) {
    ContentMediaType.image when lower.endsWith('.png') => 'image/png',
    ContentMediaType.image when lower.endsWith('.gif') => 'image/gif',
    ContentMediaType.image when lower.endsWith('.webp') => 'image/webp',
    ContentMediaType.image
        when lower.endsWith('.heic') || lower.endsWith('.heif') =>
      'image/heic',
    ContentMediaType.image => 'image/jpeg',
    ContentMediaType.video when lower.endsWith('.mov') => 'video/quicktime',
    ContentMediaType.video when lower.endsWith('.m4v') => 'video/x-m4v',
    ContentMediaType.video => 'video/mp4',
    ContentMediaType.audio when lower.endsWith('.aac') => 'audio/aac',
    ContentMediaType.audio when lower.endsWith('.m4a') => 'audio/x-m4a',
    ContentMediaType.audio when lower.endsWith('.mp4') => 'audio/mp4',
    ContentMediaType.audio => 'audio/mpeg',
    ContentMediaType.file => 'application/octet-stream',
  };
}

void validateContentMediaUploadPolicy({
  required ContentMediaType mediaType,
  required String contentType,
  required int fileSize,
}) {
  final policy = ContentMediaUploadPolicy.mediaTypes[mediaType.name];
  final normalizedContentType = contentType.trim().toLowerCase();
  if (policy == null ||
      normalizedContentType.isEmpty ||
      (!policy.allowedContentTypes.contains('*/*') &&
          !policy.allowedContentTypes.contains(normalizedContentType))) {
    throw _localUploadPolicyFailure(
      code: ContentMediaUploadPolicy.unsupportedTypeErrorCode,
      reason: 'media_type_unsupported',
      transportStatus: 415,
      kind: RuntimeFailureKind.unsupported,
    );
  }
  if (fileSize > policy.maxFileSizeBytes) {
    throw _localUploadPolicyFailure(
      code: ContentMediaUploadPolicy.fileTooLargeErrorCode,
      reason: 'media_file_too_large',
      transportStatus: 413,
      kind: RuntimeFailureKind.validation,
    );
  }
}

RuntimeFailure _localUploadPolicyFailure({
  required String code,
  required String reason,
  required int transportStatus,
  required RuntimeFailureKind kind,
}) => RuntimeFailure(
  code: code,
  semanticReason: reason,
  transportStatus: transportStatus,
  origin: RuntimeFailureOrigin.localClient,
  kind: kind,
  nature: RuntimeFailureNature.requiresUserAction,
  location: const RuntimeFailureLocation(
    businessObject: 'content.media_upload_session',
    functionModule: 'content_media_upload_coordinator',
  ),
  context: const RuntimeFailureContext(),
);

Stream<List<int>> _trackedUploadStream(
  Stream<List<int>> source, {
  required int contentLength,
  ContentMediaUploadProgressCallback? onProgress,
  ContentMediaUploadCancellationSignal? cancellationSignal,
}) async* {
  var uploadedBytes = 0;
  onProgress?.call(0, contentLength);
  await for (final chunk in source) {
    cancellationSignal?.throwIfCancelled();
    if (chunk.isEmpty) {
      continue;
    }
    uploadedBytes += chunk.length;
    if (uploadedBytes > contentLength) {
      throw StateError('media upload source exceeded declared content length');
    }
    yield chunk;
    onProgress?.call(uploadedBytes, contentLength);
  }
  cancellationSignal?.throwIfCancelled();
  if (uploadedBytes != contentLength) {
    throw StateError('media upload source length changed');
  }
}
