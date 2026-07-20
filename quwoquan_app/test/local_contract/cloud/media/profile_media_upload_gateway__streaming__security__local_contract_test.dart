import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
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
      http.Request? uploadRequest;
      final rawClient = MockClient((request) async {
        uploadRequest = request;
        expect(request.method, 'PUT');
        expect(request.headers.containsKey('Authorization'), isFalse);
        expect(request.bodyBytes, <int>[1, 2, 3, 4]);
        return http.Response('', 200);
      });
      final media = RecordingContentMediaFacet();
      final gateway = ContentProfileMediaUploadGateway(
        media,
        httpClient: CloudHttpClient(client: rawClient),
      );

      final result = await gateway.uploadImage(
        localPath: file.path,
        target: ProfileMediaTarget.avatar,
      );

      expect(uploadRequest, isNotNull);
      expect(result.assetId, isNotEmpty);
      expect(media.initCommands.single.fileSize, 4);
      expect(
        media.initCommands.single.expectedSha256,
        'sha256:9f64a747e1b97f131fabb6b447296c9b6f0201e79fb3c5356e6c77e89b6a806a',
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
        media,
        httpClient: CloudHttpClient(
          client: MockClient((_) async => http.Response('', 403)),
        ),
      );

      await expectLater(
        gateway.uploadImage(
          localPath: file.path,
          target: ProfileMediaTarget.avatar,
        ),
        throwsA(isA<HttpException>()),
      );

      expect(media.abortedSessions, <String>['session_1']);
    },
  );
}
