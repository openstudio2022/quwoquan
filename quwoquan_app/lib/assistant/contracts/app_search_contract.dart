enum AppSearchContentType {
  chatMessage('chat_message'),
  post('post'),
  historyPost('history_post'),
  user('user'),
  circle('circle');

  const AppSearchContentType(this.wireName);

  final String wireName;
}

AppSearchContentType? parseAppSearchContentType(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'chat_message':
      return AppSearchContentType.chatMessage;
    case 'post':
      return AppSearchContentType.post;
    case 'history_post':
      return AppSearchContentType.historyPost;
    case 'user':
      return AppSearchContentType.user;
    case 'circle':
      return AppSearchContentType.circle;
  }
  return null;
}

enum AppSearchSortMode {
  relevance('relevance'),
  latest('latest');

  const AppSearchSortMode(this.wireName);

  final String wireName;
}

AppSearchSortMode parseAppSearchSortMode(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'latest':
      return AppSearchSortMode.latest;
    default:
      return AppSearchSortMode.relevance;
  }
}

class AppSearchFilters {
  const AppSearchFilters({
    this.timeStart = '',
    this.timeEnd = '',
    this.userId = '',
    this.username = '',
    this.keywords = const <String>[],
    this.isMine,
  });

  final String timeStart;
  final String timeEnd;
  final String userId;
  final String username;
  final List<String> keywords;
  final bool? isMine;

  Map<String, dynamic> toJson() => <String, dynamic>{
    if (timeStart.trim().isNotEmpty) 'timeStart': timeStart.trim(),
    if (timeEnd.trim().isNotEmpty) 'timeEnd': timeEnd.trim(),
    if (userId.trim().isNotEmpty) 'userId': userId.trim(),
    if (username.trim().isNotEmpty) 'username': username.trim(),
    if (keywords.isNotEmpty) 'keywords': keywords,
    if (isMine != null) 'isMine': isMine,
  };

  factory AppSearchFilters.fromJson(Object? raw) {
    if (raw is! Map) {
      return const AppSearchFilters();
    }
    final json = raw.cast<String, dynamic>();
    return AppSearchFilters(
      timeStart: (json['timeStart'] as String?)?.trim() ?? '',
      timeEnd: (json['timeEnd'] as String?)?.trim() ?? '',
      userId: (json['userId'] as String?)?.trim() ?? '',
      username: (json['username'] as String?)?.trim() ?? '',
      keywords: _stringList(json['keywords']),
      isMine: json['isMine'] is bool ? json['isMine'] as bool : null,
    );
  }
}

class AppSearchRequest {
  const AppSearchRequest({
    this.contractId = 'app_search_request',
    required this.query,
    this.contentTypes = const <AppSearchContentType>[],
    this.filters = const AppSearchFilters(),
    this.page = 1,
    this.pageSize = 10,
    this.nextPageToken = '',
    this.sort = AppSearchSortMode.relevance,
  });

  final String contractId;
  final String query;
  final List<AppSearchContentType> contentTypes;
  final AppSearchFilters filters;
  final int page;
  final int pageSize;
  final String nextPageToken;
  final AppSearchSortMode sort;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contractId': contractId,
    'query': query,
    'contentTypes': contentTypes
        .map((item) => item.wireName)
        .toList(growable: false),
    'filters': filters.toJson(),
    'page': page,
    'pageSize': pageSize,
    if (nextPageToken.trim().isNotEmpty) 'nextPageToken': nextPageToken.trim(),
    'sort': sort.wireName,
  };

  factory AppSearchRequest.fromJson(Map<String, dynamic> json) {
    return AppSearchRequest(
      contractId:
          (json['contractId'] as String?)?.trim() ?? 'app_search_request',
      query: (json['query'] as String?)?.trim() ?? '',
      contentTypes: _contentTypes(json['contentTypes']),
      filters: AppSearchFilters.fromJson(json['filters']),
      page: json['page'] is int ? json['page'] as int : 1,
      pageSize: json['pageSize'] is int ? json['pageSize'] as int : 10,
      nextPageToken: (json['nextPageToken'] as String?)?.trim() ?? '',
      sort: parseAppSearchSortMode((json['sort'] as String?)?.trim() ?? ''),
    );
  }
}

class AppSearchResultItem {
  const AppSearchResultItem({
    required this.contentType,
    required this.contentId,
    this.title = '',
    this.body = '',
    this.timestamp = '',
    this.profile = '',
    this.tags = const <String>[],
  });

  final AppSearchContentType contentType;
  final String contentId;
  final String title;
  final String body;
  final String timestamp;
  final String profile;
  final List<String> tags;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contentType': contentType.wireName,
    'contentId': contentId,
    'title': title,
    'body': body,
    'timestamp': timestamp,
    'profile': profile,
    'tags': tags,
  };

  factory AppSearchResultItem.fromJson(Map<String, dynamic> json) {
    return AppSearchResultItem(
      contentType:
          parseAppSearchContentType(
            (json['contentType'] as String?)?.trim() ?? '',
          ) ??
          AppSearchContentType.post,
      contentId: (json['contentId'] as String?)?.trim() ?? '',
      title: (json['title'] as String?)?.trim() ?? '',
      body: (json['body'] as String?)?.trim() ?? '',
      timestamp: (json['timestamp'] as String?)?.trim() ?? '',
      profile: (json['profile'] as String?)?.trim() ?? '',
      tags: _stringList(json['tags']),
    );
  }
}

class AppSearchResponse {
  const AppSearchResponse({
    this.contractId = 'app_search_response',
    this.results = const <AppSearchResultItem>[],
    this.nextPageToken = '',
  });

  final String contractId;
  final List<AppSearchResultItem> results;
  final String nextPageToken;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contractId': contractId,
    'results': results.map((item) => item.toJson()).toList(growable: false),
    'nextPageToken': nextPageToken,
  };

  factory AppSearchResponse.fromJson(Map<String, dynamic> json) {
    return AppSearchResponse(
      contractId:
          (json['contractId'] as String?)?.trim() ?? 'app_search_response',
      results: _resultItems(json['results']),
      nextPageToken: (json['nextPageToken'] as String?)?.trim() ?? '',
    );
  }
}

List<AppSearchContentType> _contentTypes(Object? raw) {
  if (raw is! List) {
    return const <AppSearchContentType>[];
  }
  return raw
      .map((item) => parseAppSearchContentType(item.toString()))
      .whereType<AppSearchContentType>()
      .toSet()
      .toList(growable: false);
}

List<AppSearchResultItem> _resultItems(Object? raw) {
  if (raw is! List) {
    return const <AppSearchResultItem>[];
  }
  return raw
      .whereType<Map>()
      .map((item) => AppSearchResultItem.fromJson(item.cast<String, dynamic>()))
      .where((item) => item.contentId.trim().isNotEmpty)
      .toList(growable: false);
}

List<String> _stringList(Object? raw) {
  if (raw is! List) {
    return const <String>[];
  }
  return raw
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}
