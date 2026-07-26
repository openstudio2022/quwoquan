import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/remote/content/media/content_media_object_uploader.dart';

void main() {
  const digest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  final expectedChecksum = base64Encode(List<int>.filled(32, 0xaa));

  test(
    'stream upload sends every header bound into the presigned contract',
    () async {
      final client = _RecordingStreamClient();
      final uploader = RemoteContentMediaObjectUploader(client: client);

      await uploader.stream(
        Uri.parse('https://upload.example.test/object'),
        Stream<List<int>>.value(const <int>[1, 2, 3]),
        contentLength: 3,
        contentType: 'image/jpeg',
        expectedSha256: digest,
      );

      final request = client.request!;
      expect(request.headers['content-type'], 'image/jpeg');
      expect(request.headers['x-amz-checksum-sha256'], expectedChecksum);
      expect(request.headers['x-amz-meta-sha256'], digest);
      expect(client.body, const <int>[1, 2, 3]);
    },
  );

  test(
    'retryable object-storage status remains typed for coordinator retry',
    () async {
      final client = _RecordingStreamClient(statusCode: 503);
      final uploader = RemoteContentMediaObjectUploader(client: client);

      await expectLater(
        uploader.stream(
          Uri.parse('https://upload.example.test/retry'),
          Stream<List<int>>.value(const <int>[4]),
          contentLength: 1,
          contentType: 'video/mp4',
          expectedSha256: digest,
        ),
        throwsA(
          isA<ContentMediaObjectUploadException>()
              .having((error) => error.retryable, 'retryable', isTrue)
              .having((error) => error.statusCode, 'statusCode', 503),
        ),
      );
    },
  );
}

final class _RecordingStreamClient extends http.BaseClient {
  _RecordingStreamClient({this.statusCode = 200});

  final int statusCode;
  http.BaseRequest? request;
  List<int>? body;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    this.request = request;
    body = await request.finalize().toBytes();
    return http.StreamedResponse(const Stream<List<int>>.empty(), statusCode);
  }
}
