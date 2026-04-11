import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';

class CloudHttpClient {
  CloudHttpClient({
    http.Client? client,
    CloudAuthTokenProvider? authTokenProvider,
    Duration? timeout,
  }) : _client = client ?? http.Client(),
       _authTokenProvider = authTokenProvider ?? const StubCloudAuthTokenProvider(),
       _timeout = timeout ?? const Duration(seconds: 12);

  final http.Client _client;
  final CloudAuthTokenProvider _authTokenProvider;
  final Duration _timeout;

  /// JSON 解码结果可能是 `Map`、`List`、标量或 `null`；当前返回 [Future<dynamic>]。
  /// 全仓库若改为强类型（例如仅对象的 `Future<Map<String, dynamic>>` 或按路由生成解码器），
  /// 应作为单独横向里程碑统一推进，避免单域（如 RTC）与全局风格分裂。
  Future<dynamic> getJson(
    Uri uri, {
    required Map<String, String> headers,
  }) async {
    final merged = await _mergeHeaders(headers);
    final res = await _guardRequest(
      () => _client.get(uri, headers: merged).timeout(_timeout),
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  /// 见 [getJson]：响应体同样经 [jsonDecode]，返回类型保持 [Future<dynamic>] 直至全仓库协调升级。
  Future<dynamic> postJson(
    Uri uri, {
    required Map<String, String> headers,
    required Map<String, dynamic> body,
  }) async {
    final merged = await _mergeHeaders(headers);
    final payload = jsonEncode(body);
    final requestHeaders = <String, String>{
      ...merged,
      'Content-Type': 'application/json',
    };
    final res = await _guardRequest(
      () => _client.post(uri, headers: requestHeaders, body: payload).timeout(_timeout),
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  Future<dynamic> patchJson(
    Uri uri, {
    required Map<String, String> headers,
    required Map<String, dynamic> body,
  }) async {
    final merged = await _mergeHeaders(headers);
    final payload = jsonEncode(body);
    final requestHeaders = <String, String>{
      ...merged,
      'Content-Type': 'application/json',
    };
    final res = await _guardRequest(
      () => _client.patch(uri, headers: requestHeaders, body: payload).timeout(_timeout),
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  Future<dynamic> putJson(
    Uri uri, {
    required Map<String, String> headers,
    required Map<String, dynamic> body,
  }) async {
    final merged = await _mergeHeaders(headers);
    final payload = jsonEncode(body);
    final requestHeaders = <String, String>{
      ...merged,
      'Content-Type': 'application/json',
    };
    final res = await _guardRequest(
      () => _client.put(uri, headers: requestHeaders, body: payload).timeout(_timeout),
    );
    _guardStatus(res, uri.path);
    return _decodeBody(res.body, uri.path);
  }

  Future<dynamic> deleteJson(
    Uri uri, {
    required Map<String, String> headers,
  }) async {
    final merged = await _mergeHeaders(headers);
    final res = await _guardRequest(
      () => _client.delete(uri, headers: merged).timeout(_timeout),
    );
    _guardStatus(res, uri.path);
    if (res.body.isEmpty) return const <String, dynamic>{};
    return _decodeBody(res.body, uri.path);
  }

  /// [getJson] 后立即 [CloudResponseDecoder.asObject]，供需要根对象为 Map 的调用方使用。
  Future<Map<String, dynamic>> getJsonObject(
    Uri uri, {
    required Map<String, String> headers,
    required String context,
  }) async {
    final decoded = await getJson(uri, headers: headers);
    return CloudResponseDecoder.asObject(decoded, context: context);
  }

  /// 根为 JSON 数组，或根为对象且列表落在 `listKeys` 之一（与 [CloudResponseDecoder.mapListFirstNonEmpty] 一致）。
  Future<List<Map<String, dynamic>>> getJsonItemList(
    Uri uri, {
    required Map<String, String> headers,
    required String context,
    List<String> listKeys = const <String>[
      'items',
      'subAccounts',
      'personas',
    ],
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
  Future<Map<String, dynamic>> postJsonObject(
    Uri uri, {
    required Map<String, String> headers,
    required Map<String, dynamic> body,
    required String context,
  }) async {
    final decoded = await postJson(uri, headers: headers, body: body);
    return CloudResponseDecoder.asObject(decoded, context: context);
  }

  /// [patchJson] 后立即 [CloudResponseDecoder.asObject]。
  Future<Map<String, dynamic>> patchJsonObject(
    Uri uri, {
    required Map<String, String> headers,
    required Map<String, dynamic> body,
    required String context,
  }) async {
    final decoded = await patchJson(uri, headers: headers, body: body);
    return CloudResponseDecoder.asObject(decoded, context: context);
  }

  Future<Map<String, String>> _mergeHeaders(Map<String, String> headers) async {
    final token = await _authTokenProvider.getAccessToken();
    if (token == null || token.isEmpty) return headers;
    return <String, String>{
      ...headers,
      'Authorization': 'Bearer $token',
    };
  }

  Future<http.Response> _guardRequest(
    Future<http.Response> Function() run,
  ) async {
    try {
      return await run();
    } on TimeoutException catch (e) {
      throw CloudException(
        type: CloudErrorType.timeout,
        message: 'Request timed out',
        cause: e,
      );
    } on SocketException catch (e) {
      throw CloudException(
        type: CloudErrorType.network,
        message: 'Network unavailable',
        cause: e,
      );
    } catch (e) {
      if (e is CloudException) rethrow;
      throw CloudException(
        type: CloudErrorType.unknown,
        message: 'Request failed',
        cause: e,
      );
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

  dynamic _decodeBody(String body, String path) {
    if (body.isEmpty) return const <String, dynamic>{};
    try {
      return jsonDecode(body);
    } catch (e) {
      throw CloudException(
        type: CloudErrorType.invalidResponse,
        message: 'Invalid JSON response ($path)',
        cause: e,
      );
    }
  }
}
