// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 647c7b556596bb370e386bfe039faeb5263ea0e884d49cdc37e360c8ed295ab1

part of '../../../gateway/gateway_operation_contracts.g.dart';


void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}


String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}


int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}


List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class SearchPageInput {
  SearchPageInput({
    required String query,
    int? first,
    String? after,
    List<String>? objectTypes,
  }) : query = query,
       first = first,
       after = after,
       objectTypes = objectTypes == null ? null : List.unmodifiable(objectTypes) {
  }

  final String query;
  final int? first;
  final String? after;
  final List<String>? objectTypes;

  factory SearchPageInput.fromWire(Map<String, Object?> map, [String path = "SearchPageInput"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"query", "first", "after", "objectTypes"}, path);
    return SearchPageInput(
      query: _generatedRequestString(map["query"], '$path.query'),
      first: map["first"] == null ? null : _generatedRequestInt(map["first"], '$path.first'),
      after: map["after"] == null ? null : _generatedRequestString(map["after"], '$path.after'),
      objectTypes: map["objectTypes"] == null ? null : List<String>.unmodifiable(_generatedRequestList(map["objectTypes"], '$path.objectTypes').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.objectTypes' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "query": this.query,
    if (this.first != null) "first": this.first!,
    if (this.after != null) "after": this.after!,
    if (this.objectTypes != null) "objectTypes": this.objectTypes!.map((value) => value).toList(growable: false),
  };
}

CloudOperationRequestPayload encodeGatewayPersistedQueryExecutionSearchPageGeneratedRequest(SearchPageInput request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "query": request.query,
      if (request.first != null) "first": request.first!,
      if (request.after != null) "after": request.after!,
      if (request.objectTypes != null) "objectTypes": request.objectTypes!.map((value) => value).toList(growable: false),
    },
  );
}

