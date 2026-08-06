// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 5cebacbad8dfe3503f8dcf2d0f34dd34328ea5a6f0b3b297cbd11df0a9eb2d44

part of '../../../search/search_operation_contracts.g.dart';

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

  factory CanonicalSearchQuery.fromWire(Map<String, Object?> map, [String path = "CanonicalSearchQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"sessionId", "query", "mode", "objectTypes", "ids", "limit"}, path);
    return CanonicalSearchQuery(
      sessionId: map["sessionId"] == null ? null : _generatedRequestString(map["sessionId"], '$path.sessionId'),
      query: _generatedRequestString(map["query"], '$path.query'),
      mode: map.containsKey("mode") ? switch (map["mode"]) { "suggest" => CanonicalSearchMode.suggest, "result" => CanonicalSearchMode.result, _ => throw FormatException('$path.mode' + ' has an invalid enum value'), } : CanonicalSearchMode.result,
      objectTypes: map.containsKey("objectTypes") ? List<String>.unmodifiable(_generatedRequestList(map["objectTypes"], '$path.objectTypes').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.objectTypes' + '[${entry.key}]'))) : const <String>[],
      ids: map.containsKey("ids") ? List<String>.unmodifiable(_generatedRequestList(map["ids"], '$path.ids').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.ids' + '[${entry.key}]'))) : const <String>[],
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.sessionId != null) "sessionId": this.sessionId!,
    "query": this.query,
    "mode": this.mode.wireValue,
    "objectTypes": this.objectTypes.map((value) => value).toList(growable: false),
    if (this.ids.isNotEmpty) "ids": this.ids.map((value) => value).toList(growable: false),
    "limit": this.limit,
  };
}

final class ClearRecentSearchesCommand {
  ClearRecentSearchesCommand({
    String? scope,
  }) : scope = _normalizeGeneratedOptionalText(scope) {
  }

  final String? scope;

  factory ClearRecentSearchesCommand.fromWire(Map<String, Object?> map, [String path = "ClearRecentSearchesCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"scope"}, path);
    return ClearRecentSearchesCommand(
      scope: map["scope"] == null ? null : _generatedRequestString(map["scope"], '$path.scope'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.scope != null) "scope": this.scope!,
  };
}

final class DeleteRecentSearchCommand {
  DeleteRecentSearchCommand({
    required String entryId,
  }) : entryId = entryId.trim() {
    if (this.entryId.isEmpty) {
      throw ArgumentError.value(this.entryId, "entryId", 'must not be blank');
    }
  }

  final String entryId;

  factory DeleteRecentSearchCommand.fromWire(Map<String, Object?> map, [String path = "DeleteRecentSearchCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"entryId"}, path);
    return DeleteRecentSearchCommand(
      entryId: _generatedRequestString(map["entryId"], '$path.entryId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "entryId": this.entryId,
  };
}

final class ListHotQueriesQuery {
  static const int defaultLimit = 10;
  static const int maximumLimit = 20;

  ListHotQueriesQuery({
    int limit = 10,
  }) : limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 20) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 20");
    }
  }

  final int limit;

  factory ListHotQueriesQuery.fromWire(Map<String, Object?> map, [String path = "ListHotQueriesQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"limit"}, path);
    return ListHotQueriesQuery(
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 10,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "limit": this.limit,
  };
}

final class ListRecentSearchesQuery {
  ListRecentSearchesQuery({
    String? scope,
  }) : scope = _normalizeGeneratedOptionalText(scope) {
  }

  final String? scope;

  factory ListRecentSearchesQuery.fromWire(Map<String, Object?> map, [String path = "ListRecentSearchesQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"scope"}, path);
    return ListRecentSearchesQuery(
      scope: map["scope"] == null ? null : _generatedRequestString(map["scope"], '$path.scope'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.scope != null) "scope": this.scope!,
  };
}

final class ReportSearchFeedbackCommand {
  ReportSearchFeedbackCommand({
    required String searchRequestId,
    required SearchFeedbackEventType eventType,
    String? objectId,
    String? target,
    int? rankPosition,
    String? referralSource,
    String? feedRequestId,
    int? dwellMs,
  }) : searchRequestId = searchRequestId.trim(),
       eventType = eventType,
       objectId = _normalizeGeneratedOptionalText(objectId),
       target = _normalizeGeneratedOptionalText(target),
       rankPosition = rankPosition,
       referralSource = _normalizeGeneratedOptionalText(referralSource),
       feedRequestId = _normalizeGeneratedOptionalText(feedRequestId),
       dwellMs = dwellMs {
    if (this.searchRequestId.isEmpty) {
      throw ArgumentError.value(this.searchRequestId, "searchRequestId", 'must not be blank');
    }
    if (this.dwellMs != null && this.dwellMs! <= 0) {
      throw ArgumentError.value(this.dwellMs, "dwellMs", "must be positive");
    }
    if (this.eventType == SearchFeedbackEventType.dwell && this.dwellMs == null) {
      throw ArgumentError.value(this.dwellMs, "dwellMs", "is required when eventType is dwell");
    }
    if (this.eventType != SearchFeedbackEventType.dwell && this.dwellMs != null) {
      throw ArgumentError.value(this.dwellMs, "dwellMs", "is forbidden unless eventType is dwell");
    }
  }

  final String searchRequestId;
  final SearchFeedbackEventType eventType;
  final String? objectId;
  final String? target;
  final int? rankPosition;
  final String? referralSource;
  final String? feedRequestId;
  final int? dwellMs;

  factory ReportSearchFeedbackCommand.fromWire(Map<String, Object?> map, [String path = "ReportSearchFeedbackCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"searchRequestId", "eventType", "objectId", "target", "rankPosition", "referralSource", "feedRequestId", "dwellMs"}, path);
    return ReportSearchFeedbackCommand(
      searchRequestId: _generatedRequestString(map["searchRequestId"], '$path.searchRequestId'),
      eventType: switch (map["eventType"]) { "impression" => SearchFeedbackEventType.impression, "click" => SearchFeedbackEventType.click, "dwell" => SearchFeedbackEventType.dwell, "refine" => SearchFeedbackEventType.refine, "zero_result" => SearchFeedbackEventType.zeroResult, "degrade" => SearchFeedbackEventType.degrade, _ => throw FormatException('$path.eventType' + ' has an invalid enum value'), },
      objectId: map["objectId"] == null ? null : _generatedRequestString(map["objectId"], '$path.objectId'),
      target: map["target"] == null ? null : _generatedRequestString(map["target"], '$path.target'),
      rankPosition: map["rankPosition"] == null ? null : _generatedRequestInt(map["rankPosition"], '$path.rankPosition'),
      referralSource: map["referralSource"] == null ? null : _generatedRequestString(map["referralSource"], '$path.referralSource'),
      feedRequestId: map["feedRequestId"] == null ? null : _generatedRequestString(map["feedRequestId"], '$path.feedRequestId'),
      dwellMs: map["dwellMs"] == null ? null : _generatedRequestInt(map["dwellMs"], '$path.dwellMs'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "searchRequestId": this.searchRequestId,
    "eventType": this.eventType.wireValue,
    if (this.objectId != null) "objectId": this.objectId!,
    if (this.target != null) "target": this.target!,
    if (this.rankPosition != null) "rankPosition": this.rankPosition!,
    if (this.referralSource != null) "referralSource": this.referralSource!,
    if (this.feedRequestId != null) "feedRequestId": this.feedRequestId!,
    if (this.dwellMs != null) "dwellMs": this.dwellMs!,
  };
}

final class UpsertRecentSearchCommand {
  UpsertRecentSearchCommand({
    required String query,
    required String scope,
    String? facet,
  }) : query = query.trim(),
       scope = scope.trim(),
       facet = _normalizeGeneratedOptionalText(facet) {
    if (this.query.isEmpty) {
      throw ArgumentError.value(this.query, "query", 'must not be blank');
    }
    if (this.scope.isEmpty) {
      throw ArgumentError.value(this.scope, "scope", 'must not be blank');
    }
  }

  final String query;
  final String scope;
  final String? facet;

  factory UpsertRecentSearchCommand.fromWire(Map<String, Object?> map, [String path = "UpsertRecentSearchCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"query", "scope", "facet"}, path);
    return UpsertRecentSearchCommand(
      query: _generatedRequestString(map["query"], '$path.query'),
      scope: _generatedRequestString(map["scope"], '$path.scope'),
      facet: map["facet"] == null ? null : _generatedRequestString(map["facet"], '$path.facet'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "query": this.query,
    "scope": this.scope,
    if (this.facet != null) "facet": this.facet!,
  };
}

CloudOperationRequestPayload encodeSearchRecentSearchStateClearRecentSearchesGeneratedRequest(ClearRecentSearchesCommand request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.scope != null) "scope": request.scope!,
    },
  );
}

CloudOperationRequestPayload encodeSearchRecentSearchStateDeleteRecentSearchGeneratedRequest(DeleteRecentSearchCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "entryId": request.entryId,
    },
  );
}

CloudOperationRequestPayload encodeSearchRecentSearchStateListRecentSearchesGeneratedRequest(ListRecentSearchesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.scope != null) "scope": request.scope!,
    },
  );
}

CloudOperationRequestPayload encodeSearchRecentSearchStateUpsertRecentSearchGeneratedRequest(UpsertRecentSearchCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "query": request.query,
      "scope": request.scope,
      if (request.facet != null) "facet": request.facet!,
    },
  );
}

CloudOperationRequestPayload encodeSearchSearchFeedbackFactReportSearchFeedbackGeneratedRequest(ReportSearchFeedbackCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "searchRequestId": request.searchRequestId,
      "eventType": request.eventType.wireValue,
      if (request.objectId != null) "objectId": request.objectId!,
      if (request.target != null) "target": request.target!,
      if (request.rankPosition != null) "rankPosition": request.rankPosition!,
      if (request.referralSource != null) "referralSource": request.referralSource!,
      if (request.feedRequestId != null) "feedRequestId": request.feedRequestId!,
      if (request.dwellMs != null) "dwellMs": request.dwellMs!,
    },
  );
}

CloudOperationRequestPayload encodeSearchSearchIndexViewSearchGeneratedRequest(CanonicalSearchQuery request) {
  return CloudOperationRequestPayload(
    headers: <String, String>{
      if (request.sessionId != null) "X-Session-Id": request.sessionId!,
    },
    body: <String, Object?>{
      "query": request.query,
      "mode": request.mode.wireValue,
      "objectTypes": request.objectTypes.map((value) => value).toList(growable: false),
      if (request.ids.isNotEmpty) "ids": request.ids.map((value) => value).toList(growable: false),
      "limit": request.limit,
    },
  );
}

CloudOperationRequestPayload encodeSearchSearchRequestFactListHotQueriesGeneratedRequest(ListHotQueriesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
    },
  );
}

