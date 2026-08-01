import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

/// Time range filter for [RetrieveRequest]. Matches the frozen retrieve
/// contract `filters.timeRange`.
class RetrieveTimeRange {
  const RetrieveTimeRange({this.from, this.to});

  final DateTime? from;
  final DateTime? to;

  bool get isEmpty => from == null && to == null;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      if (from != null) 'from': from!.toUtc().toIso8601String(),
      if (to != null) 'to': to!.toUtc().toIso8601String(),
    };
  }
}

/// Fixed, named filter group. Intentionally NOT a free-form where clause.
class RetrieveFilters {
  const RetrieveFilters({this.tags = const <String>[], this.timeRange});

  final List<String> tags;
  final RetrieveTimeRange? timeRange;

  bool get isEmpty => tags.isEmpty && (timeRange == null || timeRange!.isEmpty);

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      if (tags.isNotEmpty) 'tags': List<String>.from(tags),
      if (timeRange != null && !timeRange!.isEmpty)
        'timeRange': timeRange!.toMap(),
    };
  }
}

/// Pagination for [RetrieveRequest].
class RetrievePage {
  const RetrievePage({this.limit = 20, this.cursor = ''});

  final int limit;
  final String cursor;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'limit': limit,
      if (cursor.isNotEmpty) 'cursor': cursor,
    };
  }
}

/// Unified object retrieval request shared with the cloud `retrieve` contract.
///
/// The AI/App only declares which objects to retrieve (`targets`) and the match
/// conditions (`ids` / `names` / `terms`); `filters` (tags / timeRange) narrow
/// the candidates. It deliberately exposes none of the forbidden fields
/// (`type` / `relation` / `mode` / `strategy` / `visibility` / ...).
class RetrieveRequest {
  const RetrieveRequest({
    this.targets = const <RetrieveTarget>[],
    this.ids = const <String>[],
    this.names = const <String>[],
    this.terms = const <String>[],
    this.filters = const RetrieveFilters(),
    this.page = const RetrievePage(),
  });

  final List<RetrieveTarget> targets;
  final List<String> ids;
  final List<String> names;
  final List<String> terms;
  final RetrieveFilters filters;
  final RetrievePage page;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'targets': targets.map((t) => t.wireValue).toList(growable: false),
      if (ids.isNotEmpty) 'ids': List<String>.from(ids),
      if (names.isNotEmpty) 'names': List<String>.from(names),
      if (terms.isNotEmpty) 'terms': List<String>.from(terms),
      if (!filters.isEmpty) 'filters': filters.toMap(),
      'page': page.toMap(),
    };
  }
}

/// Standard retrieve hit, caller-agnostic. Mirrors the cloud `RetrieveHit`.
class RetrieveHit {
  const RetrieveHit({
    required this.target,
    required this.objectId,
    required this.title,
    this.snippet = '',
    this.score = 0,
    this.matchedTerms = const <String>[],
    this.matchedTags = const <String>[],
    this.payload = const <String, dynamic>{},
  });

  final RetrieveTarget target;
  final String objectId;
  final String title;
  final String snippet;
  final double score;
  final List<String> matchedTerms;
  final List<String> matchedTags;
  final Map<String, dynamic> payload;

  factory RetrieveHit.fromMap(Map<String, dynamic> map) {
    return RetrieveHit(
      target:
          RetrieveTarget.fromWire(map['target']?.toString()) ??
          RetrieveTarget.article,
      objectId: map['objectId']?.toString() ?? '',
      title: map['title']?.toString() ?? '',
      snippet: map['snippet']?.toString() ?? '',
      score: (map['score'] as num?)?.toDouble() ?? 0,
      matchedTerms: _stringList(map['matchedTerms']),
      matchedTags: _stringList(map['matchedTags']),
      payload: map['payload'] is Map<String, dynamic>
          ? map['payload'] as Map<String, dynamic>
          : const <String, dynamic>{},
    );
  }

  static List<String> _stringList(Object? value) {
    if (value is List) {
      return value
          .map((e) => e.toString())
          .where((e) => e.isNotEmpty)
          .toList(growable: false);
    }
    return const <String>[];
  }
}

/// Unified retrieve response envelope.
class RetrieveResponse {
  const RetrieveResponse({
    required this.request,
    this.hits = const <RetrieveHit>[],
    this.degradeSignals = const <SearchDegradeSignal>[],
  });

  final RetrieveRequest request;
  final List<RetrieveHit> hits;
  final List<SearchDegradeSignal> degradeSignals;
}

/// Sanity helper: assert a retrieve payload never carries a forbidden field.
/// Mirrors `RetrieveToolContract.forbiddenFields` from the frozen metadata.
bool retrievePayloadIsContractClean(Map<String, dynamic> payload) {
  for (final forbidden in RetrieveToolContract.forbiddenFields) {
    if (payload.containsKey(forbidden)) {
      return false;
    }
  }
  return true;
}
