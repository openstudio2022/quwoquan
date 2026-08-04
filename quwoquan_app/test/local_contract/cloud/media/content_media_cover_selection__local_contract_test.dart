// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_cover_selection.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../support/runtime_failure_fixtures.dart';

void main() {
  test(
    'video cover retries canonical processing state with one command',
    () async {
      var attempts = 0;
      final delays = <Duration>[];

      final selected = await selectContentMediaCoverWhenReady(
        retryDelay: Duration.zero,
        wait: (delay) async => delays.add(delay),
        command: () async {
          attempts++;
          if (attempts < 3) {
            throw _mediaFailure(
              code: 'CONTENT.USER.media_not_ready',
              nature: RuntimeFailureNature.transient,
              recoveryAction: 'retry',
            );
          }
          return _selection();
        },
      );

      expect(selected.mediaId, 'video-asset-1');
      expect(attempts, 3);
      expect(delays, <Duration>[Duration.zero, Duration.zero]);
    },
  );

  test('video cover retries an optimistic worker completion race', () async {
    var attempts = 0;

    final selected = await selectContentMediaCoverWhenReady(
      retryDelay: Duration.zero,
      wait: (_) async {},
      command: () async {
        attempts++;
        if (attempts == 1) {
          throw _mediaFailure(
            code: 'CONTENT.USER.version_conflict',
            nature: RuntimeFailureNature.transient,
            recoveryAction: 'refresh',
          );
        }
        return _selection();
      },
    );

    expect(selected.mediaId, 'video-asset-1');
    expect(attempts, 2);
  });

  test('processing rejection is surfaced without retry', () async {
    var attempts = 0;
    await expectLater(
      selectContentMediaCoverWhenReady(
        retryDelay: Duration.zero,
        wait: (_) async {},
        command: () async {
          attempts++;
          throw _mediaFailure(
            code: 'CONTENT.USER.media_processing_rejected',
            nature: RuntimeFailureNature.permanent,
            recoveryAction: 'surface',
          );
        },
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          'CONTENT.USER.media_processing_rejected',
        ),
      ),
    );
    expect(attempts, 1);
  });
}

CloudException _mediaFailure({
  required String code,
  required RuntimeFailureNature nature,
  required String recoveryAction,
}) {
  return CloudException(
    type: CloudErrorType.invalidResponse,
    message: code,
    code: code,
    runtimeFailure: testRuntimeFailure(
      code: code,
      nature: nature,
      recovery: RuntimeRecoveryDirective(
        action: recoveryAction,
        afterSeconds: 0,
        disruptionLevel: recoveryAction == 'retry' ? 'silent' : 'inline',
      ),
    ),
  );
}

MediaCoverSelectionResult _selection() {
  final cover = Uri.parse('https://cdn.example.test/video-asset-1/cover.jpg');
  return MediaCoverSelectionResult(
    mediaId: 'video-asset-1',
    coverStrategy: MediaCoverStrategy.firstFrame,
    manualCoverAssetId: null,
    coverFrameTimeMs: 0,
    thumbnailUrl: cover,
    coverUrl: cover,
  );
}
