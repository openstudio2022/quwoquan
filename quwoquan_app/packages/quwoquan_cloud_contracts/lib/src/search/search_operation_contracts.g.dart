// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: c447f801faf8d50cae864f8bc2675a26bff61f2f0d114d1c3cf1cce3ae907bdb

library;

import '../operation_request_payload.dart';
import "../generated/search/canonical_search_mode.g.dart";
import "../generated/search_feedback_event_type.g.dart";

export "../generated/search/canonical_search_mode.g.dart";
export "../generated/search/search_contract_vocabulary.g.dart";
export "../generated/search/search_response_view.g.dart";
export "../generated/search_feedback_event_type.g.dart";

part '../generated/requests/search/search_operation_contracts.g.requests.g.dart';

final class RecentSearchCommandAck {
  const RecentSearchCommandAck({required this.status});

  final String status;

  factory RecentSearchCommandAck.fromWire(
    Map<String, Object?> map, [
    String path = "RecentSearchCommandAck",
  ]) {
    _rejectUnknownFields(map, const <String>{"status"}, path);
    return RecentSearchCommandAck(
      status: _requiredString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"status": status};
}

final class RecentSearchEntrySlice {
  const RecentSearchEntrySlice({required this.items});

  final List<RecentSearchEntryWire> items;

  factory RecentSearchEntrySlice.fromWire(
    Map<String, Object?> map, [
    String path = "RecentSearchEntrySlice",
  ]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return RecentSearchEntrySlice(
      items: List<RecentSearchEntryWire>.unmodifiable(
        _requiredList(map["items"], '$path.items').asMap().entries.map(
          (entry) => RecentSearchEntryWire.fromWire(
            _requiredObject(entry.value, '$path.items' + '[${entry.key}]'),
            '$path.items' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class RecentSearchEntryWire {
  const RecentSearchEntryWire({
    required this.entryId,
    required this.query,
    required this.scope,
    this.facet,
    required this.updatedAt,
  });

  final String entryId;
  final String query;
  final String scope;
  final String? facet;
  final DateTime updatedAt;

  factory RecentSearchEntryWire.fromWire(
    Map<String, Object?> map, [
    String path = "RecentSearchEntryWire",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "entryId",
      "query",
      "scope",
      "facet",
      "updatedAt",
    }, path);
    return RecentSearchEntryWire(
      entryId: _requiredString(map["entryId"], '$path.entryId'),
      query: _requiredString(map["query"], '$path.query'),
      scope: _requiredString(map["scope"], '$path.scope'),
      facet: map["facet"] == null
          ? null
          : _requiredString(map["facet"], '$path.facet'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "entryId": entryId,
    "query": query,
    "scope": scope,
    if (facet != null) "facet": facet!,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class SearchFeedbackAck {
  const SearchFeedbackAck({required this.accepted, required this.requestId});

  final bool accepted;
  final String requestId;

  factory SearchFeedbackAck.fromWire(
    Map<String, Object?> map, [
    String path = "SearchFeedbackAck",
  ]) {
    _rejectUnknownFields(map, const <String>{"accepted", "requestId"}, path);
    return SearchFeedbackAck(
      accepted: _requiredBool(map["accepted"], '$path.accepted'),
      requestId: _requiredString(map["requestId"], '$path.requestId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "accepted": accepted,
    "requestId": requestId,
  };
}

final class SearchTermHeatItem {
  const SearchTermHeatItem({required this.query, required this.relevance});

  final String query;
  final double relevance;

  factory SearchTermHeatItem.fromWire(
    Map<String, Object?> map, [
    String path = "SearchTermHeatItem",
  ]) {
    _rejectUnknownFields(map, const <String>{"query", "relevance"}, path);
    return SearchTermHeatItem(
      query: _requiredString(map["query"], '$path.query'),
      relevance: _requiredDouble(map["relevance"], '$path.relevance'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "query": query,
    "relevance": relevance,
  };
}

final class SearchTermHeatSlice {
  const SearchTermHeatSlice({required this.items});

  final List<SearchTermHeatItem> items;

  factory SearchTermHeatSlice.fromWire(
    Map<String, Object?> map, [
    String path = "SearchTermHeatSlice",
  ]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return SearchTermHeatSlice(
      items: List<SearchTermHeatItem>.unmodifiable(
        _requiredList(map["items"], '$path.items').asMap().entries.map(
          (entry) => SearchTermHeatItem.fromWire(
            _requiredObject(entry.value, '$path.items' + '[${entry.key}]'),
            '$path.items' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

RecentSearchCommandAck decodeRecentSearchCommandAck(Object? response) =>
    RecentSearchCommandAck.fromWire(
      _requiredObject(response, "RecentSearchCommandAck"),
      "RecentSearchCommandAck",
    );

RecentSearchEntrySlice decodeRecentSearchEntrySlice(Object? response) =>
    RecentSearchEntrySlice.fromWire(
      _requiredObject(response, "RecentSearchEntrySlice"),
      "RecentSearchEntrySlice",
    );

RecentSearchEntryWire decodeRecentSearchEntryWire(Object? response) =>
    RecentSearchEntryWire.fromWire(
      _requiredObject(response, "RecentSearchEntryWire"),
      "RecentSearchEntryWire",
    );

SearchFeedbackAck decodeSearchFeedbackAck(Object? response) =>
    SearchFeedbackAck.fromWire(
      _requiredObject(response, "SearchFeedbackAck"),
      "SearchFeedbackAck",
    );

SearchTermHeatSlice decodeSearchTermHeatSlice(Object? response) =>
    SearchTermHeatSlice.fromWire(
      _requiredObject(response, "SearchTermHeatSlice"),
      "SearchTermHeatSlice",
    );

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException(
      '$path contains unknown fields: ${unknown.join(', ')}',
    );
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

double _requiredDouble(Object? value, String path) {
  if (value is! num) throw FormatException('$path must be a number');
  return value.toDouble();
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
