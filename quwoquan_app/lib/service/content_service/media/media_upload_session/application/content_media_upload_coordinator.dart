import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/generated/content_media_upload_policy.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_preparation_checkpoint.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

final class ContentMediaObjectUploadException
    implements Exception, RuntimeFailureBase {
  const ContentMediaObjectUploadException({
    required this.retryable,
    this.statusCode,
    this.cause,
  });

  final bool retryable;
  final int? statusCode;
  final Object? cause;
  RuntimeFailure get _failure => _objectUploadFailure(statusCode: statusCode);

  @override
  String get code => _failure.code;

  @override
  RuntimeFailureContext get context => _failure.context;

  @override
  RuntimeFailureKind get kind => _failure.kind;

  @override
  RuntimeFailureLocation get location => _failure.location;

  @override
  RuntimeFailureNature get nature => _failure.nature;

  @override
  RuntimeFailureOrigin get origin => _failure.origin;

  @override
  RuntimeRecoveryDirective get recovery => _failure.recovery;

  @override
  String get semanticReason => _failure.semanticReason;

  @override
  int? get transportStatus => _failure.transportStatus;

  @override
  String toString() =>
      'ContentMediaObjectUploadException('
      'retryable: $retryable, statusCode: $statusCode)';
}

RuntimeFailure _objectUploadFailure({int? statusCode}) {
  final error = ContentErrorCode.storageWriteFailed;
  return RuntimeFailure(
    code: error.code,
    semanticReason: 'media_object_upload_failed',
    transportStatus: error.httpStatus,
    origin: RuntimeFailureOrigin.remoteDependency,
    kind: RuntimeFailureKind.unavailable,
    nature: RuntimeFailureNature.transient,
    location: const RuntimeFailureLocation(
      businessObject: 'content.media_upload_session',
      functionModule: 'content_media_object_uploader',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        if (statusCode != null)
          RuntimeContextAttribute(
            key: 'objectStorageStatus',
            value: statusCode.toString(),
          ),
      ],
    ),
    recovery: RuntimeRecoveryDirective(
      action: error.recoveryAction,
      afterSeconds: error.recoveryAfterSeconds,
      disruptionLevel: 'fullPage',
    ),
  );
}

/// Application coordinator for the upload-session aggregate and its external
/// object-storage grant. It computes the immutable byte contract before
/// opening the session, retries only repeatable object writes, and reconciles a
/// possibly committed complete response before deciding whether abort is safe.
final class ContentMediaUploadCoordinator implements ContentMediaUploadService {
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

  @override
  Future<PreparedContentMediaSource> prepareSource({
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

  @override
  ContentMediaPreparationCheckpoint createPreparationCheckpoint({
    required String preparationIdentity,
    required String slot,
    required MediaType mediaType,
    required String sha256Digest,
    int attempt = 0,
  }) => _newContentMediaPreparationCheckpoint(
    preparationIdentity: preparationIdentity,
    slot: slot,
    mediaType: mediaType,
    sha256Digest: sha256Digest,
    attempt: attempt,
  );

  @override
  Future<UploadedContentMedia> uploadPreparedSource({
    required PreparedContentMediaSource source,
    required MediaType mediaType,
    required String mimeType,
    required ContentMediaStreamObjectUpload uploadStream,
    MediaAssetAccessPolicy accessPolicy = MediaAssetAccessPolicy.ownerOnly,
    MediaCaptureMetadata? captureMetadata,
    ContentMediaUploadProgressCallback? onProgress,
    ContentMediaUploadCancellationSignal? cancellationSignal,
    ContentMediaPreparationCheckpoint? checkpoint,
    Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
    onCheckpoint,
  }) async {
    if (source.fileSize <= 0) throw StateError('media source is empty');
    validateContentMediaUploadPolicy(
      mediaType: mediaType,
      mimeType: mimeType,
      fileSize: source.fileSize,
    );
    cancellationSignal?.throwIfCancelled();
    return _upload(
      mediaType: mediaType,
      mimeType: mimeType,
      fileSize: source.fileSize,
      expectedSha256: source.sha256Digest,
      accessPolicy: accessPolicy,
      captureMetadata: captureMetadata,
      cancellationSignal: cancellationSignal,
      checkpoint:
          checkpoint ??
          createPreparationCheckpoint(
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
          mimeType: mimeType,
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
  @override
  Future<ContentMediaPreparationCheckpoint> cancelPreparedCheckpoint(
    ContentMediaPreparationCheckpoint checkpoint, {
    Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
    onCheckpoint,
  }) async {
    var resolved = checkpoint;
    Future<void> persist(ContentMediaPreparationCheckpoint updated) async {
      resolved = updated;
      await onCheckpoint?.call(updated);
    }

    if (resolved.phase == ContentMediaPreparationPhase.deleted) {
      return resolved;
    }
    if (resolved.assetId.trim().isNotEmpty &&
        (resolved.phase == ContentMediaPreparationPhase.completed ||
            resolved.phase == ContentMediaPreparationPhase.deleting)) {
      await _discardCompletedAsset(resolved, onCheckpoint: persist);
      return resolved;
    }
    await _reconcileAndAbortPendingSession(resolved, onCheckpoint: persist);
    if (resolved.assetId.trim().isNotEmpty &&
        resolved.phase == ContentMediaPreparationPhase.completed) {
      await _discardCompletedAsset(resolved, onCheckpoint: persist);
    }
    return resolved;
  }

  Future<void> _discardCompletedAsset(
    ContentMediaPreparationCheckpoint checkpoint, {
    required Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)
    onCheckpoint,
  }) async {
    final mediaID = checkpoint.assetId.trim();
    if (mediaID.isEmpty) {
      throw StateError('completed media checkpoint is missing assetId');
    }
    final deleting = checkpoint.copyWith(
      phase: ContentMediaPreparationPhase.deleting,
    );
    await onCheckpoint(deleting);
    final result = await media.discardMediaAsset(
      DiscardContentMediaAssetCommand(mediaId: mediaID),
      ContentMediaAssetCommandContext(
        idempotencyKey: checkpoint.discardIdempotencyKey,
      ),
    );
    if (result.mediaId != mediaID ||
        result.status != MediaAssetDiscardStatus.deleted) {
      throw StateError('media discard response does not match checkpoint');
    }
    await onCheckpoint(
      deleting.copyWith(phase: ContentMediaPreparationPhase.deleted),
    );
  }

  Future<UploadedContentMedia> _upload({
    required MediaType mediaType,
    required String mimeType,
    required int fileSize,
    required String expectedSha256,
    required MediaAssetAccessPolicy accessPolicy,
    MediaCaptureMetadata? captureMetadata,
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
        mimeType: mimeType,
        fileSize: fileSize,
        expectedSha256: expectedSha256,
        accessPolicy: accessPolicy,
        captureMetadata: captureMetadata,
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
      final failure = error is RuntimeFailureBase ? error : null;
      await _recordUploadOutcome(
        result: 'failure',
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        failReasonCode: failure?.code ?? ContentErrorCode.internalError.code,
        recoveryAction:
            failure?.recovery.action ??
            ContentErrorCode.internalError.recoveryAction,
      );
      rethrow;
    }
  }

  Future<void> _recordUploadOutcome({
    required String result,
    required int durationMs,
    String? failReasonCode,
    String? recoveryAction,
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
          recoveryAction: recoveryAction,
        ),
      );
      await recorder.record(
        AppTelemetryPayload.performanceSample(
          operationId: uploadOperationId,
          durationMs: durationMs,
          result: result,
          failReasonCode: failReasonCode,
          recoveryAction: recoveryAction,
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
    required MediaType mediaType,
    required String mimeType,
    required int fileSize,
    required String expectedSha256,
    required MediaAssetAccessPolicy accessPolicy,
    MediaCaptureMetadata? captureMetadata,
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

    late MediaUploadSessionCommandResult init;
    while (true) {
      final recovered = await _recoverCompletedSession(
        durable,
        onCheckpoint: persist,
      );
      if (recovered != null) {
        return recovered;
      }
      if (_checkpointGrantExpired(durable)) {
        await _reconcileAndAbortPendingSession(durable, onCheckpoint: persist);
        if (durable.phase == ContentMediaPreparationPhase.completed) {
          return _uploadedFromAssetID(durable.sessionId, durable.assetId);
        }
        if (durable.phase == ContentMediaPreparationPhase.aborted) {
          await persist(_restartContentMediaPreparationCheckpoint(durable));
          continue;
        }
      }

      final candidate = await media.initUpload(
        InitContentMediaUploadCommand(
          mediaType: mediaType,
          mimeType: mimeType,
          fileSize: fileSize,
          expectedSha256: expectedSha256,
        ),
        ContentMediaUploadCommandContext(
          idempotencyKey: durable.initIdempotencyKey,
          cancellation: operationCancellation,
        ),
      );
      final candidateSessionId = candidate.sessionId.trim();
      if (candidateSessionId.isEmpty) {
        throw StateError('media upload session is missing');
      }
      await persist(
        durable.copyWith(
          sessionId: candidateSessionId,
          expiresAt: candidate.expiresAt,
          phase: ContentMediaPreparationPhase.uploading,
        ),
      );
      if (_checkpointGrantExpired(durable)) {
        continue;
      }
      init = candidate;
      break;
    }
    final sessionId = init.sessionId.trim();
    if (sessionId.isEmpty) throw StateError('media upload session is missing');
    if (init.status == MediaUploadSessionStatus.completed) {
      final completed = _uploadedFromCompletedResult(sessionId, init);
      await persist(
        durable.copyWith(
          sessionId: completed.sessionId,
          assetId: completed.assetId,
          expiresAt: init.expiresAt,
          phase: ContentMediaPreparationPhase.completed,
        ),
      );
      return completed;
    }
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
        captureMetadata: captureMetadata,
        completeIdempotencyKey: durable.completeIdempotencyKey,
        operationCancellation: operationCancellation,
        cancellationSignal: cancellationSignal,
      );
      await persist(
        durable.copyWith(
          sessionId: completed.sessionId,
          assetId: completed.assetId,
          expiresAt: init.expiresAt,
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
    required MediaAssetAccessPolicy accessPolicy,
    MediaCaptureMetadata? captureMetadata,
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
            captureMetadata: captureMetadata,
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
      if (session.status == MediaUploadSessionStatus.completed) {
        final assetId = (session.assetId ?? '').trim();
        if (assetId.isEmpty) {
          throw StateError(
            'completed media upload session is missing recoverable assetId',
          );
        }
        return _uploadedFromAssetID(sessionId, assetId);
      }
      if (session.status == MediaUploadSessionStatus.aborted) {
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
    MediaUploadSessionCommandResult completed,
  ) {
    final assetId = (completed.assetId ?? '').trim();
    if (assetId.isEmpty) {
      throw StateError('completed media upload is missing assetId');
    }
    return UploadedContentMedia(
      sessionId: sessionId,
      assetId: assetId,
      assetProcessingStatus: completed.assetProcessingStatus,
    );
  }

  Future<UploadedContentMedia> _uploadedFromAssetID(
    String sessionId,
    String assetId,
  ) async {
    final asset = await media.getMediaAsset(
      GetContentMediaAssetQuery(mediaId: assetId),
    );
    if (asset.assetId != assetId) {
      throw StateError(
        'media asset reconciliation returned a mismatched asset',
      );
    }
    return UploadedContentMedia(
      sessionId: sessionId,
      assetId: assetId,
      assetProcessingStatus: asset.status,
    );
  }

  Future<MediaUploadSessionSlice?> _readUploadSessionForReconciliation(
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
      return _uploadedFromAssetID(checkpoint.sessionId, checkpoint.assetId);
    }
    final sessionId = checkpoint.sessionId.trim();
    if (sessionId.isEmpty) {
      return null;
    }
    final session = await _readUploadSessionForReconciliation(sessionId);
    if (session == null) {
      return null;
    }
    if (checkpoint.expiresAt?.toUtc() != session.expiresAt.toUtc()) {
      await onCheckpoint(checkpoint.copyWith(expiresAt: session.expiresAt));
    }
    if (session.status == MediaUploadSessionStatus.completed) {
      final assetId = (session.assetId ?? '').trim();
      if (assetId.isEmpty) {
        throw StateError(
          'completed media upload session is missing recoverable assetId',
        );
      }
      await onCheckpoint(
        checkpoint.copyWith(
          assetId: assetId,
          expiresAt: session.expiresAt,
          phase: ContentMediaPreparationPhase.completed,
        ),
      );
      return _uploadedFromAssetID(sessionId, assetId);
    }
    if (session.status == MediaUploadSessionStatus.aborted) {
      await onCheckpoint(_restartContentMediaPreparationCheckpoint(checkpoint));
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
      await onCheckpoint(
        checkpoint.copyWith(phase: ContentMediaPreparationPhase.aborted),
      );
      return;
    }
    await onCheckpoint(
      checkpoint.copyWith(phase: ContentMediaPreparationPhase.cancelling),
    );
    final beforeAbort = await _readUploadSessionForReconciliation(sessionId);
    if (beforeAbort?.status == MediaUploadSessionStatus.completed) {
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
    if (beforeAbort?.status == MediaUploadSessionStatus.aborted) {
      await onCheckpoint(
        checkpoint.copyWith(phase: ContentMediaPreparationPhase.aborted),
      );
      return;
    }
    Object? abortError;
    StackTrace? abortStackTrace;
    try {
      final aborted = await media.abortUpload(
        AbortContentMediaUploadCommand(sessionId: sessionId),
        ContentMediaUploadCommandContext(
          idempotencyKey: checkpoint.abortIdempotencyKey,
        ),
      );
      if (aborted.status == MediaUploadSessionStatus.completed) {
        final assetId = (aborted.assetId ?? '').trim();
        if (assetId.isNotEmpty) {
          await onCheckpoint(
            checkpoint.copyWith(
              assetId: assetId,
              phase: ContentMediaPreparationPhase.completed,
            ),
          );
          return;
        }
      }
      if (aborted.status == MediaUploadSessionStatus.aborted) {
        await onCheckpoint(
          checkpoint.copyWith(phase: ContentMediaPreparationPhase.aborted),
        );
        return;
      }
      abortError = StateError(
        'media abort response did not reach a terminal state',
      );
      abortStackTrace = StackTrace.current;
    } catch (error, stackTrace) {
      abortError = error;
      abortStackTrace = stackTrace;
    }
    final afterAbort = await _readUploadSessionForReconciliation(sessionId);
    if (afterAbort?.status == MediaUploadSessionStatus.completed) {
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
    if (afterAbort?.status == MediaUploadSessionStatus.aborted) {
      await onCheckpoint(
        checkpoint.copyWith(phase: ContentMediaPreparationPhase.aborted),
      );
      return;
    }
    Error.throwWithStackTrace(abortError, abortStackTrace);
  }

  bool _checkpointGrantExpired(ContentMediaPreparationCheckpoint checkpoint) {
    final expiresAt = checkpoint.expiresAt;
    if (expiresAt == null ||
        checkpoint.sessionId.trim().isEmpty ||
        checkpoint.phase == ContentMediaPreparationPhase.completed ||
        checkpoint.phase == ContentMediaPreparationPhase.aborted ||
        checkpoint.phase == ContentMediaPreparationPhase.deleted) {
      return false;
    }
    return !DateTime.now().toUtc().isBefore(expiresAt.toUtc());
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

ContentMediaPreparationCheckpoint _newContentMediaPreparationCheckpoint({
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

ContentMediaPreparationCheckpoint _restartContentMediaPreparationCheckpoint(
  ContentMediaPreparationCheckpoint checkpoint,
) {
  final nextAttempt = checkpoint.attempt + 1;
  String retryKey(String currentKey) {
    final digest = sha256.convert(
      utf8.encode('retry|$nextAttempt|$currentKey'),
    );
    return 'media-upload-retry-$digest';
  }

  return ContentMediaPreparationCheckpoint(
    slot: checkpoint.slot,
    mediaType: checkpoint.mediaType,
    sha256Digest: checkpoint.sha256Digest,
    assetId: '',
    initIdempotencyKey: retryKey(checkpoint.initIdempotencyKey),
    completeIdempotencyKey: retryKey(checkpoint.completeIdempotencyKey),
    abortIdempotencyKey: retryKey(checkpoint.abortIdempotencyKey),
    discardIdempotencyKey: retryKey(checkpoint.discardIdempotencyKey),
    expiresAt: null,
    phase: ContentMediaPreparationPhase.initializing,
    attempt: nextAttempt,
  );
}

void validateContentMediaUploadPolicy({
  required MediaType mediaType,
  required String mimeType,
  required int fileSize,
}) {
  final policy = ContentMediaUploadPolicy.mediaTypes[mediaType.name];
  final normalizedContentType = mimeType.trim().toLowerCase();
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
