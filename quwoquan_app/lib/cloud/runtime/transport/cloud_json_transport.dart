import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

final class CloudJsonTransportRequest {
  const CloudJsonTransportRequest({
    required this.method,
    required this.authMode,
    required this.uri,
    required this.gatewayOrigin,
    required this.headers,
    required this.abortTrigger,
    this.body,
  });

  final String method;
  final String authMode;
  final Uri uri;
  final Uri gatewayOrigin;
  final Map<String, String> headers;
  final Future<void> abortTrigger;
  final CloudJsonMap? body;
}

abstract interface class CloudJsonTransport {
  Future<Object?> send(CloudJsonTransportRequest request);
  Future<bool> refreshAuthorization({required Future<void> abortTrigger});
}

final class HttpCloudJsonTransport implements CloudJsonTransport {
  const HttpCloudJsonTransport(this._client);

  final CloudHttpClient _client;

  @override
  Future<Object?> send(CloudJsonTransportRequest request) async {
    final requireAuth = switch (request.authMode) {
      'required' => true,
      'optional' || 'public' => false,
      final mode => throw CloudErrorMapper.invalidResponse(
        message: 'Unsupported Cloud auth mode: $mode',
        requestPath: request.uri.path,
        functionModule: 'cloud_json_transport',
      ),
    };
    final method = request.method.toUpperCase();
    if (!const <String>{
      'GET',
      'POST',
      'PATCH',
      'PUT',
      'DELETE',
    }.contains(method)) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Unsupported Cloud operation method: $method',
        requestPath: request.uri.path,
        functionModule: 'cloud_json_transport',
      );
    }
    return await _client.sendOperationJson(
      method: method,
      uri: request.uri,
      gatewayOrigin: request.gatewayOrigin,
      headers: request.headers,
      requireAuth: requireAuth,
      abortTrigger: request.abortTrigger,
      body: request.body,
    );
  }

  @override
  Future<bool> refreshAuthorization({required Future<void> abortTrigger}) {
    return _client.refreshOperationAuthorization(abortTrigger: abortTrigger);
  }
}
