import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/remote/content/media/content_media_object_uploader.dart';

void main() {
  const digest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  final expectedChecksum = base64Encode(List<int>.filled(32, 0xaa));

  test(
    'stream upload sends every header bound into the presigned contract',
    () async {
      final client = _RecordingStreamClient();
      final uploader = RemoteContentMediaObjectUploader(
        client: client,
        uploadBaseUrl: 'https://upload.example.test',
      );

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
    'object-storage failures keep retry policy and canonical failure semantics',
    () async {
      final client = _RecordingStreamClient(statusCode: 503);
      final uploader = RemoteContentMediaObjectUploader(
        client: client,
        uploadBaseUrl: 'https://upload.example.test',
      );

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
              .having((error) => error.statusCode, 'statusCode', 503)
              .having(
                (error) => error.code,
                'canonical code',
                ContentErrorCode.storageWriteFailed.code,
              )
              .having(
                (error) => error.recovery.action,
                'recovery action',
                ContentErrorCode.storageWriteFailed.recoveryAction,
              ),
        ),
      );
    },
  );

  test(
    '403 remains a storage failure instead of an assumed expired grant',
    () async {
      final uploader = RemoteContentMediaObjectUploader(
        client: _RecordingStreamClient(statusCode: 403),
        uploadBaseUrl: 'https://upload.example.test',
      );

      await expectLater(
        uploader.stream(
          Uri.parse('https://upload.example.test/forbidden'),
          Stream<List<int>>.value(const <int>[5]),
          contentLength: 1,
          contentType: 'image/jpeg',
          expectedSha256: digest,
        ),
        throwsA(
          isA<ContentMediaObjectUploadException>()
              .having((error) => error.retryable, 'retryable', isFalse)
              .having((error) => error.statusCode, 'statusCode', 403)
              .having(
                (error) => error.code,
                'canonical code',
                ContentErrorCode.storageWriteFailed.code,
              )
              .having(
                (error) => error.semanticReason,
                'semantic reason',
                'media_object_upload_failed',
              ),
        ),
      );
    },
  );

  test('transport exceptions use the same canonical storage failure', () async {
    final uploader = RemoteContentMediaObjectUploader(
      client: _FailingStreamClient(),
      uploadBaseUrl: 'https://upload.example.test',
    );

    await expectLater(
      uploader.stream(
        Uri.parse('https://upload.example.test/unreachable'),
        Stream<List<int>>.value(const <int>[6]),
        contentLength: 1,
        contentType: 'image/jpeg',
        expectedSha256: digest,
      ),
      throwsA(
        isA<ContentMediaObjectUploadException>()
            .having((error) => error.statusCode, 'statusCode', isNull)
            .having(
              (error) => error.code,
              'canonical code',
              ContentErrorCode.storageWriteFailed.code,
            ),
      ),
    );
  });

  test(
    'rejects a presigned URL outside the governed upload authority',
    () async {
      final client = _RecordingStreamClient();
      final uploader = RemoteContentMediaObjectUploader(
        client: client,
        uploadBaseUrl: 'https://upload.example.test',
      );

      await expectLater(
        uploader.stream(
          Uri.parse('https://attacker.example.invalid/object'),
          Stream<List<int>>.value(const <int>[7]),
          contentLength: 1,
          contentType: 'image/jpeg',
          expectedSha256: digest,
        ),
        throwsA(
          isA<ContentMediaObjectUploadException>().having(
            (error) => error.retryable,
            'retryable',
            isFalse,
          ),
        ),
      );
      expect(client.request, isNull);
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

final class _FailingStreamClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    await request.finalize().drain<void>();
    throw http.ClientException('object storage unreachable', request.url);
  }
}
