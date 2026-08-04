// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001

import 'dart:async';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../support/recording_content_media_facet.dart';

void main() {
  group('ContentMediaUploadCoordinator commercial contract', () {
    test(
      'metadata policy rejects oversized media before opening a session',
      () async {
        final media = RecordingContentMediaFacet();
        final coordinator = ContentMediaUploadCoordinator(media: media);
        final source = PreparedContentMediaSource(
          fileSize: 50 * 1024 * 1024 + 1,
          sha256Digest: List<String>.filled(64, 'a').join(),
          openRead: () => const Stream<List<int>>.empty(),
        );

        await expectLater(
          coordinator.uploadPreparedSource(
            source: source,
            mediaType: MediaType.video,
            mimeType: 'video/mp4',
            uploadStream: _drainUpload,
          ),
          throwsA(
            isA<RuntimeFailureBase>().having(
              (failure) => failure.code,
              'code',
              'CONTENT.USER.media_file_too_large',
            ),
          ),
        );
        expect(media.initCommands, isEmpty);
      },
    );

    test(
      'retryable PUT reopens the stream and reports monotonic completion',
      () async {
        final media = RecordingContentMediaFacet();
        final coordinator = ContentMediaUploadCoordinator(
          media: media,
          objectUploadRetryBaseDelay: Duration.zero,
        );
        const bytes = <int>[1, 2, 3, 4];
        var attempts = 0;
        final progress = <double>[];

        final uploaded = await coordinator.uploadPreparedSource(
          source: PreparedContentMediaSource(
            fileSize: bytes.length,
            sha256Digest: sha256.convert(bytes).toString(),
            openRead: () => Stream<List<int>>.fromIterable(const <List<int>>[
              <int>[1, 2],
              <int>[3, 4],
            ]),
          ),
          mediaType: MediaType.video,
          mimeType: 'video/mp4',
          uploadStream:
              (
                _,
                body, {
                required contentLength,
                required mimeType,
                required expectedSha256,
                abortTrigger,
              }) async {
                attempts++;
                if (attempts == 1) {
                  throw const ContentMediaObjectUploadException(
                    retryable: true,
                  );
                }
                await body.drain<void>();
              },
          onProgress: (sent, total) => progress.add(sent / total),
        );

        expect(attempts, 2);
        expect(progress.last, 1);
        expect(
          progress.skipWhile((value) => value == 0),
          orderedEquals(<double>[0.5, 1]),
        );
        expect(uploaded.assetId, 'video_asset_1');
        expect(media.completedSessions, <String>['session_1']);
        expect(media.abortedSessions, isEmpty);
      },
    );

    test(
      'complete command carries only the explicitly disclosed EXIF snapshot',
      () async {
        final media = RecordingContentMediaFacet();
        final coordinator = ContentMediaUploadCoordinator(media: media);
        final capturedAt = DateTime.utc(2026, 5, 2, 8, 30);

        await coordinator.uploadPreparedSource(
          source: PreparedContentMediaSource(
            fileSize: 1,
            sha256Digest: sha256.convert(const <int>[1]).toString(),
            openRead: () => Stream<List<int>>.value(const <int>[1]),
          ),
          mediaType: MediaType.image,
          mimeType: 'image/jpeg',
          captureMetadata: MediaCaptureMetadata(
            cameraModel: 'ILCE-7M4',
            capturedAt: capturedAt,
          ),
          uploadStream: _drainUpload,
        );

        expect(media.completeCommands, hasLength(1));
        expect(
          media.completeCommands.single.captureMetadata?.toWire(),
          <String, Object?>{
            'cameraModel': 'ILCE-7M4',
            'capturedAt': capturedAt.toIso8601String(),
          },
        );
      },
    );

    test(
      'cancellation aborts both data plane and authoritative session',
      () async {
        final media = RecordingContentMediaFacet();
        final coordinator = ContentMediaUploadCoordinator(media: media);
        final cancellation = ContentMediaUploadCancellationSignal();
        final uploadStarted = Completer<void>();
        const bytes = <int>[1, 2, 3, 4];

        final upload = coordinator.uploadPreparedSource(
          source: PreparedContentMediaSource(
            fileSize: bytes.length,
            sha256Digest: sha256.convert(bytes).toString(),
            openRead: () => Stream<List<int>>.value(bytes),
          ),
          mediaType: MediaType.video,
          mimeType: 'video/mp4',
          cancellationSignal: cancellation,
          uploadStream:
              (
                _,
                _, {
                required contentLength,
                required mimeType,
                required expectedSha256,
                abortTrigger,
              }) async {
                uploadStarted.complete();
                await abortTrigger;
                throw const ContentMediaUploadCancelledException();
              },
        );

        await uploadStarted.future;
        cancellation.cancel();
        await expectLater(
          upload,
          throwsA(isA<ContentMediaUploadCancelledException>()),
        );
        expect(media.completedSessions, isEmpty);
        expect(media.abortedSessions, <String>['session_1']);
      },
    );

    test(
      'non-retryable PUT failure is attempted once and aborts session',
      () async {
        final media = RecordingContentMediaFacet();
        final coordinator = ContentMediaUploadCoordinator(
          media: media,
          objectUploadRetryBaseDelay: Duration.zero,
        );
        var attempts = 0;
        const bytes = <int>[1];

        await expectLater(
          coordinator.uploadPreparedSource(
            source: PreparedContentMediaSource(
              fileSize: bytes.length,
              sha256Digest: sha256.convert(bytes).toString(),
              openRead: () => Stream<List<int>>.value(bytes),
            ),
            mediaType: MediaType.image,
            mimeType: 'image/jpeg',
            uploadStream:
                (
                  _,
                  _, {
                  required contentLength,
                  required mimeType,
                  required expectedSha256,
                  abortTrigger,
                }) async {
                  attempts++;
                  throw const ContentMediaObjectUploadException(
                    retryable: false,
                    statusCode: 403,
                  );
                },
          ),
          throwsA(isA<ContentMediaObjectUploadException>()),
        );
        expect(attempts, 1);
        expect(media.abortedSessions, <String>['session_1']);
      },
    );

    test(
      'object failure telemetry records canonical code and recovery action',
      () async {
        final media = RecordingContentMediaFacet();
        final telemetry = _RecordingTelemetry();
        final coordinator = ContentMediaUploadCoordinator(
          media: media,
          telemetry: telemetry,
          objectUploadRetryBaseDelay: Duration.zero,
        );
        const bytes = <int>[1];

        await expectLater(
          coordinator.uploadPreparedSource(
            source: PreparedContentMediaSource(
              fileSize: bytes.length,
              sha256Digest: sha256.convert(bytes).toString(),
              openRead: () => Stream<List<int>>.value(bytes),
            ),
            mediaType: MediaType.image,
            mimeType: 'image/jpeg',
            uploadStream:
                (
                  _,
                  _, {
                  required contentLength,
                  required mimeType,
                  required expectedSha256,
                  abortTrigger,
                }) async {
                  throw const ContentMediaObjectUploadException(
                    retryable: false,
                    statusCode: 403,
                  );
                },
          ),
          throwsA(isA<ContentMediaObjectUploadException>()),
        );

        final failurePayloads = telemetry.payloads
            .where(
              (payload) =>
                  payload.extensions['result'] == 'failure' &&
                  (payload.eventType == 'operation_result' ||
                      payload.eventType == 'performance_sample'),
            )
            .toList(growable: false);
        expect(failurePayloads, hasLength(2));
        for (final payload in failurePayloads) {
          expect(
            payload.extensions['failReasonCode'],
            'CONTENT.SYSTEM.storage_write_failed',
          );
          expect(payload.extensions['recoveryAction'], 'retry');
        }
      },
    );

    test(
      'lost complete response reconciles asset identity without aborting',
      () async {
        final media = RecordingContentMediaFacet(
          loseFirstCompleteResponse: true,
        );
        final coordinator = ContentMediaUploadCoordinator(
          media: media,
          objectUploadRetryBaseDelay: Duration.zero,
        );
        const bytes = <int>[1, 2, 3, 4];

        final uploaded = await coordinator.uploadPreparedSource(
          source: PreparedContentMediaSource(
            fileSize: bytes.length,
            sha256Digest: sha256.convert(bytes).toString(),
            openRead: () => Stream<List<int>>.value(bytes),
          ),
          mediaType: MediaType.video,
          mimeType: 'video/mp4',
          uploadStream: _drainUpload,
        );

        expect(uploaded.sessionId, 'session_1');
        expect(uploaded.assetId, 'video_asset_1');
        expect(media.completedSessions, <String>['session_1']);
        expect(media.abortedSessions, isEmpty);
      },
    );

    test(
      'restart resumes the durable session with persisted idempotency keys',
      () async {
        final media = RecordingContentMediaFacet();
        final coordinator = ContentMediaUploadCoordinator(media: media);
        const bytes = <int>[9, 8, 7, 6];
        final checkpoint = ContentMediaPreparationCheckpoint.forSource(
          preparationIdentity: 'draft-durable-recovery',
          slot: 'video:0',
          mediaType: MediaType.video,
          sha256Digest: sha256.convert(bytes).toString(),
        );
        final initialized = await media.initUpload(
          InitContentMediaUploadCommand(
            mediaType: MediaType.video,
            mimeType: 'video/mp4',
            fileSize: bytes.length,
            expectedSha256: sha256.convert(bytes).toString(),
          ),
          ContentMediaUploadCommandContext(
            idempotencyKey: checkpoint.initIdempotencyKey,
          ),
        );
        final persisted = <ContentMediaPreparationCheckpoint>[
          checkpoint.copyWith(
            sessionId: initialized.sessionId,
            phase: ContentMediaPreparationPhase.uploading,
          ),
        ];

        final uploaded = await coordinator.uploadPreparedSource(
          source: PreparedContentMediaSource(
            fileSize: bytes.length,
            sha256Digest: sha256.convert(bytes).toString(),
            openRead: () => Stream<List<int>>.value(bytes),
          ),
          mediaType: MediaType.video,
          mimeType: 'video/mp4',
          uploadStream: _drainUpload,
          checkpoint: persisted.single,
          onCheckpoint: (updated) async {
            persisted
              ..clear()
              ..add(updated);
          },
        );

        expect(uploaded.sessionId, initialized.sessionId);
        expect(media.initCommands, hasLength(1));
        expect(media.initIdempotencyKeys, <String>[
          checkpoint.initIdempotencyKey,
        ]);
        expect(media.completeIdempotencyKeys, <String>[
          checkpoint.completeIdempotencyKey,
        ]);
        expect(persisted.single.isCompleted, isTrue);
        expect(persisted.single.assetId, uploaded.assetId);
      },
    );

    test(
      'expired durable grant aborts once and starts a new attempt',
      () async {
        final media = RecordingContentMediaFacet(
          uploadExpirations: <DateTime>[DateTime.utc(2000), DateTime.utc(2030)],
        );
        final coordinator = ContentMediaUploadCoordinator(media: media);
        const bytes = <int>[4, 3, 2, 1];
        final digest = sha256.convert(bytes).toString();
        final initial = ContentMediaPreparationCheckpoint.forSource(
          preparationIdentity: 'draft-expired-recovery',
          slot: 'video:0',
          mediaType: MediaType.video,
          sha256Digest: digest,
        );
        final expired = await media.initUpload(
          InitContentMediaUploadCommand(
            mediaType: MediaType.video,
            mimeType: 'video/mp4',
            fileSize: bytes.length,
            expectedSha256: digest,
          ),
          ContentMediaUploadCommandContext(
            idempotencyKey: initial.initIdempotencyKey,
          ),
        );
        var durable = initial.copyWith(
          sessionId: expired.sessionId,
          expiresAt: expired.expiresAt,
          phase: ContentMediaPreparationPhase.uploading,
        );

        final uploaded = await coordinator.uploadPreparedSource(
          source: PreparedContentMediaSource(
            fileSize: bytes.length,
            sha256Digest: digest,
            openRead: () => Stream<List<int>>.value(bytes),
          ),
          mediaType: MediaType.video,
          mimeType: 'video/mp4',
          uploadStream: _drainUpload,
          checkpoint: durable,
          onCheckpoint: (updated) async => durable = updated,
        );

        expect(media.abortedSessions, <String>['session_1']);
        expect(media.completedSessions, <String>['session_2']);
        expect(uploaded.sessionId, 'session_2');
        expect(durable.attempt, 1);
        expect(durable.isCompleted, isTrue);
        expect(media.initIdempotencyKeys.toSet(), hasLength(2));
      },
    );

    test(
      'unreconciled complete failure requests authoritative session cleanup',
      () async {
        final media = RecordingContentMediaFacet(
          loseFirstCompleteResponse: true,
          failUploadSessionRead: true,
        );
        final coordinator = ContentMediaUploadCoordinator(
          media: media,
          maxCompleteAttempts: 1,
        );
        const bytes = <int>[1, 2, 3, 4];

        await expectLater(
          coordinator.uploadPreparedSource(
            source: PreparedContentMediaSource(
              fileSize: bytes.length,
              sha256Digest: sha256.convert(bytes).toString(),
              openRead: () => Stream<List<int>>.value(bytes),
            ),
            mediaType: MediaType.video,
            mimeType: 'video/mp4',
            uploadStream: _drainUpload,
          ),
          throwsA(isA<StateError>()),
        );

        expect(media.completedSessions, <String>['session_1']);
        expect(media.abortedSessions, <String>['session_1']);
      },
    );

    test(
      'repeated pending complete failures issue one authoritative abort',
      () async {
        final media = RecordingContentMediaFacet(
          failCompleteWithoutCommit: true,
        );
        final coordinator = ContentMediaUploadCoordinator(
          media: media,
          maxCompleteAttempts: 2,
          objectUploadRetryBaseDelay: Duration.zero,
        );
        const bytes = <int>[1, 2, 3, 4];

        await expectLater(
          coordinator.uploadPreparedSource(
            source: PreparedContentMediaSource(
              fileSize: bytes.length,
              sha256Digest: sha256.convert(bytes).toString(),
              openRead: () => Stream<List<int>>.value(bytes),
            ),
            mediaType: MediaType.video,
            mimeType: 'video/mp4',
            uploadStream: _drainUpload,
          ),
          throwsA(isA<StateError>()),
        );

        expect(media.completedSessions, <String>['session_1', 'session_1']);
        expect(media.abortedSessions, <String>['session_1']);
      },
    );

    test(
      'lost discard response resumes from deleting with the same key',
      () async {
        final media = RecordingContentMediaFacet(
          loseFirstDiscardResponse: true,
        );
        final coordinator = ContentMediaUploadCoordinator(media: media);
        var durable =
            ContentMediaPreparationCheckpoint.forSource(
              preparationIdentity: 'draft-discard',
              slot: 'image:0',
              mediaType: MediaType.image,
              sha256Digest: sha256.convert(const <int>[1]).toString(),
            ).copyWith(
              sessionId: 'session-discard',
              assetId: 'asset-discard',
              phase: ContentMediaPreparationPhase.completed,
            );

        await expectLater(
          coordinator.cancelPreparedCheckpoint(
            durable,
            onCheckpoint: (checkpoint) async {
              durable = checkpoint;
            },
          ),
          throwsA(isA<StateError>()),
        );
        expect(durable.phase, ContentMediaPreparationPhase.deleting);

        final recovered = await coordinator.cancelPreparedCheckpoint(
          durable,
          onCheckpoint: (checkpoint) async {
            durable = checkpoint;
          },
        );

        expect(recovered.phase, ContentMediaPreparationPhase.deleted);
        expect(durable.phase, ContentMediaPreparationPhase.deleted);
        expect(media.discardCommands, hasLength(2));
        expect(media.discardIdempotencyKeys.toSet(), <String>{
          durable.discardIdempotencyKey,
        });
      },
    );
  });
}

Future<void> _drainUpload(
  Uri _,
  Stream<List<int>> body, {
  required int contentLength,
  required String mimeType,
  required String expectedSha256,
  Future<void>? abortTrigger,
}) async {
  await body.drain<void>();
}

final class _RecordingTelemetry implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> payloads = <AppTelemetryPayload>[];

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    payloads.add(payload);
    return AppTelemetryRecordResult.accepted;
  }
}
