import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show setEquals;

export 'package:quwoquan_app/core/models/search_hit_payload.dart';
export 'package:quwoquan_app/cloud/runtime/generated/content/post_search_item_view_dto.g.dart';
export 'package:quwoquan_app/cloud/runtime/generated/circle/circle_search_views.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_search_views.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/recent_search_entry_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relationship_capability_wire_dto.g.dart';

/// 与集合迭代顺序无关的稳定 hash（用于 [SearchObjectSelection.hashCode]）。
int _enumIndexSetHash<T extends Enum>(Set<T> values) {
  if (values.isEmpty) {
    return 0;
  }
  final indices = values.map((e) => e.index).toList()..sort();
  return Object.hashAll(indices);
}

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
      final targets = rawTargets
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

  static SearchObjectSelection fromSearchScope(SearchScope scope) {
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

  /// Riverpod `family` 等场景：内容相同即同一键，避免父组件 rebuild 时重复创建 provider。
  @override
  bool operator ==(Object other) {
    if (identical(this, other)) {
      return true;
    }
    return other is SearchObjectSelection &&
        setEquals(targets, other.targets) &&
        setEquals(contentTypes, other.contentTypes);
  }

  @override
  int get hashCode =>
      Object.hash(_enumIndexSetHash(targets), _enumIndexSetHash(contentTypes));
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

  /// 与 [SearchObjectSelection] 一致：值相等则 `searchCoordinatorProvider` family 复用同一实例。
  @override
  bool operator ==(Object other) {
    if (identical(this, other)) {
      return true;
    }
    return other is SearchLaunchContext &&
        entrySurfaceId == other.entrySurfaceId &&
        initialScope == other.initialScope &&
        searchObjectSelection == other.searchObjectSelection &&
        prefilledQuery == other.prefilledQuery &&
        restoreState == other.restoreState &&
        initialFacet == other.initialFacet &&
        initialNetworkTabId == other.initialNetworkTabId;
  }

  @override
  int get hashCode => Object.hash(
    entrySurfaceId,
    initialScope,
    searchObjectSelection,
    prefilledQuery,
    restoreState,
    initialFacet,
    initialNetworkTabId,
  );
}

class SearchConversationAnchorContext {
  const SearchConversationAnchorContext({
    required this.messageAnchorId,
    this.sourceQuery,
  });

  final String messageAnchorId;
  final String? sourceQuery;
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

  factory SocialRelationshipCapabilityView.fromSocialRelationshipCapabilityWire(
    SocialRelationshipCapabilityWireDto w,
  ) {
    return SocialRelationshipCapabilityView(
      relationState: w.relationState,
      canFollow: w.canFollow,
      canUnfollow: w.canUnfollow,
      canOpenConversation: w.canOpenConversation,
      canStartVoiceCall: w.canStartVoiceCall,
      canStartVideoCall: w.canStartVideoCall,
    );
  }

  factory SocialRelationshipCapabilityView.fromMap(Map<String, dynamic> map) {
    return SocialRelationshipCapabilityView.fromSocialRelationshipCapabilityWire(
      SocialRelationshipCapabilityWireDto.fromMap(map),
    );
  }
}

class SocialRelationSearchItemView {
  const SocialRelationSearchItemView({
    required this.subAccountId,
    required this.username,
    required this.displayName,
    this.avatarUrl,
    this.headline,
    required this.chatAvailable,
    required this.relationshipCapability,
  });

  final String subAccountId;
  final String username;
  final String displayName;
  final String? avatarUrl;
  final String? headline;
  final bool chatAvailable;
  final SocialRelationshipCapabilityView relationshipCapability;

  /// [row] 为整行 JSON（与 [SocialRelationSearchItemWireDto.fromMap] 同源），用于 capability 嵌套缺失时回退。
  factory SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
    SocialRelationSearchItemWireDto w,
    Map<String, dynamic> row,
  ) {
    final subAccountId = w.subAccountId;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : subAccountId;
    final username = w.username.isNotEmpty ? w.username : subAccountId;
    final nested = w.relationshipCapability;
    final Map<String, dynamic> effectiveCap =
        (nested != null && nested.isNotEmpty)
        ? Map<String, dynamic>.from(nested)
        : row;
    final cap = SocialRelationshipCapabilityWireDto.fromMap(effectiveCap);
    final canOpen = cap.canOpenConversation || w.chatAvailable;
    final capView = SocialRelationshipCapabilityView(
      relationState: cap.relationState,
      canFollow: cap.canFollow,
      canUnfollow: cap.canUnfollow,
      canOpenConversation: canOpen,
      canStartVoiceCall: cap.canStartVoiceCall,
      canStartVideoCall: cap.canStartVideoCall,
    );
    return SocialRelationSearchItemView(
      subAccountId: subAccountId,
      username: username,
      displayName: displayName,
      avatarUrl: w.avatarUrl,
      headline: w.headline,
      chatAvailable: w.chatAvailable || capView.canOpenConversation,
      relationshipCapability: capView,
    );
  }

  factory SocialRelationSearchItemView.fromMap(Map<String, dynamic> map) {
    return SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
      SocialRelationSearchItemWireDto.fromMap(map),
      map,
    );
  }
}

class ConversationSearchItemView {
  const ConversationSearchItemView({
    required this.conversationId,
    required this.type,
    required this.title,
    this.avatarUrl,
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
      avatarUrl: _optionalString(map['avatarUrl']),
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
    this.senderSubAccountId,
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
  final String? senderSubAccountId;
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
      senderSubAccountId:
          (map['senderSubAccountId'] ??
                  map['senderProfileSubjectId'] ??
                  map['senderId'])
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

  factory RecentSearchEntryView.fromRecentSearchEntryWire(
    RecentSearchEntryWireDto w,
  ) {
    final query = w.query.trim();
    final scope = SearchScope.fromWire(w.scope);
    final facetRaw = w.facet;
    final facetTrim = facetRaw?.trim();
    return RecentSearchEntryView(
      entryId: w.entryId.trim().isNotEmpty
          ? w.entryId.trim()
          : buildEntryId(query: query, scope: scope, facet: facetTrim),
      query: query,
      scope: scope,
      facet: facetTrim?.isEmpty == true ? null : facetTrim,
      updatedAt: w.updatedAt ?? DateTime.now(),
    );
  }

  factory RecentSearchEntryView.fromMap(Map<String, dynamic> map) {
    return RecentSearchEntryView.fromRecentSearchEntryWire(
      RecentSearchEntryWireDto.fromMap(map),
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
    this.messageAnchorId,
    this.timestamp,
  });

  final String conversationId;
  final String conversationTitle;
  final String conversationType;
  final String matchedPreview;
  final int matchCount;
  final String? avatarUrl;
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

String? _optionalString(Object? value) {
  final s = value?.toString().trim() ?? '';
  return s.isEmpty ? null : s;
}

DateTime? _parseDateTime(Object? value) {
  if (value is DateTime) {
    return value;
  }
  if (value is String && value.trim().isNotEmpty) {
    return DateTime.tryParse(value);
  }
  return null;
}
