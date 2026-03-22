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
    SearchScope.circles => '圈子',
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

class SearchLaunchContext {
  const SearchLaunchContext({
    required this.entrySurfaceId,
    this.initialScope = SearchScope.all,
    this.prefilledQuery = '',
    this.restoreState = true,
    this.initialFacet,
  });

  final String entrySurfaceId;
  final SearchScope initialScope;
  final String prefilledQuery;
  final bool restoreState;
  final String? initialFacet;

  SearchLaunchContext copyWith({
    String? entrySurfaceId,
    SearchScope? initialScope,
    String? prefilledQuery,
    bool? restoreState,
    String? initialFacet,
  }) {
    return SearchLaunchContext(
      entrySurfaceId: entrySurfaceId ?? this.entrySurfaceId,
      initialScope: initialScope ?? this.initialScope,
      prefilledQuery: prefilledQuery ?? this.prefilledQuery,
      restoreState: restoreState ?? this.restoreState,
      initialFacet: initialFacet ?? this.initialFacet,
    );
  }
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
  final String? highlightText;
  final String? matchedField;
  final DateTime? publishedAt;

  factory PostSearchItemView.fromMap(Map<String, dynamic> map) {
    return PostSearchItemView(
      postId:
          (map['postId'] ?? map['id'] ?? map['_id'] ?? '').toString().trim(),
      contentType:
          (map['contentType'] ?? map['type'] ?? 'image').toString().trim(),
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
              (map['relationState'] ?? map['relationshipState'] ?? 'not_following')
                  .toString(),
          'canFollow': map['canFollow'] == true,
          'canUnfollow': map['canUnfollow'] == true,
          'canOpenConversation':
              map['canOpenConversation'] == true || map['chatAvailable'] == true,
          'canStartVoiceCall': map['canStartVoiceCall'] == true,
          'canStartVideoCall': map['canStartVideoCall'] == true,
        };
    final profileSubjectId =
        (map['profileSubjectId'] ?? map['userId'] ?? '').toString().trim();
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
      relationshipCapability:
          SocialRelationshipCapabilityView.fromMap(capabilityMap),
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
  final String? highlightText;
  final String? matchedField;

  factory ConversationSearchItemView.fromMap(Map<String, dynamic> map) {
    return ConversationSearchItemView(
      conversationId:
          (map['conversationId'] ?? map['id'] ?? map['_id'] ?? '')
              .toString()
              .trim(),
      type: (map['type'] ?? 'direct').toString().trim(),
      title: (map['title'] ?? map['conversationTitle'] ?? '').toString().trim(),
      avatarUrl: map['avatarUrl']?.toString(),
      avatarCompositeUrls: _parseStringList(
            map['avatarCompositeUrls'] ?? map['memberAvatars'],
          ) ??
          const <String>[],
      lastMessagePreview:
          (map['lastMessagePreview'] ?? map['highlightText'])?.toString(),
      lastMessageTime: _parseDateTime(map['lastMessageTime']),
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      circleId: map['circleId']?.toString(),
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
      messageId:
          (map['messageId'] ?? map['id'] ?? map['_id'] ?? '').toString().trim(),
      conversationId:
          (map['conversationId'] ?? '').toString().trim(),
      conversationTitle: map['conversationTitle']?.toString(),
      conversationAvatarUrl: map['conversationAvatarUrl']?.toString(),
      senderProfileSubjectId:
          (map['senderProfileSubjectId'] ?? map['senderId'])?.toString(),
      senderDisplayName:
          (map['senderDisplayName'] ??
                  map['senderDisplayNameSnapshot'] ??
                  map['senderName'])
              ?.toString(),
      senderAvatarUrl:
          (map['senderAvatarUrl'] ?? map['senderAvatarUrlSnapshot'])
              ?.toString(),
      messageType:
          (map['messageType'] ?? map['type'] ?? 'text').toString().trim(),
      contentPreview:
          (map['contentPreview'] ?? map['content'] ?? '').toString().trim(),
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
    required this.memberCount,
    required this.postCount,
    this.highlightText,
    this.matchedField,
  });

  final String circleId;
  final String name;
  final String? description;
  final String? coverUrl;
  final String? categoryId;
  final String? subCategory;
  final String? domainId;
  final int memberCount;
  final int postCount;
  final String? highlightText;
  final String? matchedField;

  factory CircleSearchItemView.fromMap(Map<String, dynamic> map) {
    return CircleSearchItemView(
      circleId:
          (map['circleId'] ?? map['id'] ?? map['_id'] ?? '').toString().trim(),
      name: (map['name'] ?? '').toString().trim(),
      description: map['description']?.toString(),
      coverUrl: (map['coverUrl'] ?? map['cover'])?.toString(),
      categoryId:
          (map['categoryId'] ?? map['category'])?.toString(),
      subCategory: map['subCategory']?.toString(),
      domainId: map['domainId']?.toString(),
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      postCount: (map['postCount'] as num?)?.toInt() ?? 0,
      highlightText: map['highlightText']?.toString(),
      matchedField: map['matchedField']?.toString(),
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
      label:
          (map['label'] ?? map['subCategory'] ?? map['categoryId'] ?? '')
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
      items: itemMaps
          .map(CircleSearchItemView.fromMap)
          .toList(growable: false),
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

enum SearchSectionKind {
  content,
  socialRelation,
  messages,
  circles,
  circleFacets;

  String get title => switch (this) {
    SearchSectionKind.content => '内容',
    SearchSectionKind.socialRelation => '社交关系',
    SearchSectionKind.messages => '聊天',
    SearchSectionKind.circles => '圈子',
    SearchSectionKind.circleFacets => '频道',
  };
}

enum SearchResultItemKind {
  post,
  socialRelation,
  conversation,
  message,
  circle,
  circleFacet,
}

class SearchResultItem {
  const SearchResultItem._({required this.kind, required this.payload});

  final SearchResultItemKind kind;
  final Object payload;

  const SearchResultItem.post(PostSearchItemView value)
    : this._(kind: SearchResultItemKind.post, payload: value);
  const SearchResultItem.socialRelation(SocialRelationSearchItemView value)
    : this._(kind: SearchResultItemKind.socialRelation, payload: value);
  const SearchResultItem.conversation(ConversationSearchItemView value)
    : this._(kind: SearchResultItemKind.conversation, payload: value);
  const SearchResultItem.message(MessageSearchItemView value)
    : this._(kind: SearchResultItemKind.message, payload: value);
  const SearchResultItem.circle(CircleSearchItemView value)
    : this._(kind: SearchResultItemKind.circle, payload: value);
  const SearchResultItem.circleFacet(CircleFacetBucketView value)
    : this._(kind: SearchResultItemKind.circleFacet, payload: value);

  T cast<T>() => payload as T;
}

class SearchSection {
  const SearchSection({
    required this.kind,
    required this.items,
    this.degraded = false,
    this.errorMessage,
  });

  final SearchSectionKind kind;
  final List<SearchResultItem> items;
  final bool degraded;
  final String? errorMessage;

  String get title => kind.title;
}

class SearchSessionState {
  const SearchSessionState({
    required this.launchContext,
    this.query = '',
    this.scope = SearchScope.all,
    this.selectedFacet,
    this.sections = const <SearchSection>[],
    this.recentSearches = const <RecentSearchEntryView>[],
    this.isLoading = false,
    this.isHydratingHistory = false,
    this.isVoiceRunning = false,
  });

  final SearchLaunchContext launchContext;
  final String query;
  final SearchScope scope;
  final String? selectedFacet;
  final List<SearchSection> sections;
  final List<RecentSearchEntryView> recentSearches;
  final bool isLoading;
  final bool isHydratingHistory;
  final bool isVoiceRunning;

  bool get hasQuery => query.trim().isNotEmpty;
  bool get isLanding => !hasQuery;

  SearchSessionState copyWith({
    SearchLaunchContext? launchContext,
    String? query,
    SearchScope? scope,
    ValueGetter<String?>? selectedFacet,
    List<SearchSection>? sections,
    List<RecentSearchEntryView>? recentSearches,
    bool? isLoading,
    bool? isHydratingHistory,
    bool? isVoiceRunning,
  }) {
    return SearchSessionState(
      launchContext: launchContext ?? this.launchContext,
      query: query ?? this.query,
      scope: scope ?? this.scope,
      selectedFacet: selectedFacet != null ? selectedFacet() : this.selectedFacet,
      sections: sections ?? this.sections,
      recentSearches: recentSearches ?? this.recentSearches,
      isLoading: isLoading ?? this.isLoading,
      isHydratingHistory: isHydratingHistory ?? this.isHydratingHistory,
      isVoiceRunning: isVoiceRunning ?? this.isVoiceRunning,
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

List<String>? _parseStringList(dynamic value) {
  if (value is List) {
    return value.map((item) => item.toString()).toList(growable: false);
  }
  return null;
}
