import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
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
