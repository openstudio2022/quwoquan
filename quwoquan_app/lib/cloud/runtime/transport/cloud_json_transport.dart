import 'dart:convert';

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
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
    this.maximumResponseBodyBytes,
  });

  final String method;
  final String authMode;
  final Uri uri;
  final Uri gatewayOrigin;
  final Map<String, String> headers;
  final Future<void> abortTrigger;
  final CloudJsonMap? body;
  final int? maximumResponseBodyBytes;
}

abstract interface class CloudJsonTransport {
  Future<Object?> send(CloudJsonTransportRequest request);
  Future<bool> refreshAuthorization({required Future<void> abortTrigger});
}

abstract interface class CloudEventStreamTransport {
  Stream<CloudEventStreamFrame> stream(CloudJsonTransportRequest request);
}

/// One decoded SSE frame. [eventId] is the protocol-level `id:` identity;
/// [data] remains the untouched canonical business wire passed to its decoder.
final class CloudEventStreamFrame {
  const CloudEventStreamFrame({required this.eventId, required this.data});

  final String eventId;
  final Object? data;
}

final class HttpCloudJsonTransport
    implements CloudJsonTransport, CloudEventStreamTransport {
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
      maximumResponseBodyBytes: request.maximumResponseBodyBytes,
    );
  }

  @override
  Future<bool> refreshAuthorization({required Future<void> abortTrigger}) {
    return _client.refreshOperationAuthorization(abortTrigger: abortTrigger);
  }

  @override
  Stream<CloudEventStreamFrame> stream(
    CloudJsonTransportRequest request,
  ) async* {
    final maximumEventFrameBytes = request.maximumResponseBodyBytes;
    if (maximumEventFrameBytes == null || maximumEventFrameBytes < 1024) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Generated SSE operation requires a canonical frame budget',
        requestPath: request.uri.path,
        functionModule: 'cloud_json_transport',
      );
    }
    if (request.body != null) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Generated SSE operation cannot carry a request body',
        requestPath: request.uri.path,
        functionModule: 'cloud_json_transport',
      );
    }
    final requireAuth = switch (request.authMode) {
      'required' => true,
      'optional' || 'public' => false,
      final mode => throw CloudErrorMapper.invalidResponse(
        message: 'Unsupported Cloud auth mode: $mode',
        requestPath: request.uri.path,
        functionModule: 'cloud_json_transport',
      ),
    };
    final response = await _client.openOperationEventStream(
      method: request.method,
      uri: request.uri,
      gatewayOrigin: request.gatewayOrigin,
      headers: request.headers,
      requireAuth: requireAuth,
      abortTrigger: request.abortTrigger,
      maximumEventFrameBytes: maximumEventFrameBytes,
    );
    var buffer = <int>[];
    await for (final chunk in response.stream) {
      buffer.addAll(chunk);
      var boundary = _nextSseFrameBoundary(buffer);
      while (boundary != null) {
        final frameBytes = buffer.sublist(0, boundary.index);
        buffer = buffer.sublist(boundary.index + boundary.delimiterLength);
        if (frameBytes.length > maximumEventFrameBytes) {
          throw _eventFrameTooLarge(request.uri.path);
        }
        final decoded = _decodeSseFrame(frameBytes);
        if (decoded != null) yield decoded;
        boundary = _nextSseFrameBoundary(buffer);
      }
      if (buffer.length > maximumEventFrameBytes) {
        throw _eventFrameTooLarge(request.uri.path);
      }
    }
    if (buffer.isNotEmpty) {
      final decoded = _decodeSseFrame(buffer);
      if (decoded != null) yield decoded;
    }
  }
}

final class _SseFrameBoundary {
  const _SseFrameBoundary(this.index, this.delimiterLength);

  final int index;
  final int delimiterLength;
}

_SseFrameBoundary? _nextSseFrameBoundary(List<int> bytes) {
  for (var index = 0; index < bytes.length - 1; index++) {
    if (bytes[index] == 10 && bytes[index + 1] == 10) {
      return _SseFrameBoundary(index, 2);
    }
    if (index < bytes.length - 3 &&
        bytes[index] == 13 &&
        bytes[index + 1] == 10 &&
        bytes[index + 2] == 13 &&
        bytes[index + 3] == 10) {
      return _SseFrameBoundary(index, 4);
    }
  }
  return null;
}

CloudEventStreamFrame? _decodeSseFrame(List<int> bytes) {
  final frame = utf8.decode(bytes).replaceAll('\r\n', '\n');
  final dataLines = <String>[];
  var eventId = '';
  for (final line in frame.split('\n')) {
    if (line.startsWith('id:')) {
      eventId = line.substring(3).trim();
      continue;
    }
    if (line == 'data') {
      dataLines.add('');
      continue;
    }
    if (!line.startsWith('data:')) continue;
    var value = line.substring(5);
    if (value.startsWith(' ')) value = value.substring(1);
    dataLines.add(value);
  }
  if (dataLines.isEmpty) {
    return null;
  }
  return CloudEventStreamFrame(
    eventId: eventId,
    data: jsonDecode(dataLines.join('\n')),
  );
}

CloudException _eventFrameTooLarge(String path) {
  return CloudErrorMapper.invalidResponse(
    message: 'Generated SSE event frame exceeds the canonical byte budget',
    requestPath: path,
    functionModule: 'cloud_json_transport',
  );
}
