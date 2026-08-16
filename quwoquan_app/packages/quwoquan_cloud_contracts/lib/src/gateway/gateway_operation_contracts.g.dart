// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 2a80fd8995b437f8bf98acb9e3f369212a5edf05d488c5b22f54c343a0db9cad

library;

import '../operation_request_payload.dart';

part '../generated/requests/gateway/gateway_operation_contracts.g.requests.g.dart';

enum SearchPageContentType {
  article("ARTICLE"),
  image("IMAGE"),
  video("VIDEO");

  const SearchPageContentType(this.wireName);

  final String wireName;

  static SearchPageContentType fromWire(Object? value, String path) {
    return switch (value) {
      "ARTICLE" => SearchPageContentType.article,
      "IMAGE" => SearchPageContentType.image,
      "VIDEO" => SearchPageContentType.video,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum SearchPageObjectType {
  circle("CIRCLE"),
  circleGroup("CIRCLE_GROUP"),
  contentPost("CONTENT_POST"),
  entityHomepage("ENTITY_HOMEPAGE"),
  locationPlace("LOCATION_PLACE"),
  userProfile("USER_PROFILE");

  const SearchPageObjectType(this.wireName);

  final String wireName;

  static SearchPageObjectType fromWire(Object? value, String path) {
    return switch (value) {
      "CIRCLE" => SearchPageObjectType.circle,
      "CIRCLE_GROUP" => SearchPageObjectType.circleGroup,
      "CONTENT_POST" => SearchPageObjectType.contentPost,
      "ENTITY_HOMEPAGE" => SearchPageObjectType.entityHomepage,
      "LOCATION_PLACE" => SearchPageObjectType.locationPlace,
      "USER_PROFILE" => SearchPageObjectType.userProfile,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class SearchPageDegradeSignal {
  const SearchPageDegradeSignal({
    required this.code,
    required this.message,
    this.objectType,
  });

  final String code;
  final String message;
  final String? objectType;

  factory SearchPageDegradeSignal.fromWire(Map<String, Object?> map, [String path = "SearchPageDegradeSignal"]) {
    _rejectUnknownFields(map, const <String>{"code", "message", "objectType"}, path);
    return SearchPageDegradeSignal(
      code: _requiredString(map["code"], '$path.code'),
      message: _requiredString(map["message"], '$path.message'),
      objectType: map["objectType"] == null ? null : _requiredString(map["objectType"], '$path.objectType'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "code": code,
    "message": message,
    if (objectType != null) "objectType": objectType!,
  };
}

final class SearchPageFacet {
  const SearchPageFacet({
    required this.key,
    required this.count,
  });

  final String key;
  final int count;

  factory SearchPageFacet.fromWire(Map<String, Object?> map, [String path = "SearchPageFacet"]) {
    _rejectUnknownFields(map, const <String>{"key", "count"}, path);
    return SearchPageFacet(
      key: _requiredString(map["key"], '$path.key'),
      count: _requiredInt(map["count"], '$path.count'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "key": key,
    "count": count,
  };
}

final class SearchPageItem {
  const SearchPageItem({
    required this.objectRef,
    required this.resultType,
    this.contentType,
    required this.title,
    this.subtitle,
    this.snippet,
    this.thumbnailUrl,
    required this.action,
    required this.rankPosition,
    this.rankReason,
  });

  final String objectRef;
  final SearchPageObjectType resultType;
  final SearchPageContentType? contentType;
  final String title;
  final String? subtitle;
  final String? snippet;
  final String? thumbnailUrl;
  final String action;
  final int rankPosition;
  final String? rankReason;

  factory SearchPageItem.fromWire(Map<String, Object?> map, [String path = "SearchPageItem"]) {
    _rejectUnknownFields(map, const <String>{"objectRef", "resultType", "contentType", "title", "subtitle", "snippet", "thumbnailUrl", "action", "rankPosition", "rankReason"}, path);
    return SearchPageItem(
      objectRef: _requiredString(map["objectRef"], '$path.objectRef'),
      resultType: SearchPageObjectType.fromWire(map["resultType"], '$path.resultType'),
      contentType: map["contentType"] == null ? null : SearchPageContentType.fromWire(map["contentType"], '$path.contentType'),
      title: _requiredString(map["title"], '$path.title'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      snippet: map["snippet"] == null ? null : _requiredString(map["snippet"], '$path.snippet'),
      thumbnailUrl: map["thumbnailUrl"] == null ? null : _requiredString(map["thumbnailUrl"], '$path.thumbnailUrl'),
      action: _requiredString(map["action"], '$path.action'),
      rankPosition: _requiredInt(map["rankPosition"], '$path.rankPosition'),
      rankReason: map["rankReason"] == null ? null : _requiredString(map["rankReason"], '$path.rankReason'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectRef": objectRef,
    "resultType": resultType.wireName,
    if (contentType != null) "contentType": contentType!.wireName,
    "title": title,
    if (subtitle != null) "subtitle": subtitle!,
    if (snippet != null) "snippet": snippet!,
    if (thumbnailUrl != null) "thumbnailUrl": thumbnailUrl!,
    "action": action,
    "rankPosition": rankPosition,
    if (rankReason != null) "rankReason": rankReason!,
  };
}

final class SearchPageSlice {
  const SearchPageSlice({
    required this.items,
    required this.facets,
    required this.suggestions,
    required this.matchedTerms,
    required this.degradeSignals,
    required this.searchRequestId,
    this.nextCursor,
  });

  final List<SearchPageItem> items;
  final List<SearchPageFacet> facets;
  final List<String> suggestions;
  final List<String> matchedTerms;
  final List<SearchPageDegradeSignal> degradeSignals;
  final String searchRequestId;
  final String? nextCursor;

  factory SearchPageSlice.fromWire(Map<String, Object?> map, [String path = "SearchPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "facets", "suggestions", "matchedTerms", "degradeSignals", "searchRequestId", "nextCursor"}, path);
    return SearchPageSlice(
      items: List<SearchPageItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => SearchPageItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      facets: List<SearchPageFacet>.unmodifiable(_requiredList(map["facets"], '$path.facets').asMap().entries.map((entry) => SearchPageFacet.fromWire(_requiredObject(entry.value, '$path.facets' + '[${entry.key}]'), '$path.facets' + '[${entry.key}]'))),
      suggestions: List<String>.unmodifiable(_requiredList(map["suggestions"], '$path.suggestions').asMap().entries.map((entry) => _requiredString(entry.value, '$path.suggestions' + '[${entry.key}]'))),
      matchedTerms: List<String>.unmodifiable(_requiredList(map["matchedTerms"], '$path.matchedTerms').asMap().entries.map((entry) => _requiredString(entry.value, '$path.matchedTerms' + '[${entry.key}]'))),
      degradeSignals: List<SearchPageDegradeSignal>.unmodifiable(_requiredList(map["degradeSignals"], '$path.degradeSignals').asMap().entries.map((entry) => SearchPageDegradeSignal.fromWire(_requiredObject(entry.value, '$path.degradeSignals' + '[${entry.key}]'), '$path.degradeSignals' + '[${entry.key}]'))),
      searchRequestId: _requiredString(map["searchRequestId"], '$path.searchRequestId'),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "facets": facets.map((value) => value.toWire()).toList(growable: false),
    "suggestions": suggestions.map((value) => value).toList(growable: false),
    "matchedTerms": matchedTerms.map((value) => value).toList(growable: false),
    "degradeSignals": degradeSignals.map((value) => value.toWire()).toList(growable: false),
    "searchRequestId": searchRequestId,
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

SearchPageSlice decodeSearchPageSlice(Object? response) =>
    SearchPageSlice.fromWire(_requiredObject(response, "SearchPageSlice"), "SearchPageSlice");

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
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
