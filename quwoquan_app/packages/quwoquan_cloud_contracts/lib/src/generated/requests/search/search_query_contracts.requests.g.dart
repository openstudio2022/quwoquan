// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../search/search_query_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class CanonicalSearchQuery {
  CanonicalSearchQuery({
    String? sessionId,
    required String query,
    CanonicalSearchMode mode = CanonicalSearchMode.result,
    Iterable<String> objectTypes = const <String>[],
    Iterable<String> ids = const <String>[],
    int limit = 20,
  }) : sessionId = _normalizeGeneratedOptionalText(sessionId),
       query = query.trim(),
       mode = mode,
       objectTypes = _normalizeGeneratedTextList(objectTypes, deduplicate: false),
       ids = _normalizeGeneratedTextList(ids, deduplicate: false),
       limit = limit {
    if (this.query.isEmpty) {
      throw ArgumentError.value(this.query, "query", 'must not be blank');
    }
  }

  final String? sessionId;
  final String query;
  final CanonicalSearchMode mode;
  final List<String> objectTypes;
  final List<String> ids;
  final int limit;
}

CloudOperationRequestPayload encodeSearchSearchQuerySearchQueryGeneratedRequest(CanonicalSearchQuery request) {
  return CloudOperationRequestPayload(
    headers: <String, String>{
      if (request.sessionId != null) "X-Session-Id": request.sessionId!,
    },
    body: <String, Object?>{
      "query": request.query,
      "mode": switch (request.mode) { CanonicalSearchMode.suggest => "suggest", CanonicalSearchMode.result => "result", },
      "objectTypes": request.objectTypes.map((value) => value).toList(growable: false),
      if (request.ids.isNotEmpty) "ids": request.ids.map((value) => value).toList(growable: false),
      "limit": request.limit,
    },
  );
}

