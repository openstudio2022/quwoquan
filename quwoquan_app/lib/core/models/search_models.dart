import 'package:flutter/cupertino.dart';

enum SearchScope {
  all,
  content,
  socialRelation,
  messages,
  circles;

  String get wireValue => switch (this) {
    SearchScope.all => 'all',
    SearchScope.content => 'content',
    SearchScope.socialRelation => 'social_relation',
    SearchScope.messages => 'messages',
    SearchScope.circles => 'circles',
  };

  String get label => switch (this) {
    SearchScope.all => '全部',
    SearchScope.content => '内容',
    SearchScope.socialRelation => '社交关系',
    SearchScope.messages => '聊天',
    SearchScope.circles => '群组',
  };

  static SearchScope fromWire(String? raw) {
    switch ((raw ?? '').trim()) {
      case 'content':
        return SearchScope.content;
      case 'social_relation':
        return SearchScope.socialRelation;
      case 'messages':
        return SearchScope.messages;
      case 'circles':
        return SearchScope.circles;
      case 'all':
      default:
        return SearchScope.all;
    }
  }
}

enum SearchObjectTarget {
  contacts,
  directChats,
  groupChats,
  circles;

  String get wireValue => switch (this) {
    SearchObjectTarget.contacts => 'contacts',
    SearchObjectTarget.directChats => 'direct_chats',
    SearchObjectTarget.groupChats => 'group_chats',
    SearchObjectTarget.circles => 'circles',
  };

  String get label => switch (this) {
    SearchObjectTarget.contacts => '联系人',
    SearchObjectTarget.directChats => '单聊',
    SearchObjectTarget.groupChats => '群聊',
    SearchObjectTarget.circles => '群组',
  };

  static SearchObjectTarget? fromWire(String raw) {
    switch (raw.trim()) {
      case 'contacts':
        return SearchObjectTarget.contacts;
      case 'direct_chats':
        return SearchObjectTarget.directChats;
      case 'group_chats':
        return SearchObjectTarget.groupChats;
      case 'circles':
        return SearchObjectTarget.circles;
      default:
        return null;
    }
  }
}

enum SearchContentTypeFilter {
  article,
  image,
  video,
  moment;

  String get wireValue => switch (this) {
    SearchContentTypeFilter.article => 'article',
    SearchContentTypeFilter.image => 'image',
    SearchContentTypeFilter.video => 'video',
    SearchContentTypeFilter.moment => 'moment',
  };

  String get label => switch (this) {
    SearchContentTypeFilter.article => '文章',
    SearchContentTypeFilter.image => '图片',
    SearchContentTypeFilter.video => '视频',
    SearchContentTypeFilter.moment => '动态',
  };

  String get identity => switch (this) {
    SearchContentTypeFilter.moment => 'moment',
    SearchContentTypeFilter.article ||
    SearchContentTypeFilter.image ||
    SearchContentTypeFilter.video => 'work',
  };

  String get contentType => switch (this) {
    SearchContentTypeFilter.article => 'article',
    SearchContentTypeFilter.image => 'image',
    SearchContentTypeFilter.video => 'video',
    SearchContentTypeFilter.moment => 'micro',
  };

  static SearchContentTypeFilter? fromWire(String raw) {
    switch (raw.trim()) {
      case 'article':
        return SearchContentTypeFilter.article;
      case 'image':
        return SearchContentTypeFilter.image;
      case 'video':
        return SearchContentTypeFilter.video;
      case 'moment':
        return SearchContentTypeFilter.moment;
      default:
        return null;
    }
  }
}

class SearchObjectSelection {
  const SearchObjectSelection({
    this.targets = const <SearchObjectTarget>{},
    this.contentTypes = const <SearchContentTypeFilter>{},
  });

  final Set<SearchObjectTarget> targets;
  final Set<SearchContentTypeFilter> contentTypes;

  Set<SearchObjectTarget> get normalizedTargets =>
      targets.length == 1 ? <SearchObjectTarget>{targets.first} : const {};

  bool get isEmpty => normalizedTargets.isEmpty;
  bool get isAll => normalizedTargets.isEmpty;
  bool get isAllContent => contentTypes.isEmpty;

  SearchObjectTarget? get activeObjectTarget =>
      normalizedTargets.length == 1 ? normalizedTargets.first : null;

  Set<SearchContentTypeFilter> get enabledContentTypes =>
      isAllContent ? SearchContentTypeFilter.values.toSet() : contentTypes;

  SearchContentTypeFilter? get activeContentType {
    for (final type in SearchContentTypeFilter.values) {
      if (contentTypes.contains(type)) {
        return type;
      }
    }
    return null;
  }

  bool contains(SearchObjectTarget target) =>
      normalizedTargets.contains(target);

  bool isContentTypeEnabled(SearchContentTypeFilter type) =>
      enabledContentTypes.contains(type);

  SearchObjectSelection normalized() {
    final normalizedContentTypes =
        contentTypes.length == SearchContentTypeFilter.values.length
        ? const <SearchContentTypeFilter>{}
        : <SearchContentTypeFilter>{
            for (final type in SearchContentTypeFilter.values)
              if (contentTypes.contains(type)) type,
          };
    return SearchObjectSelection(
      targets: normalizedTargets,
      contentTypes: normalizedContentTypes,
    );
  }

  String? toFacet() {
    final normalizedSelection = normalized();
    if (normalizedSelection.isEmpty) {
      if (normalizedSelection.isAllContent) {
        return null;
      }
    }
    final params = <String, String>{};
    if (!normalizedSelection.isAll) {
      params['targets'] = normalizedSelection.activeObjectTarget!.wireValue;
    }
    if (!normalizedSelection.isAllContent) {
      params['content'] = SearchContentTypeFilter.values
          .where(normalizedSelection.contentTypes.contains)
          .map((item) => item.wireValue)
          .join(',');
    }
    if (params.isEmpty) {
      return null;
    }
    return Uri(queryParameters: params).query;
  }

  SearchObjectSelection copyWith({
    Set<SearchObjectTarget>? targets,
    Set<SearchContentTypeFilter>? contentTypes,
  }) {
    return SearchObjectSelection(
      targets: targets ?? this.targets,
      contentTypes: contentTypes ?? this.contentTypes,
    ).normalized();
  }

  static SearchObjectSelection fromFacet(String? raw) {
    final trimmed = (raw ?? '').trim();
    if (trimmed.isEmpty) {
      return const SearchObjectSelection();
    }
    try {
      final params = Uri.splitQueryString(trimmed);
      final rawTargets = (params['targets'] ?? '').split(',');
      final legacyHasChatRecords = rawTargets.any(
        (value) => value.trim() == 'chat_records',
      );
      final targets = legacyHasChatRecords
          ? const <SearchObjectTarget>{}
          : rawTargets
                .map(SearchObjectTarget.fromWire)
                .whereType<SearchObjectTarget>()
                .take(1)
                .toSet();
      final contentTypes =
          ((params['content'] ?? '')
                  .split(',')
                  .map(SearchContentTypeFilter.fromWire)
                  .whereType<SearchContentTypeFilter>())
              .toSet();
      return SearchObjectSelection(
        targets: targets,
        contentTypes: contentTypes,
      ).normalized();
    } catch (_) {
      return const SearchObjectSelection();
    }
  }

  static SearchObjectSelection fromLegacyScope(SearchScope scope) {
    switch (scope) {
      case SearchScope.content:
        return const SearchObjectSelection();
      case SearchScope.socialRelation:
        return const SearchObjectSelection(
          targets: <SearchObjectTarget>{SearchObjectTarget.contacts},
        );
      case SearchScope.messages:
        return const SearchObjectSelection();
      case SearchScope.circles:
        return const SearchObjectSelection(
          targets: <SearchObjectTarget>{SearchObjectTarget.circles},
        );
      case SearchScope.all:
        return const SearchObjectSelection();
    }
  }
}

class SearchLaunchContext {
  const SearchLaunchContext({
    required this.entrySurfaceId,
    this.initialScope = SearchScope.all,
    this.searchObjectSelection = const SearchObjectSelection(),
    this.prefilledQuery = '',
    this.restoreState = true,
    this.initialFacet,
    this.initialNetworkTabId,
  });

  final String entrySurfaceId;
  final SearchScope initialScope;
  final SearchObjectSelection searchObjectSelection;
  final String prefilledQuery;
  final bool restoreState;
  final String? initialFacet;
  final String? initialNetworkTabId;

  SearchLaunchContext copyWith({
    String? entrySurfaceId,
    SearchScope? initialScope,
    SearchObjectSelection? searchObjectSelection,
    String? prefilledQuery,
    bool? restoreState,
    String? initialFacet,
    String? initialNetworkTabId,
  }) {
    return SearchLaunchContext(
      entrySurfaceId: entrySurfaceId ?? this.entrySurfaceId,
      initialScope: initialScope ?? this.initialScope,
      searchObjectSelection:
          searchObjectSelection ?? this.searchObjectSelection,
      prefilledQuery: prefilledQuery ?? this.prefilledQuery,
      restoreState: restoreState ?? this.restoreState,
      initialFacet: initialFacet ?? this.initialFacet,
      initialNetworkTabId: initialNetworkTabId ?? this.initialNetworkTabId,
    );
  }
}

class SearchConversationAnchorContext {
  const SearchConversationAnchorContext({
    required this.messageAnchorId,
    this.sourceQuery,
  });

  final String messageAnchorId;
  final String? sourceQuery;
}

class PostSearchItemView {
  const PostSearchItemView({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.summary,
    this.coverUrl,
    this.authorProfileSubjectId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.circleId,
    this.circleName,
    this.categoryId,
    this.subCategory,
    this.likeCount = 0,
    this.highlightText,
    this.matchedField,
    this.publishedAt,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String? title;
  final String? summary;
  final String? coverUrl;
  final String? authorProfileSubjectId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? circleId;
  final String? circleName;
  final String? categoryId;
  final String? subCategory;
  final int likeCount;
  final String? highlightText;
  final String? matchedField;
  final DateTime? publishedAt;

  factory PostSearchItemView.fromMap(Map<String, dynamic> map) {
    return PostSearchItemView(
      postId: (map['postId'] ?? map['id'] ?? map['_id'] ?? '')
          .toString()
          .trim(),
      contentType: (map['contentType'] ?? map['type'] ?? 'image')
          .toString()
          .trim(),
      contentIdentity: map['contentIdentity']?.toString(),
      title: map['title']?.toString(),
      summary: (map['summary'] ?? map['body'] ?? map['highlightText'])
          ?.toString(),
      coverUrl: (map['coverUrl'] ?? map['thumbnailUrl'])?.toString(),
      authorProfileSubjectId:
          (map['authorProfileSubjectId'] ?? map['profileSubjectId'])
              ?.toString(),
      authorDisplayName:
          (map['authorDisplayName'] ??
                  map['authorDisplayNameSnapshot'] ??
                  map['displayName'])
              ?.toString(),
      authorAvatarUrl:
          (map['authorAvatarUrl'] ??
                  map['authorAvatarUrlSnapshot'] ??
                  map['avatarUrl'])
              ?.toString(),
      circleId: map['circleId']?.toString(),
      circleName: map['circleName']?.toString(),
      categoryId: map['categoryId']?.toString(),
      subCategory: map['subCategory']?.toString(),
      likeCount: _parseInt(map['likeCount']) ?? 0,
      highlightText: map['highlightText']?.toString(),
      matchedField: map['matchedField']?.toString(),
      publishedAt: _parseDateTime(map['publishedAt']),
    );
  }
}

class SocialRelationshipCapabilityView {
  const SocialRelationshipCapabilityView({
    required this.relationState,
    required this.canFollow,
    required this.canUnfollow,
    required this.canOpenConversation,
    required this.canStartVoiceCall,
    required this.canStartVideoCall,
  });

  final String relationState;
  final bool canFollow;
  final bool canUnfollow;
  final bool canOpenConversation;
  final bool canStartVoiceCall;
  final bool canStartVideoCall;

  factory SocialRelationshipCapabilityView.fromMap(Map<String, dynamic> map) {
    return SocialRelationshipCapabilityView(
      relationState: (map['relationState'] ?? 'not_following')
          .toString()
          .trim(),
      canFollow: map['canFollow'] == true,
      canUnfollow: map['canUnfollow'] == true,
      canOpenConversation: map['canOpenConversation'] == true,
      canStartVoiceCall: map['canStartVoiceCall'] == true,
      canStartVideoCall: map['canStartVideoCall'] == true,
    );
  }
}

class SocialRelationSearchItemView {
  const SocialRelationSearchItemView({
    required this.profileSubjectId,
    required this.username,
    required this.displayName,
    this.avatarUrl,
    this.headline,
    required this.chatAvailable,
    required this.relationshipCapability,
  });

  final String profileSubjectId;
  final String username;
  final String displayName;
  final String? avatarUrl;
  final String? headline;
  final bool chatAvailable;
  final SocialRelationshipCapabilityView relationshipCapability;

  factory SocialRelationSearchItemView.fromMap(Map<String, dynamic> map) {
    final capabilityMap =
        (map['relationshipCapability'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{
          'relationState':
              (map['relationState'] ??
                      map['relationshipState'] ??
                      'not_following')
                  .toString(),
          'canFollow': map['canFollow'] == true,
          'canUnfollow': map['canUnfollow'] == true,
          'canOpenConversation':
              map['canOpenConversation'] == true ||
              map['chatAvailable'] == true,
          'canStartVoiceCall': map['canStartVoiceCall'] == true,
          'canStartVideoCall': map['canStartVideoCall'] == true,
        };
    final profileSubjectId = (map['profileSubjectId'] ?? map['userId'] ?? '')
        .toString()
        .trim();
    final displayName =
        (map['displayName'] ?? map['nickname'] ?? profileSubjectId)
            .toString()
            .trim();
    return SocialRelationSearchItemView(
      profileSubjectId: profileSubjectId,
      username: (map['username'] ?? map['subAccountId'] ?? profileSubjectId)
          .toString()
          .trim(),
      displayName: displayName,
      avatarUrl: map['avatarUrl']?.toString(),
      headline: (map['headline'] ?? map['bio'])?.toString(),
      chatAvailable:
          map['chatAvailable'] == true ||
          capabilityMap['canOpenConversation'] == true,
      relationshipCapability: SocialRelationshipCapabilityView.fromMap(
        capabilityMap,
      ),
    );
  }
}

class ConversationSearchItemView {
  const ConversationSearchItemView({
    required this.conversationId,
    required this.type,
    required this.title,
    this.avatarUrl,
    this.avatarCompositeUrls = const <String>[],
    this.lastMessagePreview,
    this.lastMessageTime,
    required this.memberCount,
    this.circleId,
    this.circleGroupId,
    this.highlightText,
    this.matchedField,
  });

  final String conversationId;
  final String type;
  final String title;
  final String? avatarUrl;
  final List<String> avatarCompositeUrls;
  final String? lastMessagePreview;
  final DateTime? lastMessageTime;
  final int memberCount;
  final String? circleId;
  final String? circleGroupId;
  final String? highlightText;
  final String? matchedField;

  factory ConversationSearchItemView.fromMap(Map<String, dynamic> map) {
    return ConversationSearchItemView(
      conversationId: (map['conversationId'] ?? map['id'] ?? map['_id'] ?? '')
          .toString()
          .trim(),
      type: (map['type'] ?? 'direct').toString().trim(),
      title: (map['title'] ?? map['conversationTitle'] ?? '').toString().trim(),
      avatarUrl: map['avatarUrl']?.toString(),
      avatarCompositeUrls:
          _parseStringList(
            map['avatarCompositeUrls'] ?? map['memberAvatars'],
          ) ??
          const <String>[],
      lastMessagePreview: (map['lastMessagePreview'] ?? map['highlightText'])
          ?.toString(),
      lastMessageTime: _parseDateTime(map['lastMessageTime']),
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      circleId: map['circleId']?.toString(),
      circleGroupId: map['circleGroupId']?.toString(),
      highlightText: map['highlightText']?.toString(),
      matchedField: map['matchedField']?.toString(),
    );
  }
}

class MessageSearchItemView {
  const MessageSearchItemView({
    required this.messageId,
    required this.conversationId,
    this.conversationTitle,
    this.conversationAvatarUrl,
    this.senderProfileSubjectId,
    this.senderDisplayName,
    this.senderAvatarUrl,
    required this.messageType,
    required this.contentPreview,
    this.seq,
    required this.timestamp,
    this.highlightText,
    this.matchedField,
  });

  final String messageId;
  final String conversationId;
  final String? conversationTitle;
  final String? conversationAvatarUrl;
  final String? senderProfileSubjectId;
  final String? senderDisplayName;
  final String? senderAvatarUrl;
  final String messageType;
  final String contentPreview;
  final int? seq;
  final DateTime timestamp;
  final String? highlightText;
  final String? matchedField;

  factory MessageSearchItemView.fromMap(Map<String, dynamic> map) {
    return MessageSearchItemView(
      messageId: (map['messageId'] ?? map['id'] ?? map['_id'] ?? '')
          .toString()
          .trim(),
      conversationId: (map['conversationId'] ?? '').toString().trim(),
      conversationTitle: map['conversationTitle']?.toString(),
      conversationAvatarUrl: map['conversationAvatarUrl']?.toString(),
      senderProfileSubjectId: (map['senderProfileSubjectId'] ?? map['senderId'])
          ?.toString(),
      senderDisplayName:
          (map['senderDisplayName'] ??
                  map['senderDisplayNameSnapshot'] ??
                  map['senderName'])
              ?.toString(),
      senderAvatarUrl:
          (map['senderAvatarUrl'] ?? map['senderAvatarUrlSnapshot'])
              ?.toString(),
      messageType: (map['messageType'] ?? map['type'] ?? 'text')
          .toString()
          .trim(),
      contentPreview: (map['contentPreview'] ?? map['content'] ?? '')
          .toString()
          .trim(),
      seq: (map['seq'] as num?)?.toInt(),
      timestamp: _parseDateTime(map['timestamp']) ?? DateTime.now(),
      highlightText: map['highlightText']?.toString(),
      matchedField: map['matchedField']?.toString(),
    );
  }
}

class CircleSearchItemView {
  const CircleSearchItemView({
    required this.circleId,
    required this.name,
    this.description,
    this.coverUrl,
    this.categoryId,
    this.subCategory,
    this.domainId,
    this.kind,
    this.displaySubjectType,
    required this.memberCount,
    required this.postCount,
    this.highlightText,
    this.matchedField,
    this.circleName,
  });

  final String circleId;
  final String name;
  final String? description;
  final String? coverUrl;
  final String? categoryId;
  final String? subCategory;
  final String? domainId;
  final String? kind;
  final String? displaySubjectType;
  final int memberCount;
  final int postCount;
  final String? highlightText;
  final String? matchedField;
  /// 群组结果场景下父圈子展示名（wire：`circleName` / `circle_name`）。
  final String? circleName;

  factory CircleSearchItemView.fromMap(Map<String, dynamic> map) {
    return CircleSearchItemView(
      circleId: (map['circleId'] ?? map['id'] ?? map['_id'] ?? '')
          .toString()
          .trim(),
      name: (map['name'] ?? '').toString().trim(),
      description: map['description']?.toString(),
      coverUrl: (map['coverUrl'] ?? map['cover'])?.toString(),
      categoryId: (map['categoryId'] ?? map['category'])?.toString(),
      subCategory: map['subCategory']?.toString(),
      domainId: map['domainId']?.toString(),
      kind: map['kind']?.toString(),
      displaySubjectType: map['displaySubjectType']?.toString(),
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      postCount: (map['postCount'] as num?)?.toInt() ?? 0,
      highlightText: map['highlightText']?.toString(),
      matchedField: map['matchedField']?.toString(),
      circleName:
          map['circleName']?.toString() ?? map['circle_name']?.toString(),
    );
  }
}

class CircleFacetBucketView {
  const CircleFacetBucketView({
    required this.facetKey,
    required this.label,
    this.categoryId,
    this.subCategory,
    required this.facetCount,
  });

  final String facetKey;
  final String label;
  final String? categoryId;
  final String? subCategory;
  final int facetCount;

  factory CircleFacetBucketView.fromMap(Map<String, dynamic> map) {
    return CircleFacetBucketView(
      facetKey:
          (map['facetKey'] ?? map['subCategory'] ?? map['categoryId'] ?? '')
              .toString()
              .trim(),
      label: (map['label'] ?? map['subCategory'] ?? map['categoryId'] ?? '')
          .toString()
          .trim(),
      categoryId: map['categoryId']?.toString(),
      subCategory: map['subCategory']?.toString(),
      facetCount: (map['facetCount'] as num?)?.toInt() ?? 0,
    );
  }
}

class CircleSearchResultView {
  const CircleSearchResultView({
    this.items = const <CircleSearchItemView>[],
    this.facetBuckets = const <CircleFacetBucketView>[],
  });

  final List<CircleSearchItemView> items;
  final List<CircleFacetBucketView> facetBuckets;

  factory CircleSearchResultView.fromMap(Map<String, dynamic> map) {
    final itemMaps =
        (map['items'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final facetMaps =
        (map['facetBuckets'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return CircleSearchResultView(
      items: itemMaps.map(CircleSearchItemView.fromMap).toList(growable: false),
      facetBuckets: facetMaps
          .map(CircleFacetBucketView.fromMap)
          .toList(growable: false),
    );
  }
}

class RecentSearchEntryView {
  const RecentSearchEntryView({
    required this.entryId,
    required this.query,
    required this.scope,
    this.facet,
    required this.updatedAt,
  });

  final String entryId;
  final String query;
  final SearchScope scope;
  final String? facet;
  final DateTime updatedAt;

  static String buildEntryId({
    required String query,
    required SearchScope scope,
    String? facet,
  }) {
    final normalizedQuery = query.trim().toLowerCase();
    final normalizedFacet = (facet ?? '').trim().toLowerCase();
    return Uri.encodeComponent(
      '${scope.wireValue}::$normalizedQuery::$normalizedFacet',
    );
  }

  factory RecentSearchEntryView.fromMap(Map<String, dynamic> map) {
    final query = (map['query'] ?? '').toString().trim();
    final scope = SearchScope.fromWire(map['scope']?.toString());
    final facet = map['facet']?.toString();
    return RecentSearchEntryView(
      entryId:
          (map['entryId'] ??
                  buildEntryId(query: query, scope: scope, facet: facet))
              .toString()
              .trim(),
      query: query,
      scope: scope,
      facet: facet?.trim().isEmpty == true ? null : facet,
      updatedAt: _parseDateTime(map['updatedAt']) ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'entryId': entryId,
      'query': query,
      'scope': scope.wireValue,
      'facet': facet,
      'updatedAt': updatedAt.toIso8601String(),
    };
  }

  RecentSearchEntryView copyWith({
    String? entryId,
    String? query,
    SearchScope? scope,
    ValueGetter<String?>? facet,
    DateTime? updatedAt,
  }) {
    return RecentSearchEntryView(
      entryId: entryId ?? this.entryId,
      query: query ?? this.query,
      scope: scope ?? this.scope,
      facet: facet != null ? facet() : this.facet,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}

enum SearchViewMode { historyBrowse, historyManage, liveSuggestions }

enum SearchSuggestionSectionKind {
  mostUsed,
  contacts,
  chatRecords,
  circles,
  network;

  String get title => switch (this) {
    SearchSuggestionSectionKind.mostUsed => '最常使用',
    SearchSuggestionSectionKind.contacts => '联系人',
    SearchSuggestionSectionKind.chatRecords => '聊天记录',
    SearchSuggestionSectionKind.circles => '群组',
    SearchSuggestionSectionKind.network => '搜索网络结果',
  };
}

enum MostUsedTargetKind { contact, chatRecord, circle }

class MostUsedSearchItem {
  const MostUsedSearchItem({
    required this.itemId,
    required this.targetKind,
    required this.title,
    required this.subtitle,
    this.avatarUrl,
    this.avatarCompositeUrls = const <String>[],
    this.conversationId,
    this.conversationType,
    this.circleId,
    this.messageAnchorId,
    this.timestamp,
    this.matchCount = 0,
    this.usageScore = 0,
  });

  final String itemId;
  final MostUsedTargetKind targetKind;
  final String title;
  final String subtitle;
  final String? avatarUrl;
  final List<String> avatarCompositeUrls;
  final String? conversationId;
  final String? conversationType;
  final String? circleId;
  final String? messageAnchorId;
  final DateTime? timestamp;
  final int matchCount;
  final int usageScore;
}

class ContactSearchSuggestion {
  const ContactSearchSuggestion({
    required this.contactId,
    required this.displayName,
    required this.conversationId,
    this.avatarUrl,
    this.subtitle,
  });

  final String contactId;
  final String displayName;
  final String conversationId;
  final String? avatarUrl;
  final String? subtitle;
}

class ChatRecordSearchSuggestion {
  const ChatRecordSearchSuggestion({
    required this.conversationId,
    required this.conversationTitle,
    required this.conversationType,
    required this.matchedPreview,
    required this.matchCount,
    this.avatarUrl,
    this.avatarCompositeUrls = const <String>[],
    this.messageAnchorId,
    this.timestamp,
  });

  final String conversationId;
  final String conversationTitle;
  final String conversationType;
  final String matchedPreview;
  final int matchCount;
  final String? avatarUrl;
  final List<String> avatarCompositeUrls;
  final String? messageAnchorId;
  final DateTime? timestamp;
}

class NetworkSearchSuggestion {
  const NetworkSearchSuggestion({
    required this.query,
    this.title,
    this.subtitle,
    this.initialTabId,
  });

  final String query;
  final String? title;
  final String? subtitle;
  final String? initialTabId;

  String get displayTitle => title ?? query;
}

enum SearchSuggestionEntryKind {
  mostUsed,
  contact,
  chatRecord,
  circle,
  network,
}

class SearchSuggestionEntry {
  const SearchSuggestionEntry._({required this.kind, required this.payload});

  final SearchSuggestionEntryKind kind;
  final Object payload;

  const SearchSuggestionEntry.mostUsed(MostUsedSearchItem value)
    : this._(kind: SearchSuggestionEntryKind.mostUsed, payload: value);
  const SearchSuggestionEntry.contact(ContactSearchSuggestion value)
    : this._(kind: SearchSuggestionEntryKind.contact, payload: value);
  const SearchSuggestionEntry.chatRecord(ChatRecordSearchSuggestion value)
    : this._(kind: SearchSuggestionEntryKind.chatRecord, payload: value);
  const SearchSuggestionEntry.circle(CircleSearchItemView value)
    : this._(kind: SearchSuggestionEntryKind.circle, payload: value);
  const SearchSuggestionEntry.network(NetworkSearchSuggestion value)
    : this._(kind: SearchSuggestionEntryKind.network, payload: value);

  T cast<T>() => payload as T;
}

class SearchSuggestionSection {
  const SearchSuggestionSection({
    required this.kind,
    required this.items,
    this.expanded = false,
    this.collapsedItemCount,
    this.moreLabel,
    this.titleOverride,
  });

  final SearchSuggestionSectionKind kind;
  final List<SearchSuggestionEntry> items;
  final bool expanded;
  final int? collapsedItemCount;
  final String? moreLabel;
  final String? titleOverride;

  String get title => titleOverride ?? kind.title;

  List<SearchSuggestionEntry> get visibleItems {
    final limit = collapsedItemCount;
    if (expanded || limit == null || items.length <= limit) {
      return items;
    }
    return items.take(limit).toList(growable: false);
  }

  bool get showsMoreEntry {
    final limit = collapsedItemCount;
    return !expanded && limit != null && items.length > limit;
  }

  SearchSuggestionSection copyWith({
    SearchSuggestionSectionKind? kind,
    List<SearchSuggestionEntry>? items,
    bool? expanded,
    int? collapsedItemCount,
    String? moreLabel,
    String? titleOverride,
  }) {
    return SearchSuggestionSection(
      kind: kind ?? this.kind,
      items: items ?? this.items,
      expanded: expanded ?? this.expanded,
      collapsedItemCount: collapsedItemCount ?? this.collapsedItemCount,
      moreLabel: moreLabel ?? this.moreLabel,
      titleOverride: titleOverride ?? this.titleOverride,
    );
  }
}

class SearchSessionState {
  const SearchSessionState({
    required this.launchContext,
    this.query = '',
    this.scope = SearchScope.all,
    this.selection = const SearchObjectSelection(),
    this.suggestionSections = const <SearchSuggestionSection>[],
    this.recentSearches = const <RecentSearchEntryView>[],
    this.isLoading = false,
    this.isHydratingHistory = false,
    this.isManagingHistory = false,
    this.isHistoryExpanded = false,
    this.areContactsExpanded = false,
    this.areChatRecordsExpanded = false,
  });

  final SearchLaunchContext launchContext;
  final String query;
  final SearchScope scope;
  final SearchObjectSelection selection;
  final List<SearchSuggestionSection> suggestionSections;
  final List<RecentSearchEntryView> recentSearches;
  final bool isLoading;
  final bool isHydratingHistory;
  final bool isManagingHistory;
  final bool isHistoryExpanded;
  final bool areContactsExpanded;
  final bool areChatRecordsExpanded;

  bool get hasQuery => query.trim().isNotEmpty;
  SearchViewMode get viewMode {
    if (hasQuery) {
      return SearchViewMode.liveSuggestions;
    }
    return isManagingHistory
        ? SearchViewMode.historyManage
        : SearchViewMode.historyBrowse;
  }

  SearchSessionState copyWith({
    SearchLaunchContext? launchContext,
    String? query,
    SearchScope? scope,
    SearchObjectSelection? selection,
    List<SearchSuggestionSection>? suggestionSections,
    List<RecentSearchEntryView>? recentSearches,
    bool? isLoading,
    bool? isHydratingHistory,
    bool? isManagingHistory,
    bool? isHistoryExpanded,
    bool? areContactsExpanded,
    bool? areChatRecordsExpanded,
  }) {
    return SearchSessionState(
      launchContext: launchContext ?? this.launchContext,
      query: query ?? this.query,
      scope: scope ?? this.scope,
      selection: selection ?? this.selection,
      suggestionSections: suggestionSections ?? this.suggestionSections,
      recentSearches: recentSearches ?? this.recentSearches,
      isLoading: isLoading ?? this.isLoading,
      isHydratingHistory: isHydratingHistory ?? this.isHydratingHistory,
      isManagingHistory: isManagingHistory ?? this.isManagingHistory,
      isHistoryExpanded: isHistoryExpanded ?? this.isHistoryExpanded,
      areContactsExpanded: areContactsExpanded ?? this.areContactsExpanded,
      areChatRecordsExpanded:
          areChatRecordsExpanded ?? this.areChatRecordsExpanded,
    );
  }
}

DateTime? _parseDateTime(dynamic value) {
  if (value is DateTime) {
    return value;
  }
  if (value is String && value.trim().isNotEmpty) {
    return DateTime.tryParse(value);
  }
  return null;
}

int? _parseInt(dynamic value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String && value.trim().isNotEmpty) {
    return int.tryParse(value);
  }
  return null;
}

List<String>? _parseStringList(dynamic value) {
  if (value is List) {
    return value.map((item) => item.toString()).toList(growable: false);
  }
  return null;
}
