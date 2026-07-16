import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/remote/content/media/content_media_object_uploader.dart';

void main() {
  const digest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  final expectedChecksum = base64Encode(List<int>.filled(32, 0xaa));

  test(
    'byte upload sends every header bound into the presigned contract',
    () async {
      late http.Request captured;
      final uploader = RemoteContentMediaObjectUploader(
        client: MockClient((request) async {
          captured = request;
          return http.Response('', 200);
        }),
      );

      await uploader.call(
        Uri.parse('https://upload.example.test/object'),
        const <int>[1, 2, 3],
        contentType: 'image/jpeg',
        expectedSha256: digest,
      );

      expect(captured.headers['content-type'], 'image/jpeg');
      expect(captured.headers['x-amz-checksum-sha256'], expectedChecksum);
      expect(captured.headers['x-amz-meta-sha256'], digest);
      expect(captured.bodyBytes, const <int>[1, 2, 3]);
    },
  );

  test('stream upload uses the same integrity-bound headers', () async {
    final client = _RecordingStreamClient();
    final uploader = RemoteContentMediaObjectUploader(client: client);

    await uploader.stream(
      Uri.parse('https://upload.example.test/stream'),
      Stream<List<int>>.value(const <int>[4, 5, 6]),
      contentLength: 3,
      contentType: 'video/mp4',
      expectedSha256: digest,
    );

    final request = client.request!;
    expect(request.headers['content-type'], 'video/mp4');
    expect(request.headers['x-amz-checksum-sha256'], expectedChecksum);
    expect(request.headers['x-amz-meta-sha256'], digest);
    expect(client.body, const <int>[4, 5, 6]);
  });
}

final class _RecordingStreamClient extends http.BaseClient {
  http.BaseRequest? request;
  List<int>? body;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    this.request = request;
    body = await request.finalize().toBytes();
    return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
  }
}
