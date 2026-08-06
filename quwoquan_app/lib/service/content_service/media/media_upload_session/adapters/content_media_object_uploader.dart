import 'package:http/http.dart' as http;
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/transport/links/trusted_endpoint_policy.dart';
import 'package:quwoquan_app/runtime/platform/content_addressed_upload_headers.dart';

/// Object-storage data-plane adapter. Authentication headers are intentionally
/// absent because authorization is carried only by the server-issued URL.
final class RemoteContentMediaObjectUploader {
  RemoteContentMediaObjectUploader({http.Client? client, String? uploadBaseUrl})
    : _uploadBaseUri = Uri.tryParse(
        uploadBaseUrl ?? CloudRuntimeConfig.mediaUploadBaseUrl,
      ),
      _client = client ?? http.Client(),
      _ownsClient = client == null;

  final http.Client _client;
  final bool _ownsClient;
  final Uri? _uploadBaseUri;

  ContentMediaStreamObjectUpload get uploadStream => stream;

  Future<void> stream(
    Uri uploadUri,
    Stream<List<int>> bytes, {
    required int contentLength,
    required String mimeType,
    required String expectedSha256,
    Future<void>? abortTrigger,
  }) async {
    if (_uploadBaseUri == null ||
        !isUriWithinTrustedHttpsBase(uploadUri, _uploadBaseUri)) {
      throw ContentMediaObjectUploadException(
        retryable: false,
        cause: FormatException('upload URL is outside MEDIA_UPLOAD_BASE_URL'),
      );
    }
    final uploadHeaders = ContentAddressedUploadHeaders(
      mimeType: mimeType,
      expectedSha256: expectedSha256,
    );
    final request =
        http.AbortableStreamedRequest(
            'PUT',
            uploadUri,
            abortTrigger: abortTrigger,
          )
          ..headers.addAll(uploadHeaders.toHttpHeaders())
          ..contentLength = contentLength;
    try {
      final responseFuture = _client
          .send(request)
          .then<(http.StreamedResponse?, Object?, StackTrace?)>(
            (response) => (response, null, null),
            onError: (Object error, StackTrace stackTrace) =>
                (null, error, stackTrace),
          );
      await request.sink.addStream(bytes);
      await request.sink.close();
      final (response, transportError, transportStackTrace) =
          await responseFuture;
      if (transportError != null) {
        Error.throwWithStackTrace(transportError, transportStackTrace!);
      }
      if (response == null) {
        throw StateError('object storage returned no response or error');
      }
      await response.stream.drain<void>();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ContentMediaObjectUploadException(
          retryable: _isRetryableStatus(response.statusCode),
          statusCode: response.statusCode,
        );
      }
    } on ContentMediaUploadCancelledException {
      rethrow;
    } on ContentMediaObjectUploadException {
      rethrow;
    } on http.RequestAbortedException {
      throw const ContentMediaUploadCancelledException();
    } catch (error) {
      throw ContentMediaObjectUploadException(retryable: true, cause: error);
    }
  }

  void dispose() {
    if (_ownsClient) _client.close();
  }
}

bool _isRetryableStatus(int statusCode) =>
    statusCode == 408 ||
    statusCode == 425 ||
    statusCode == 429 ||
    statusCode >= 500;
