import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
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
  const RetrieveFilters({
    this.tags = const <String>[],
    this.timeRange,
  });

  final List<String> tags;
  final RetrieveTimeRange? timeRange;

  bool get isEmpty =>
      tags.isEmpty && (timeRange == null || timeRange!.isEmpty);

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

  /// Compatibility bridge: convert an earlier [SearchRequest] into the unified
  /// retrieve contract. No forbidden field (mode/objectTypes/contentTypes/
  /// conversationType/categoryId) ever leaks; they only influence target
  /// selection and term derivation.
  factory RetrieveRequest.fromSearchRequest(SearchRequest request) {
    final normalized = request.normalized();
    return RetrieveRequest(
      targets: _targetsFor(normalized),
      terms: _termsFor(normalized.query),
      page: RetrievePage(limit: normalized.limit),
    );
  }

  static List<String> _termsFor(String query) {
    final trimmed = query.trim();
    if (trimmed.isEmpty) {
      return const <String>[];
    }
    final terms = <String>[trimmed];
    for (final token in trimmed.split(RegExp(r'\s+'))) {
      final t = token.trim();
      if (t.isNotEmpty && t != trimmed) {
        terms.add(t);
      }
    }
    return terms;
  }

  static List<RetrieveTarget> _targetsFor(SearchRequest request) {
    final targets = <RetrieveTarget>{};
    for (final objectType in request.objectTypes) {
      switch (objectType) {
        case SearchObjectType.contentPost:
          targets.addAll(_contentTargets(request.contentTypes));
        case SearchObjectType.userProfile:
          targets.add(RetrieveTarget.user);
        case SearchObjectType.entityHomepage:
          targets.add(RetrieveTarget.entity);
        case SearchObjectType.circleCircle:
          targets.add(RetrieveTarget.circle);
        case SearchObjectType.circleGroup:
          targets.add(RetrieveTarget.group);
        case SearchObjectType.chatContact:
        case SearchObjectType.chatConversation:
        case SearchObjectType.chatMessage:
          targets.add(RetrieveTarget.chat);
        case SearchObjectType.locationPlace:
          // First-party place object (R-S05e): a free-text place referenced by
          // content but not yet bound to an entity homepage.
          targets.add(RetrieveTarget.location);
        case SearchObjectType.webDocument:
        case SearchObjectType.tag:
        case SearchObjectType.integrationLocationPoi:
          // Not retrieve business targets (web is a citation supplement; tag is a
          // filter; integration.location_poi is the live 3rd-party POI handled by
          // integration, distinct from the first-party location.place above).
          break;
      }
    }
    if (targets.isEmpty) {
      // Default broad fan-out matching the result-mode object set
      // (search-service DefaultResultTargets, single-sourced with the cloud).
      targets.addAll(<RetrieveTarget>[
        RetrieveTarget.article,
        RetrieveTarget.photo,
        RetrieveTarget.video,
        RetrieveTarget.user,
        RetrieveTarget.entity,
        RetrieveTarget.circle,
        RetrieveTarget.group,
        RetrieveTarget.location,
      ]);
    }
    return targets.toList(growable: false);
  }

  static Iterable<RetrieveTarget> _contentTargets(
    Set<SearchContentTypeFilter> contentTypes,
  ) {
    if (contentTypes.isEmpty) {
      return const <RetrieveTarget>[
        RetrieveTarget.article,
        RetrieveTarget.photo,
        RetrieveTarget.video,
      ];
    }
    final mapped = <RetrieveTarget>{};
    for (final type in contentTypes) {
      switch (type) {
        case SearchContentTypeFilter.article:
        case SearchContentTypeFilter.micro:
          mapped.add(RetrieveTarget.article);
        case SearchContentTypeFilter.image:
          mapped.add(RetrieveTarget.photo);
        case SearchContentTypeFilter.video:
          mapped.add(RetrieveTarget.video);
      }
    }
    return mapped;
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
