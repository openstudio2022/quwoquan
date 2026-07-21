import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/retry_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Callback for API latency instrumentation.
///
/// Invoked after every HTTP request completes (success or failure).
/// [method] is the HTTP verb (GET, POST, etc.), [path] is the request path,
/// [elapsedMs] is the round-trip time in milliseconds, [statusCode] is the
/// HTTP status code (-1 on network/timeout errors).
typedef ApiLatencyObserver =
    void Function(String method, String path, int elapsedMs, int statusCode);

typedef CloudUnauthorizedRefresh =
    Future<bool> Function(Future<void> abortTrigger);

final Future<void> _neverAbort = Completer<void>().future;

class CloudHttpClient {
  CloudHttpClient({
    http.Client? client,
    CloudAuthTokenProvider? authTokenProvider,
    this._onUnauthorizedRefresh,
    Duration? timeout,
    this._latencyObserver,
  }) : _client = client ?? RetryHttpClient(),
       _authTokenProvider =
           authTokenProvider ?? const StubCloudAuthTokenProvider(),
       _timeout = timeout ?? const Duration(seconds: 12);

  final http.Client _client;
  final CloudAuthTokenProvider _authTokenProvider;
  final CloudUnauthorizedRefresh? _onUnauthorizedRefresh;
  final Duration _timeout;
  final ApiLatencyObserver? _latencyObserver;

  /// Executes exactly one generated-operation network attempt.
  ///
  /// Retry, deadline and cancellation ownership stays in
  /// [AppGeneratedCloudOperationExecutor]. This method deliberately bypasses
  /// [RetryHttpClient.send].
  Future<CloudHttpDecodedJson> sendOperationJson({
    required String method,
    required Uri uri,
    required Uri gatewayOrigin,
    required Map<String, String> headers,
    required bool requireAuth,
    required Future<void> abortTrigger,
    CloudJsonMap? body,
  }) async {
    if (!_sameOrigin(uri, gatewayOrigin)) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Generated Cloud operation must target the Gateway origin',
        requestPath: uri.path,
        functionModule: 'cloud_http_client',
      );
    }
    final stopwatch = Stopwatch()..start();
    var latencyRecorded = false;
    final request = http.AbortableRequest(
      method.toUpperCase(),
      uri,
      abortTrigger: abortTrigger,
    );
    try {
      request.headers.addAll(
        await _completeBeforeAbort(
          _mergeHeaders(
            headers,
            requireAuth: requireAuth,
            requestPath: uri.path,
            abortTrigger: abortTrigger,
          ),
          abortTrigger: abortTrigger,
          requestPath: uri.path,
        ),
      );
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);
      }
      final streamed = await _sendSingleAttempt(request);
      final response = await http.Response.fromStream(streamed);
      stopwatch.stop();
      _latencyObserver?.call(
        request.method,
        uri.path,
        stopwatch.elapsedMilliseconds,
        response.statusCode,
      );
      latencyRecorded = true;
      _guardStatus(response, uri.path);
      return _decodeBody(response.body, uri.path);
    } catch (error) {
      stopwatch.stop();
      if (!latencyRecorded) {
        _latencyObserver?.call(
          request.method,
          uri.path,
          stopwatch.elapsedMilliseconds,
          error is CloudException ? error.statusCode ?? -1 : -1,
        );
      }
      rethrow;
    }
  }

  Future<bool> refreshOperationAuthorization({
    required Future<void> abortTrigger,
  }) {
    return _completeBeforeAbort(
      _attemptUnauthorizedRefresh(abortTrigger: abortTrigger),
      abortTrigger: abortTrigger,
      requestPath: '/auth/refresh',
    );
  }

  // ── http.Client 兼容底层 API（不自动根据状态码抛错；见 [getJson]/[postJson]）────────

  /// 返回原始 [http.Response]，**不会**因非 2xx 抛 [CloudException]。
  Future<http.Response> get(Uri url, {Map<String, String>? headers}) async {
    return _requestWithRefreshRetry(
      requestPath: url.path,
      method: 'GET',
      headers: headers ?? const <String, String>{},
      shouldAttemptRefresh: true,
      run: (mergedHeaders) => _guardRequest(
        () => _client.get(url, headers: mergedHeaders).timeout(_timeout),
        requestPath: url.path,
        method: 'GET',
      ),
    );
  }

  Future<http.Response> post(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    return _requestWithRefreshRetry(
      requestPath: url.path,
      method: 'POST',
      headers: headers ?? const <String, String>{},
      shouldAttemptRefresh: true,
      run: (mergedHeaders) => _guardRequest(
        () => _client
            .post(url, headers: mergedHeaders, body: body, encoding: encoding)
            .timeout(_timeout),
        requestPath: url.path,
        method: 'POST',
      ),
    );
  }

  Future<http.Response> patch(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    return _requestWithRefreshRetry(
      requestPath: url.path,
      method: 'PATCH',
      headers: headers ?? const <String, String>{},
      shouldAttemptRefresh: true,
      run: (mergedHeaders) => _guardRequest(
        () => _client
            .patch(url, headers: mergedHeaders, body: body, encoding: encoding)
            .timeout(_timeout),
        requestPath: url.path,
        method: 'PATCH',
      ),
    );
  }

  Future<http.Response> put(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    return _requestWithRefreshRetry(
      requestPath: url.path,
      method: 'PUT',
      headers: headers ?? const <String, String>{},
      shouldAttemptRefresh: true,
      run: (mergedHeaders) => _guardRequest(
        () => _client
            .put(url, headers: mergedHeaders, body: body, encoding: encoding)
            .timeout(_timeout),
        requestPath: url.path,
        method: 'PUT',
      ),
    );
  }

  Future<http.Response> delete(
    Uri url, {
    Map<String, String>? headers,
    Object? body,
    Encoding? encoding,
  }) async {
    return _requestWithRefreshRetry(
      requestPath: url.path,
      method: 'DELETE',
      headers: headers ?? const <String, String>{},
      shouldAttemptRefresh: true,
      run: (mergedHeaders) => _guardRequest(
        () => _client
            .delete(url, headers: mergedHeaders, body: body, encoding: encoding)
            .timeout(_timeout),
        requestPath: url.path,
        method: 'DELETE',
      ),
    );
  }

  /// 与 [http.Client.send] 一致；在发送前合并鉴权头（及 [TimeoutException] 映射）。
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final sw = Stopwatch()..start();
    try {
      final merged = await _mergeHeaders(
        Map<String, String>.from(request.headers),
        requireAuth: false,
        requestPath: request.url.path,
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
      throw CloudErrorMapper.fromException(e, requestPath: request.url.path);
    } catch (e) {
      sw.stop();
      _latencyObserver?.call(
        request.method,
        request.url.path,
        sw.elapsedMilliseconds,
        -1,
      );
      if (e is CloudException) rethrow;
      throw CloudErrorMapper.fromException(e, requestPath: request.url.path);
    }
  }

  /// JSON 解码结果可能是 `Map`、`List`、标量或 `null`；返回 [CloudHttpDecodedJson]（即 [Object?]）。
  Future<CloudHttpDecodedJson> getJson(
    Uri uri, {
    required Map<String, String> headers,
    bool requireAuth = false,
  }) async {
    final res = await _requestWithRefreshRetry(
      requestPath: uri.path,
      method: 'GET',
      headers: headers,
      shouldAttemptRefresh: true,
      requireAuth: requireAuth,
      run: (mergedHeaders) => _guardRequest(
        () => _client.get(uri, headers: mergedHeaders).timeout(_timeout),
        requestPath: uri.path,
        method: 'GET',
      ),
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  /// 供仍在迁入 generated executor 的可见读取使用真实 transport abort。
  ///
  /// 新调用链应优先使用 generated operation executor；此入口只为当前已经存在、
  /// 但尚无 typed client contract 的 canonical operation 提供取消能力。
  Future<CloudHttpDecodedJson> getJsonAbortable(
    Uri uri, {
    required Uri gatewayOrigin,
    required Map<String, String> headers,
    required CloudOperationCancellationSignal cancellation,
    bool requireAuth = false,
  }) async {
    try {
      return await sendOperationJson(
        method: 'GET',
        uri: uri,
        gatewayOrigin: gatewayOrigin,
        headers: headers,
        requireAuth: requireAuth,
        abortTrigger: cancellation.whenCancelled,
      );
    } on http.RequestAbortedException catch (_) {
      throw CloudErrorMapper.fromException(
        const CloudOperationCancelledException(),
        requestPath: uri.path,
      );
    }
  }

  /// 见 [getJson]：响应体同样经 [jsonDecode]。
  Future<CloudHttpDecodedJson> postJson(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
    bool requireAuth = false,
  }) async {
    final payload = jsonEncode(body);
    final res = await _requestWithRefreshRetry(
      requestPath: uri.path,
      method: 'POST',
      headers: headers,
      shouldAttemptRefresh: true,
      requireAuth: requireAuth,
      run: (mergedHeaders) {
        final requestHeaders = <String, String>{
          ...mergedHeaders,
          'Content-Type': 'application/json',
        };
        return _guardRequest(
          () => _client
              .post(uri, headers: requestHeaders, body: payload)
              .timeout(_timeout),
          requestPath: uri.path,
          method: 'POST',
        );
      },
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  Future<CloudHttpDecodedJson> patchJson(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
    bool requireAuth = false,
  }) async {
    final payload = jsonEncode(body);
    final res = await _requestWithRefreshRetry(
      requestPath: uri.path,
      method: 'PATCH',
      headers: headers,
      shouldAttemptRefresh: true,
      requireAuth: requireAuth,
      run: (mergedHeaders) {
        final requestHeaders = <String, String>{
          ...mergedHeaders,
          'Content-Type': 'application/json',
        };
        return _guardRequest(
          () => _client
              .patch(uri, headers: requestHeaders, body: payload)
              .timeout(_timeout),
          requestPath: uri.path,
          method: 'PATCH',
        );
      },
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  Future<CloudHttpDecodedJson> putJson(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
    bool requireAuth = false,
  }) async {
    final payload = jsonEncode(body);
    final res = await _requestWithRefreshRetry(
      requestPath: uri.path,
      method: 'PUT',
      headers: headers,
      shouldAttemptRefresh: true,
      requireAuth: requireAuth,
      run: (mergedHeaders) {
        final requestHeaders = <String, String>{
          ...mergedHeaders,
          'Content-Type': 'application/json',
        };
        return _guardRequest(
          () => _client
              .put(uri, headers: requestHeaders, body: payload)
              .timeout(_timeout),
          requestPath: uri.path,
          method: 'PUT',
        );
      },
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
    return _requestWithRefreshRetry(
      requestPath: uri.path,
      method: 'POST',
      headers: headers,
      shouldAttemptRefresh: true,
      run: (mergedHeaders) => _guardRequest(
        () => _client
            .post(uri, headers: mergedHeaders, body: body)
            .timeout(_timeout),
        requestPath: uri.path,
        method: 'POST',
      ),
    );
  }

  Future<CloudHttpDecodedJson> deleteJson(
    Uri uri, {
    required Map<String, String> headers,
    CloudJsonMap? body,
    bool requireAuth = false,
  }) async {
    final payload = body == null ? null : jsonEncode(body);
    final res = await _requestWithRefreshRetry(
      requestPath: uri.path,
      method: 'DELETE',
      headers: headers,
      shouldAttemptRefresh: true,
      requireAuth: requireAuth,
      run: (mergedHeaders) {
        final requestHeaders = body == null
            ? mergedHeaders
            : <String, String>{
                ...mergedHeaders,
                'Content-Type': 'application/json',
              };
        return _guardRequest(
          () => _client
              .delete(uri, headers: requestHeaders, body: payload)
              .timeout(_timeout),
          requestPath: uri.path,
          method: 'DELETE',
        );
      },
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

  /// 根为 JSON 数组，或根为对象且列表落在单一 canonical `listKey`（默认 `items`）。
  Future<List<CloudJsonMap>> getJsonItemList(
    Uri uri, {
    required Map<String, String> headers,
    required String context,
    String listKey = 'items',
  }) async {
    final decoded = await getJson(uri, headers: headers);
    if (decoded is List) {
      return decoded
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    }
    final object = CloudResponseDecoder.asObject(decoded, context: context);
    return CloudResponseDecoder.mapList(object, listKey, context: context);
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

  Future<CloudJsonMap> postJsonObjectAbortable(
    Uri uri, {
    required Uri gatewayOrigin,
    required Map<String, String> headers,
    required CloudJsonMap body,
    required String context,
    required CloudOperationCancellationSignal cancellation,
    bool requireAuth = false,
  }) async {
    try {
      final decoded = await sendOperationJson(
        method: 'POST',
        uri: uri,
        gatewayOrigin: gatewayOrigin,
        headers: headers,
        requireAuth: requireAuth,
        abortTrigger: cancellation.whenCancelled,
        body: body,
      );
      return CloudResponseDecoder.asObject(decoded, context: context);
    } on http.RequestAbortedException catch (_) {
      throw CloudErrorMapper.fromException(
        const CloudOperationCancelledException(),
        requestPath: uri.path,
      );
    }
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

  Future<Map<String, String>> _mergeHeaders(
    Map<String, String> headers, {
    required bool requireAuth,
    required String requestPath,
    Future<void>? abortTrigger,
  }) async {
    final sanitizedHeaders = Map<String, String>.from(headers)
      ..removeWhere((key, _) => key.toLowerCase() == 'authorization');
    var token = await _authTokenProvider.getAccessToken();
    if ((token == null || token.isEmpty) && requireAuth) {
      final refreshed = await _attemptUnauthorizedRefresh(
        abortTrigger: abortTrigger,
      );
      if (refreshed) {
        token = await _authTokenProvider.getAccessToken();
      }
      if (token == null || token.isEmpty) {
        throw CloudErrorMapper.fromStatusCode(401, requestPath: requestPath);
      }
    }
    if (token == null || token.isEmpty) return sanitizedHeaders;
    return <String, String>{
      ...sanitizedHeaders,
      'Authorization': 'Bearer $token',
    };
  }

  Future<http.Response> _requestWithRefreshRetry({
    required String requestPath,
    required String method,
    required Map<String, String> headers,
    required bool shouldAttemptRefresh,
    bool requireAuth = false,
    required Future<http.Response> Function(Map<String, String> mergedHeaders)
    run,
  }) async {
    final initialHeaders = await _mergeHeaders(
      headers,
      requireAuth: requireAuth,
      requestPath: requestPath,
    );
    final first = await run(initialHeaders);
    if (!_shouldRefreshAfterResponse(
      response: first,
      requestPath: requestPath,
      method: method,
      shouldAttemptRefresh: shouldAttemptRefresh,
    )) {
      return first;
    }
    final refreshed = await _attemptUnauthorizedRefresh();
    if (!refreshed) {
      return first;
    }
    final retryHeaders = await _mergeHeaders(
      headers,
      requireAuth: requireAuth,
      requestPath: requestPath,
    );
    return run(retryHeaders);
  }

  bool _shouldRefreshAfterResponse({
    required http.Response response,
    required String requestPath,
    required String method,
    required bool shouldAttemptRefresh,
  }) {
    if (!shouldAttemptRefresh) {
      return false;
    }
    // account_suspended 与 stale authEpoch 都可能在已认证请求上以 403 返回。
    // 仍只刷新一次：正常权限不足会保留原始 403；若 refresh 发现账号限制，
    // AuthSessionController 会清凭证并切入结构化受限落点。
    if (response.statusCode != 401 && response.statusCode != 403) {
      return false;
    }
    if (requestPath.endsWith('/auth/token/refresh')) {
      return false;
    }
    return method != 'AUTH_REFRESH';
  }

  Future<bool> _attemptUnauthorizedRefresh({Future<void>? abortTrigger}) async {
    final refresh = _onUnauthorizedRefresh;
    if (refresh == null) {
      return false;
    }
    return refresh(abortTrigger ?? _neverAbort);
  }

  Future<http.StreamedResponse> _sendSingleAttempt(http.BaseRequest request) {
    final client = _client;
    if (client is RetryHttpClient) {
      return client.sendSingleAttempt(request);
    }
    return client.send(request);
  }

  Future<T> _completeBeforeAbort<T>(
    Future<T> operation, {
    required Future<void> abortTrigger,
    required String requestPath,
  }) {
    final completer = Completer<T>();
    operation.then(
      (value) {
        if (!completer.isCompleted) completer.complete(value);
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!completer.isCompleted) {
          completer.completeError(error, stackTrace);
        }
      },
    );
    abortTrigger.then(
      (_) {
        if (!completer.isCompleted) {
          completer.completeError(
            http.RequestAbortedException(Uri(path: requestPath)),
          );
        }
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!completer.isCompleted) {
          completer.completeError(error, stackTrace);
        }
      },
    );
    return completer.future;
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
      retryAfter: res.headers['retry-after'],
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

  void close() {
    _client.close();
  }
}

bool _sameOrigin(Uri left, Uri right) {
  return left.scheme.toLowerCase() == right.scheme.toLowerCase() &&
      left.host.toLowerCase() == right.host.toLowerCase() &&
      _effectivePort(left) == _effectivePort(right);
}

int _effectivePort(Uri uri) {
  if (uri.hasPort) return uri.port;
  return uri.scheme.toLowerCase() == 'https' ? 443 : 80;
}
