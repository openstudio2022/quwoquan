// ignore_for_file: prefer_initializing_formals

import 'dart:convert';

import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

final class AppTelemetryBatchAck {
  const AppTelemetryBatchAck({
    required this.acceptedCount,
    required this.duplicateBatch,
  });

  final int acceptedCount;
  final bool duplicateBatch;
}

abstract interface class AppTelemetryTransport {
  Future<AppTelemetryBatchAck> sendSealedBatch({
    required String canonicalBody,
    required String idempotencyKey,
  });
}

final class CloudAppTelemetryTransport implements AppTelemetryTransport {
  CloudAppTelemetryTransport({
    required CloudHttpClient httpClient,
    String? baseUrl,
  }) : _httpClient = httpClient,
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<AppTelemetryBatchAck> sendSealedBatch({
    required String canonicalBody,
    required String idempotencyKey,
  }) async {
    final path = OpsApiMetadata.reportEventBatchPath;
    final response = await _httpClient.post(
      Uri.parse('$_baseUrl$path'),
      headers: <String, String>{
        ...CloudRequestHeaders.forPage(OpsRequestPageIds.reportEventBatch),
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: canonicalBody,
      encoding: utf8,
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw CloudErrorMapper.fromStatusCode(
        response.statusCode,
        body: response.body,
        requestPath: path,
        retryAfter: response.headers['retry-after'],
      );
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) {
      throw CloudErrorMapper.invalidResponse(
        message: 'telemetry batch ACK must be an object',
        requestPath: path,
      );
    }
    final acceptedCount = _asInt(decoded['acceptedCount']);
    final duplicateBatch = decoded['duplicateBatch'];
    if (acceptedCount < 0 || duplicateBatch is! bool) {
      throw CloudErrorMapper.invalidResponse(
        message: 'telemetry batch ACK has invalid fields',
        requestPath: path,
      );
    }
    return AppTelemetryBatchAck(
      acceptedCount: acceptedCount,
      duplicateBatch: duplicateBatch,
    );
  }

  int _asInt(Object? value) {
    if (value is int) return value;
    return int.tryParse(value?.toString() ?? '') ?? -1;
  }
}

String canonicalJsonEncode(Object? value) => jsonEncode(_canonicalize(value));

Object? _canonicalize(Object? value) {
  if (value is Map) {
    final keys = value.keys.map((key) => key.toString()).toList()..sort();
    return <String, Object?>{
      for (final key in keys) key: _canonicalize(value[key]),
    };
  }
  if (value is Iterable) {
    return value.map(_canonicalize).toList(growable: false);
  }
  return value;
}
