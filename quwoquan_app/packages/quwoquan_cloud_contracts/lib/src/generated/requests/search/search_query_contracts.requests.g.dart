// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.sessionId != null) "sessionId": this.sessionId!,
    "query": this.query,
    "mode": switch (this.mode) { CanonicalSearchMode.suggest => "suggest", CanonicalSearchMode.result => "result", },
    "objectTypes": this.objectTypes.map((value) => value).toList(growable: false),
    if (this.ids.isNotEmpty) "ids": this.ids.map((value) => value).toList(growable: false),
    "limit": this.limit,
  };
}

CloudOperationRequestPayload encodeSearchSearchIndexViewSearchGeneratedRequest(CanonicalSearchQuery request) {
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

