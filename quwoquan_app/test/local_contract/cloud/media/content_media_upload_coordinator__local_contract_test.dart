import 'dart:async';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
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
            mediaType: ContentMediaType.video,
            contentType: 'video/mp4',
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
          mediaType: ContentMediaType.video,
          contentType: 'video/mp4',
          uploadStream:
              (
                _,
                body, {
                required contentLength,
                required contentType,
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
          mediaType: ContentMediaType.video,
          contentType: 'video/mp4',
          cancellationSignal: cancellation,
          uploadStream:
              (
                _,
                _, {
                required contentLength,
                required contentType,
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
            mediaType: ContentMediaType.image,
            contentType: 'image/jpeg',
            uploadStream:
                (
                  _,
                  _, {
                  required contentLength,
                  required contentType,
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
          mediaType: ContentMediaType.video,
          contentType: 'video/mp4',
          uploadStream: _drainUpload,
        );

        expect(uploaded.sessionId, 'session_1');
        expect(uploaded.assetId, 'video_asset_1');
        expect(uploaded.cdnUrl, isNull);
        expect(media.completedSessions, <String>['session_1']);
        expect(media.abortedSessions, isEmpty);
      },
    );
  });
}

Future<void> _drainUpload(
  Uri _,
  Stream<List<int>> body, {
  required int contentLength,
  required String contentType,
  required String expectedSha256,
  Future<void>? abortTrigger,
}) async {
  await body.drain<void>();
}
