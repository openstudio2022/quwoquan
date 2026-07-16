import 'package:http/http.dart' as http;
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/platform/content_addressed_upload_headers.dart';

/// Object-storage data-plane adapter. Authentication headers are intentionally
/// absent because authorization is carried only by the server-issued URL.
final class RemoteContentMediaObjectUploader {
  RemoteContentMediaObjectUploader({http.Client? client})
    : _client = client ?? http.Client(),
      _ownsClient = client == null;

  final http.Client _client;
  final bool _ownsClient;

  ContentMediaObjectUpload get upload => call;
  ContentMediaStreamObjectUpload get uploadStream => stream;

  Future<void> call(
    Uri uploadUri,
    List<int> bytes, {
    required String contentType,
    required String expectedSha256,
  }) async {
    final uploadHeaders = ContentAddressedUploadHeaders(
      contentType: contentType,
      expectedSha256: expectedSha256,
    );
    final response = await _client.put(
      uploadUri,
      headers: uploadHeaders.toHttpHeaders(),
      body: bytes,
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('media object upload failed: ${response.statusCode}');
    }
  }

  Future<void> stream(
    Uri uploadUri,
    Stream<List<int>> bytes, {
    required int contentLength,
    required String contentType,
    required String expectedSha256,
  }) async {
    final uploadHeaders = ContentAddressedUploadHeaders(
      contentType: contentType,
      expectedSha256: expectedSha256,
    );
    final request = http.StreamedRequest('PUT', uploadUri)
      ..headers.addAll(uploadHeaders.toHttpHeaders())
      ..contentLength = contentLength;
    final responseFuture = _client.send(request);
    await request.sink.addStream(bytes);
    await request.sink.close();
    final response = await responseFuture;
    await response.stream.drain<void>();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('media object upload failed: ${response.statusCode}');
    }
  }

  void dispose() {
    if (_ownsClient) _client.close();
  }
}
