// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 706dad710e4f1250b9e7691b55e7aa2583905544296e2ddaa55ecef53fd07c31

part of '../../../gateway/gateway_operation_contracts.g.dart';

Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}

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
    ClientContentPresentationContract? clientPresentationContract,
    required String query,
    int? first,
    String? after,
    List<String>? objectTypes,
    List<String>? contentTypes,
  }) : clientPresentationContract = clientPresentationContract,
       query = query,
       first = first,
       after = after,
       objectTypes = objectTypes == null
           ? null
           : List.unmodifiable(objectTypes),
       contentTypes = contentTypes == null
           ? null
           : List.unmodifiable(contentTypes) {}

  final ClientContentPresentationContract? clientPresentationContract;
  final String query;
  final int? first;
  final String? after;
  final List<String>? objectTypes;
  final List<String>? contentTypes;

  factory SearchPageInput.fromWire(
    Map<String, Object?> map, [
    String path = "SearchPageInput",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "clientPresentationContract",
      "query",
      "first",
      "after",
      "objectTypes",
      "contentTypes",
    }, path);
    return SearchPageInput(
      clientPresentationContract: map["clientPresentationContract"] == null
          ? null
          : ClientContentPresentationContract.fromWire(
              _generatedRequestObject(
                map["clientPresentationContract"],
                '$path.clientPresentationContract',
              ),
              '$path.clientPresentationContract',
            ),
      query: _generatedRequestString(map["query"], '$path.query'),
      first: map["first"] == null
          ? null
          : _generatedRequestInt(map["first"], '$path.first'),
      after: map["after"] == null
          ? null
          : _generatedRequestString(map["after"], '$path.after'),
      objectTypes: map["objectTypes"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["objectTypes"],
                '$path.objectTypes',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.objectTypes' + '[${entry.key}]',
                ),
              ),
            ),
      contentTypes: map["contentTypes"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["contentTypes"],
                '$path.contentTypes',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.contentTypes' + '[${entry.key}]',
                ),
              ),
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.clientPresentationContract != null)
      "clientPresentationContract": this.clientPresentationContract!.toWire(),
    "query": this.query,
    if (this.first != null) "first": this.first!,
    if (this.after != null) "after": this.after!,
    if (this.objectTypes != null)
      "objectTypes": this.objectTypes!
          .map((value) => value)
          .toList(growable: false),
    if (this.contentTypes != null)
      "contentTypes": this.contentTypes!
          .map((value) => value)
          .toList(growable: false),
  };
}

CloudOperationRequestPayload
encodeGatewayPersistedQueryExecutionSearchPageGeneratedRequest(
  SearchPageInput request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.clientPresentationContract != null)
        "clientPresentationContract": request.clientPresentationContract!
            .toWire(),
      "query": request.query,
      if (request.first != null) "first": request.first!,
      if (request.after != null) "after": request.after!,
      if (request.objectTypes != null)
        "objectTypes": request.objectTypes!
            .map((value) => value)
            .toList(growable: false),
      if (request.contentTypes != null)
        "contentTypes": request.contentTypes!
            .map((value) => value)
            .toList(growable: false),
    },
  );
}
