import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';

final CloudHttpClient _legalDocumentClient = CloudHttpClient(
  timeout: const Duration(seconds: 5),
);

Future<bool> defaultLegalDocumentAvailabilityProbe(
  Uri uri, {
  http.Client? client,
}) async {
  try {
    final response = await _client(
      client,
    ).get(uri, headers: const <String, String>{'Range': 'bytes=0-0'});
    return _isSuccessfulStatus(response.statusCode) ||
        response.statusCode == 206;
  } catch (_) {
    return false;
  }
}

Future<String> defaultLegalDocumentHtmlLoader(
  Uri uri, {
  http.Client? client,
}) async {
  final response = await _client(client).get(uri);
  if (!_isSuccessfulStatus(response.statusCode)) {
    throw StateError('legal_document_http_${response.statusCode}');
  }
  return utf8.decode(response.bodyBytes);
}

CloudHttpClient _client(http.Client? client) => client == null
    ? _legalDocumentClient
    : CloudHttpClient(client: client, timeout: const Duration(seconds: 5));

bool _isSuccessfulStatus(int statusCode) =>
    statusCode >= 200 && statusCode < 400;
