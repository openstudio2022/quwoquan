import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/remote/content/media/local_media_upload_source.dart';
import 'package:quwoquan_app/cloud/services/user/profile_media_upload_gateway.dart';

import '../../../support/recording_content_media_facet.dart';

void main() {
  test(
    'profile media streams only to presigned data plane without auth',
    () async {
      final tempDir = Directory.systemTemp.createTempSync(
        'qwq-profile-upload-',
      );
      addTearDown(() => tempDir.deleteSync(recursive: true));
      final file = File('${tempDir.path}/avatar.jpg')
        ..writeAsBytesSync(<int>[1, 2, 3, 4]);
      final media = RecordingContentMediaFacet();
      final gateway = ContentProfileMediaUploadGateway(
        ContentMediaUploadCoordinator(media: media),
        const LocalContentMediaSourceReader(),
        (
          uploadUri,
          bytes, {
          required contentLength,
          required mimeType,
          required expectedSha256,
          abortTrigger,
        }) async {
          expect(uploadUri.scheme, 'https');
          expect(contentLength, 4);
          expect(mimeType, 'image/jpeg');
          expect(
            expectedSha256,
            '9f64a747e1b97f131fabb6b447296c9b6f0201e79fb3c5356e6c77e89b6a806a',
          );
          expect(await bytes.expand((chunk) => chunk).toList(), <int>[
            1,
            2,
            3,
            4,
          ]);
        },
      );

      final result = await gateway.uploadImage(
        localPath: file.path,
        target: ProfileMediaTarget.avatar,
      );

      expect(result.assetId, isNotEmpty);
      expect(media.initCommands.single.fileSize, 4);
      expect(
        media.initCommands.single.expectedSha256,
        '9f64a747e1b97f131fabb6b447296c9b6f0201e79fb3c5356e6c77e89b6a806a',
      );
    },
  );

  test(
    'profile media aborts authoritative session after data-plane failure',
    () async {
      final tempDir = Directory.systemTemp.createTempSync('qwq-profile-abort-');
      addTearDown(() => tempDir.deleteSync(recursive: true));
      final file = File('${tempDir.path}/avatar.jpg')
        ..writeAsBytesSync(<int>[1, 2, 3, 4]);
      final media = RecordingContentMediaFacet();
      final gateway = ContentProfileMediaUploadGateway(
        ContentMediaUploadCoordinator(media: media),
        const LocalContentMediaSourceReader(),
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
      );

      await expectLater(
        gateway.uploadImage(
          localPath: file.path,
          target: ProfileMediaTarget.avatar,
        ),
        throwsA(isA<ContentMediaObjectUploadException>()),
      );

      expect(media.abortedSessions, <String>['session_1']);
    },
  );
}
