import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/retry_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';

/// Callback for API latency instrumentation.
///
/// Invoked after every HTTP request completes (success or failure).
/// [method] is the HTTP verb (GET, POST, etc.), [path] is the request path,
/// [elapsedMs] is the round-trip time in milliseconds, [statusCode] is the
/// HTTP status code (-1 on network/timeout errors).
typedef ApiLatencyObserver = void Function(
  String method,
  String path,
  int elapsedMs,
  int statusCode,
);

class CloudHttpClient {
  CloudHttpClient({
    http.Client? client,
    CloudAuthTokenProvider? authTokenProvider,
    Duration? timeout,
    ApiLatencyObserver? latencyObserver,
  }) : _client = client ?? RetryHttpClient(),
       _authTokenProvider =
           authTokenProvider ?? const StubCloudAuthTokenProvider(),
       _timeout = timeout ?? const Duration(seconds: 12),
       _latencyObserver = latencyObserver;

  final http.Client _client;
  final CloudAuthTokenProvider _authTokenProvider;
  final Duration _timeout;
  final ApiLatencyObserver? _latencyObserver;

  // ── http.Client 兼容底层 API（不自动根据状态码抛错；见 [getJson]/[postJson]）────────

  /// 返回原始 [http.Response]，**不会**因非 2xx 抛 [CloudException]。
  Future<http.Response> get(
    Uri url, {
    Map<String, String>? headers,
  }) async {
    final merged = await _mergeHeaders(headers ?? const {});
    return _guardRequest(
      () => _client.get(url, headers: merged).timeout(_timeout),
      requestPath: url.path,
      method: 'GET',
    );
  }

  Future<http.Response> post(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    final merged = await _mergeHeaders(headers ?? const {});
    return _guardRequest(
      () => _client
          .post(url, headers: merged, body: body, encoding: encoding)
          .timeout(_timeout),
      requestPath: url.path,
      method: 'POST',
    );
  }

  Future<http.Response> patch(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    final merged = await _mergeHeaders(headers ?? const {});
    return _guardRequest(
      () => _client
          .patch(url, headers: merged, body: body, encoding: encoding)
          .timeout(_timeout),
      requestPath: url.path,
      method: 'PATCH',
    );
  }

  Future<http.Response> put(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    final merged = await _mergeHeaders(headers ?? const {});
    return _guardRequest(
      () => _client
          .put(url, headers: merged, body: body, encoding: encoding)
          .timeout(_timeout),
      requestPath: url.path,
      method: 'PUT',
    );
  }

  Future<http.Response> delete(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    final merged = await _mergeHeaders(headers ?? const {});
    return _guardRequest(
      () => _client
          .delete(url, headers: merged, body: body, encoding: encoding)
          .timeout(_timeout),
      requestPath: url.path,
      method: 'DELETE',
    );
  }

  /// 与 [http.Client.send] 一致；在发送前合并鉴权头（及 [TimeoutException] 映射）。
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final sw = Stopwatch()..start();
    try {
      final merged = await _mergeHeaders(
        Map<String, String>.from(request.headers),
      );
      request.headers
        ..clear()
        ..addAll(merged);
      final response = await _client.send(request).timeout(_timeout);
      sw.stop();
      _latencyObserver?.call(
        request.method,
        request.url.path,
        sw.elapsedMilliseconds,
        response.statusCode,
      );
      return response;
    } on TimeoutException catch (e) {
      sw.stop();
      _latencyObserver?.call(
        request.method,
        request.url.path,
        sw.elapsedMilliseconds,
        -1,
      );
      throw CloudErrorMapper.fromException(
        e,
        requestPath: request.url.path,
      );
    } on SocketException catch (e) {
      sw.stop();
      _latencyObserver?.call(
        request.method,
        request.url.path,
        sw.elapsedMilliseconds,
        -1,
      );
      throw CloudErrorMapper.fromException(
        e,
        requestPath: request.url.path,
      );
    } catch (e) {
      sw.stop();
      _latencyObserver?.call(
        request.method,
        request.url.path,
        sw.elapsedMilliseconds,
        -1,
      );
      if (e is CloudException) rethrow;
      throw CloudErrorMapper.fromException(
        e,
        requestPath: request.url.path,
      );
    }
  }

  /// JSON 解码结果可能是 `Map`、`List`、标量或 `null`；返回 [CloudHttpDecodedJson]（即 [Object?]）。
  Future<CloudHttpDecodedJson> getJson(
    Uri uri, {
    required Map<String, String> headers,
  }) async {
    final merged = await _mergeHeaders(headers);
    final res = await _guardRequest(
      () => _client.get(uri, headers: merged).timeout(_timeout),
      requestPath: uri.path,
      method: 'GET',
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  /// 见 [getJson]：响应体同样经 [jsonDecode]。
  Future<CloudHttpDecodedJson> postJson(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
  }) async {
    final merged = await _mergeHeaders(headers);
    final payload = jsonEncode(body);
    final requestHeaders = <String, String>{
      ...merged,
      'Content-Type': 'application/json',
    };
    final res = await _guardRequest(
      () => _client
          .post(uri, headers: requestHeaders, body: payload)
          .timeout(_timeout),
      requestPath: uri.path,
      method: 'POST',
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  Future<CloudHttpDecodedJson> patchJson(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
  }) async {
    final merged = await _mergeHeaders(headers);
    final payload = jsonEncode(body);
    final requestHeaders = <String, String>{
      ...merged,
      'Content-Type': 'application/json',
    };
    final res = await _guardRequest(
      () => _client
          .patch(uri, headers: requestHeaders, body: payload)
          .timeout(_timeout),
      requestPath: uri.path,
      method: 'PATCH',
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  Future<CloudHttpDecodedJson> putJson(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
  }) async {
    final merged = await _mergeHeaders(headers);
    final payload = jsonEncode(body);
    final requestHeaders = <String, String>{
      ...merged,
      'Content-Type': 'application/json',
    };
    final res = await _guardRequest(
      () => _client
          .put(uri, headers: requestHeaders, body: payload)
          .timeout(_timeout),
      requestPath: uri.path,
      method: 'PUT',
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  /// Low-level POST with raw byte body. Used for gzip-compressed payloads
  /// where JSON encoding is done by the caller.
  Future<http.Response> postBytes(
    Uri uri, {
    required Map<String, String> headers,
    required List<int> body,
  }) async {
    final merged = await _mergeHeaders(headers);
    return _guardRequest(
      () => _client.post(uri, headers: merged, body: body).timeout(_timeout),
      requestPath: uri.path,
      method: 'POST',
    );
  }

  Future<CloudHttpDecodedJson> deleteJson(
    Uri uri, {
    required Map<String, String> headers,
  }) async {
    final merged = await _mergeHeaders(headers);
    final res = await _guardRequest(
      () => _client.delete(uri, headers: merged).timeout(_timeout),
      requestPath: uri.path,
      method: 'DELETE',
    );
    _guardStatus(res, uri.path);
    if (res.body.isEmpty) return const <String, dynamic>{};
    return _decodeBody(res.body, uri.path);
  }

  /// [getJson] 后立即 [CloudResponseDecoder.asObject]，供需要根对象为 Map 的调用方使用。
  Future<CloudJsonMap> getJsonObject(
    Uri uri, {
    required Map<String, String> headers,
    required String context,
  }) async {
    final decoded = await getJson(uri, headers: headers);
    return CloudResponseDecoder.asObject(decoded, context: context);
  }

  /// 根为 JSON 数组，或根为对象且列表落在 `listKeys` 之一（与 [CloudResponseDecoder.mapListFirstNonEmpty] 一致）。
  Future<List<CloudJsonMap>> getJsonItemList(
    Uri uri, {
    required Map<String, String> headers,
    required String context,
    List<String> listKeys = const <String>['items', 'subAccounts', 'personas'],
  }) async {
    final decoded = await getJson(uri, headers: headers);
    if (decoded is List) {
      return decoded
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    }
    final object = CloudResponseDecoder.asObject(decoded, context: context);
    return CloudResponseDecoder.mapListFirstNonEmpty(object, listKeys);
  }

  /// [postJson] 后立即 [CloudResponseDecoder.asObject]。
  Future<CloudJsonMap> postJsonObject(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
    required String context,
  }) async {
    final decoded = await postJson(uri, headers: headers, body: body);
    return CloudResponseDecoder.asObject(decoded, context: context);
  }

  /// [patchJson] 后立即 [CloudResponseDecoder.asObject]。
  Future<CloudJsonMap> patchJsonObject(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
    required String context,
  }) async {
    final decoded = await patchJson(uri, headers: headers, body: body);
    return CloudResponseDecoder.asObject(decoded, context: context);
  }

  Future<Map<String, String>> _mergeHeaders(Map<String, String> headers) async {
    final token = await _authTokenProvider.getAccessToken();
    if (token == null || token.isEmpty) return headers;
    return <String, String>{...headers, 'Authorization': 'Bearer $token'};
  }

  Future<http.Response> _guardRequest(
    Future<http.Response> Function() run, {
    required String requestPath,
    String method = 'GET',
  }) async {
    final sw = Stopwatch()..start();
    try {
      final response = await run();
      sw.stop();
      _latencyObserver?.call(
        method,
        requestPath,
        sw.elapsedMilliseconds,
        response.statusCode,
      );
      return response;
    } on TimeoutException catch (e) {
      sw.stop();
      _latencyObserver?.call(method, requestPath, sw.elapsedMilliseconds, -1);
      throw CloudErrorMapper.fromException(e, requestPath: requestPath);
    } on SocketException catch (e) {
      sw.stop();
      _latencyObserver?.call(method, requestPath, sw.elapsedMilliseconds, -1);
      throw CloudErrorMapper.fromException(e, requestPath: requestPath);
    } catch (e) {
      sw.stop();
      _latencyObserver?.call(method, requestPath, sw.elapsedMilliseconds, -1);
      if (e is CloudException) rethrow;
      throw CloudErrorMapper.fromException(e, requestPath: requestPath);
    }
  }

  void _guardStatus(http.Response res, String path) {
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw CloudErrorMapper.fromStatusCode(
      res.statusCode,
      body: res.body,
      requestPath: path,
    );
  }

  CloudHttpDecodedJson _decodeBody(String body, String path) {
    if (body.isEmpty) return const <String, dynamic>{};
    try {
      return jsonDecode(body) as Object?;
    } catch (e) {
      throw CloudErrorMapper.fromException(e, requestPath: path);
    }
  }
}
