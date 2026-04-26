import 'package:quwoquan_app/assistant/contracts/app_search_contract.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

class AppSearchTool implements AssistantTool {
  AppSearchTool({required SearchRepository searchRepository})
    : _searchRepository = searchRepository;

  static const String toolName = 'app_search';

  final SearchRepository _searchRepository;

  @override
  String get name => toolName;

  @override
  String get description => '统一检索应用内个人、他人及全站信息。';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final request = AppSearchRequest.fromJson(arguments.toDynamicJson());
    if (request.query.trim().isEmpty) {
      return AssistantToolResult(
        success: false,
        message: '缺少应用内检索 query',
        errorCode: AssistantErrorCode.invalidArguments,
        degraded: true,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.invalidArguments,
          message: '缺少应用内检索 query',
          functionModule: toolName,
          stage: 'argument_validation',
        ),
      );
    }

    final response = await _searchRepository.search(
      SearchRequest(
        query: _canonicalRepositoryQuery(request),
        mode: SearchMode.result,
        objectTypes: _mapObjectTypes(request.contentTypes),
        limit: _repositoryLimit(request),
      ),
    );
    final filteredHits = response.hits
        .where((hit) {
          return _matchesFilters(hit, request.filters);
        })
        .toList(growable: false);
    final sortedHits = _sortHits(filteredHits, request.sort);
    final pageSize = _normalizedPageSize(request.pageSize);
    final page = _effectivePage(request);
    final start = (page - 1) * pageSize;
    final pagedHits = start >= sortedHits.length
        ? const <SearchHit>[]
        : sortedHits.skip(start).take(pageSize).toList(growable: false);
    final hasNextPage = start + pageSize < sortedHits.length;
    final appSearchResponse = AppSearchResponse(
      results: pagedHits
          .map((hit) => _toResultItem(hit, request.contentTypes))
          .toList(growable: false),
      nextPageToken: hasNextPage ? 'page:${page + 1}' : '',
    );
    return AssistantToolResult(
      success: true,
      message: '已完成应用内信息检索',
      data: AssistantToolResultData.fromJson(appSearchResponse.toJson()),
    );
  }

  String _canonicalRepositoryQuery(AppSearchRequest request) {
    final parts = <String>[
      request.query.trim(),
      ...request.filters.keywords.map((item) => item.trim()),
    ];
    final username = request.filters.username.trim();
    if (username.isNotEmpty) {
      parts.add(username);
    }
    return parts.where((item) => item.isNotEmpty).join(' ');
  }

  int _repositoryLimit(AppSearchRequest request) {
    final pageSize = _normalizedPageSize(request.pageSize);
    final page = _effectivePage(request);
    return (page * pageSize + 1).clamp(pageSize, 50).toInt();
  }

  int _normalizedPageSize(int raw) {
    return raw.clamp(1, 50).toInt();
  }

  int _effectivePage(AppSearchRequest request) {
    final token = request.nextPageToken.trim();
    if (token.startsWith('page:')) {
      final parsed = int.tryParse(token.substring('page:'.length).trim());
      if (parsed != null && parsed > 0) {
        return parsed;
      }
    }
    return request.page > 0 ? request.page : 1;
  }

  bool _matchesFilters(SearchHit hit, AppSearchFilters filters) {
    final payload = _payloadMap(hit);
    return _matchesKeywords(hit, payload, filters.keywords) &&
        _matchesUserId(payload, filters.userId) &&
        _matchesUsername(hit, payload, filters.username) &&
        _matchesIsMine(payload, filters.isMine) &&
        _matchesTimeRange(hit, payload, filters.timeStart, filters.timeEnd);
  }

  bool _matchesKeywords(
    SearchHit hit,
    Map<String, dynamic> payload,
    List<String> keywords,
  ) {
    if (keywords.isEmpty) return true;
    final haystack = _searchableText(hit, payload).toLowerCase();
    for (final keyword in keywords) {
      final normalized = keyword.trim().toLowerCase();
      if (normalized.isNotEmpty && !haystack.contains(normalized)) {
        return false;
      }
    }
    return true;
  }

  bool _matchesUserId(Map<String, dynamic> payload, String userId) {
    final normalized = userId.trim();
    if (normalized.isEmpty) return true;
    return _payloadValues(payload, const <String>[
      'userId',
      'authorUserId',
      'senderUserId',
      'ownerUserId',
      'contactId',
    ]).contains(normalized);
  }

  bool _matchesUsername(
    SearchHit hit,
    Map<String, dynamic> payload,
    String username,
  ) {
    final normalized = username.trim().toLowerCase();
    if (normalized.isEmpty) return true;
    final candidates = <String>[
      hit.title,
      hit.subtitle ?? '',
      ..._payloadValues(payload, const <String>[
        'username',
        'displayName',
        'authorDisplayName',
        'senderDisplayName',
        'conversationTitle',
        'name',
      ]),
    ].map((item) => item.toLowerCase()).toList(growable: false);
    return candidates.any((item) => item.contains(normalized));
  }

  bool _matchesIsMine(Map<String, dynamic> payload, bool? isMine) {
    if (isMine == null) return true;
    final raw = payload['isMine'] ?? payload['mine'] ?? payload['ownedByMe'];
    return raw is bool ? raw == isMine : true;
  }

  bool _matchesTimeRange(
    SearchHit hit,
    Map<String, dynamic> payload,
    String timeStart,
    String timeEnd,
  ) {
    final start = DateTime.tryParse(timeStart.trim());
    final end = DateTime.tryParse(timeEnd.trim());
    if (start == null && end == null) return true;
    final timestamp = DateTime.tryParse(_timestampFor(hit, payload));
    if (timestamp == null) return true;
    if (start != null && timestamp.isBefore(start)) return false;
    if (end != null && timestamp.isAfter(end)) return false;
    return true;
  }

  List<SearchHit> _sortHits(List<SearchHit> hits, AppSearchSortMode sort) {
    if (sort != AppSearchSortMode.latest) {
      return hits;
    }
    final sorted = List<SearchHit>.of(hits);
    sorted.sort((left, right) {
      final leftTime = DateTime.tryParse(
        _timestampFor(left, _payloadMap(left)),
      );
      final rightTime = DateTime.tryParse(
        _timestampFor(right, _payloadMap(right)),
      );
      if (leftTime == null && rightTime == null) return 0;
      if (leftTime == null) return 1;
      if (rightTime == null) return -1;
      return rightTime.compareTo(leftTime);
    });
    return sorted;
  }

  String _searchableText(SearchHit hit, Map<String, dynamic> payload) {
    return <String>[
      hit.objectId,
      hit.title,
      hit.subtitle ?? '',
      hit.snippet ?? '',
      ...payload.values.map((item) => item.toString()),
    ].join(' ');
  }

  List<String> _payloadValues(Map<String, dynamic> payload, List<String> keys) {
    return keys
        .map((key) => payload[key]?.toString().trim() ?? '')
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }

  Set<SearchObjectType> _mapObjectTypes(
    List<AppSearchContentType> contentTypes,
  ) {
    if (contentTypes.isEmpty) {
      return const <SearchObjectType>{
        SearchObjectType.chatMessage,
        SearchObjectType.contentPost,
        SearchObjectType.entityHomepage,
        SearchObjectType.circleCircle,
      };
    }

    final mapped = <SearchObjectType>{};
    for (final contentType in contentTypes) {
      switch (contentType) {
        case AppSearchContentType.chatMessage:
          mapped.add(SearchObjectType.chatMessage);
        case AppSearchContentType.post:
        case AppSearchContentType.historyPost:
          mapped.add(SearchObjectType.contentPost);
        case AppSearchContentType.user:
          mapped
            ..add(SearchObjectType.entityHomepage)
            ..add(SearchObjectType.chatContact);
        case AppSearchContentType.circle:
          mapped.add(SearchObjectType.circleCircle);
      }
    }
    return mapped;
  }

  AppSearchResultItem _toResultItem(
    SearchHit hit,
    List<AppSearchContentType> requestedContentTypes,
  ) {
    final payload = _payloadMap(hit);
    final contentType = _toContentType(
      hit.objectType,
      requestedContentTypes: requestedContentTypes,
    );
    return AppSearchResultItem(
      contentType: contentType,
      contentId: hit.objectId,
      title: _titleFor(contentType, hit, payload),
      body: _bodyFor(contentType, hit, payload),
      timestamp: _timestampFor(hit, payload),
      profile: _profileFor(contentType, hit, payload),
      tags: _tagsFor(contentType, payload),
    );
  }

  AppSearchContentType _toContentType(
    SearchObjectType objectType, {
    required List<AppSearchContentType> requestedContentTypes,
  }) {
    switch (objectType) {
      case SearchObjectType.chatMessage:
        return AppSearchContentType.chatMessage;
      case SearchObjectType.contentPost:
        return requestedContentTypes.length == 1 &&
                requestedContentTypes.single == AppSearchContentType.historyPost
            ? AppSearchContentType.historyPost
            : AppSearchContentType.post;
      case SearchObjectType.chatContact:
      case SearchObjectType.entityHomepage:
        return AppSearchContentType.user;
      case SearchObjectType.circleCircle:
      case SearchObjectType.circleGroup:
        return AppSearchContentType.circle;
      case SearchObjectType.chatConversation:
        return AppSearchContentType.chatMessage;
      case SearchObjectType.integrationLocationPoi:
      case SearchObjectType.webDocument:
        return AppSearchContentType.post;
    }
  }

  Map<String, dynamic> _payloadMap(SearchHit hit) {
    final payload = hit.toMap()['payload'];
    if (payload is! Map) {
      return const <String, dynamic>{};
    }
    return payload.cast<String, dynamic>();
  }

  String _titleFor(
    AppSearchContentType contentType,
    SearchHit hit,
    Map<String, dynamic> payload,
  ) {
    switch (contentType) {
      case AppSearchContentType.chatMessage:
        return _firstNonEmpty(<Object?>[
          payload['conversationTitle'],
          hit.title,
        ]);
      case AppSearchContentType.post:
      case AppSearchContentType.historyPost:
        return _firstNonEmpty(<Object?>[payload['title'], hit.title]);
      case AppSearchContentType.user:
      case AppSearchContentType.circle:
        return _firstNonEmpty(<Object?>[hit.title, payload['name']]);
    }
  }

  String _bodyFor(
    AppSearchContentType contentType,
    SearchHit hit,
    Map<String, dynamic> payload,
  ) {
    switch (contentType) {
      case AppSearchContentType.chatMessage:
        return _firstNonEmpty(<Object?>[
          payload['body'],
          payload['contentPreview'],
          payload['lastMessagePreview'],
          hit.snippet,
          hit.subtitle,
        ]);
      case AppSearchContentType.post:
      case AppSearchContentType.historyPost:
        return _firstNonEmpty(<Object?>[
          payload['body'],
          payload['summary'],
          payload['highlightText'],
          hit.snippet,
        ]);
      case AppSearchContentType.user:
      case AppSearchContentType.circle:
        return '';
    }
  }

  String _profileFor(
    AppSearchContentType contentType,
    SearchHit hit,
    Map<String, dynamic> payload,
  ) {
    switch (contentType) {
      case AppSearchContentType.user:
        return _joinProfileSegments(<String>[
          _firstNonEmpty(<Object?>[
            payload['subtitle'],
            payload['displayName'],
            hit.subtitle,
          ]),
          _firstNonEmpty(<Object?>[payload['address'], hit.snippet]),
        ]);
      case AppSearchContentType.circle:
        return _joinProfileSegments(<String>[
          _firstNonEmpty(<Object?>[payload['description'], hit.snippet]),
          _firstNonEmpty(<Object?>[
            payload['subCategory'],
            payload['categoryId'],
          ]),
        ]);
      case AppSearchContentType.post:
      case AppSearchContentType.historyPost:
        return _firstNonEmpty(<Object?>[
          payload['authorDisplayName'],
          payload['displayName'],
        ]);
      case AppSearchContentType.chatMessage:
        return _firstNonEmpty(<Object?>[
          payload['senderDisplayName'],
          payload['conversationTitle'],
          hit.subtitle,
        ]);
    }
  }

  List<String> _tagsFor(
    AppSearchContentType contentType,
    Map<String, dynamic> payload,
  ) {
    switch (contentType) {
      case AppSearchContentType.post:
      case AppSearchContentType.historyPost:
        return <String>[
          _stringValue(payload['categoryId']),
          _stringValue(payload['subCategory']),
        ].where((item) => item.isNotEmpty).toList(growable: false);
      case AppSearchContentType.chatMessage:
      case AppSearchContentType.user:
      case AppSearchContentType.circle:
        return const <String>[];
    }
  }

  String _timestampFor(SearchHit hit, Map<String, dynamic> payload) {
    return _firstNonEmpty(<Object?>[
      payload['sentAt'],
      payload['createdAt'],
      payload['updatedAt'],
      payload['publishedAt'],
      payload['timestamp'],
    ]);
  }

  String _joinProfileSegments(List<String> segments) {
    return segments.where((item) => item.trim().isNotEmpty).join(' · ').trim();
  }

  String _stringValue(Object? raw) {
    return raw?.toString().trim() ?? '';
  }

  String _firstNonEmpty(List<Object?> candidates) {
    for (final candidate in candidates) {
      final value = candidate?.toString().trim() ?? '';
      if (value.isNotEmpty) {
        return value;
      }
    }
    return '';
  }
}
