import 'package:flutter/foundation.dart' show ValueGetter, setEquals;

export 'package:quwoquan_app/core/models/search_hit_payload.dart';
export 'package:quwoquan_app/core/models/search_post_item_view.dart';
export 'package:quwoquan_app/cloud/runtime/generated/circle/circle_search_views.dart';
export 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show LocationPoiDto;
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_search_views.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/recent_search_entry_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relationship_capability_wire_dto.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        LocationPoiDto,
        SocialRelationSearchItemProjection,
        SocialRelationshipCapabilityProjection;
part 'search_models_presentation.dart';
part 'search_models_selection.dart';

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
    SearchScope.all => SearchText.searchAllTab,
    SearchScope.content => SearchText.searchScopeContent,
    SearchScope.socialRelation => SearchText.searchScopeSocialRelation,
    SearchScope.messages => SearchText.searchScopeMessages,
    SearchScope.circles => SearchText.searchScopeDiscussions,
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
    SearchObjectTarget.contacts => SearchText.searchTargetContacts,
    SearchObjectTarget.directChats => SearchText.searchTargetDirectChats,
    SearchObjectTarget.groupChats => SearchText.searchTargetGroupChats,
    SearchObjectTarget.circles => SearchText.searchScopeDiscussions,
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
  micro;

  String get wireValue => switch (this) {
    SearchContentTypeFilter.article => 'article',
    SearchContentTypeFilter.image => 'image',
    SearchContentTypeFilter.video => 'video',
    SearchContentTypeFilter.micro => 'micro',
  };

  String get label => switch (this) {
    SearchContentTypeFilter.article => SearchText.searchContentTypeArticle,
    SearchContentTypeFilter.image => SearchText.searchCategoryImage,
    SearchContentTypeFilter.video => SearchText.searchCategoryVideo,
    SearchContentTypeFilter.micro => SearchText.searchContentTypeMicro,
  };

  String get identity => switch (this) {
    SearchContentTypeFilter.micro => 'moment',
    SearchContentTypeFilter.article ||
    SearchContentTypeFilter.image ||
    SearchContentTypeFilter.video => 'work',
  };

  String get contentType => switch (this) {
    SearchContentTypeFilter.article => 'article',
    SearchContentTypeFilter.image => 'image',
    SearchContentTypeFilter.video => 'video',
    SearchContentTypeFilter.micro => 'micro',
  };

  static SearchContentTypeFilter? fromWire(String raw) {
    switch (raw.trim()) {
      case 'article':
        return SearchContentTypeFilter.article;
      case 'image':
        return SearchContentTypeFilter.image;
      case 'video':
        return SearchContentTypeFilter.video;
      case 'micro':
        return SearchContentTypeFilter.micro;
      default:
        return null;
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

  factory SocialRelationshipCapabilityView.fromProjection(
    SocialRelationshipCapabilityProjection projection,
  ) {
    return SocialRelationshipCapabilityView(
      relationState: projection.relationState,
      canFollow: projection.canFollow,
      canUnfollow: projection.canUnfollow,
      canOpenConversation: projection.canOpenConversation,
      canStartVoiceCall: projection.canStartVoiceCall,
      canStartVideoCall: projection.canStartVideoCall,
    );
  }
}

class SocialRelationSearchItemView {
  const SocialRelationSearchItemView({
    required this.subAccountId,
    required this.username,
    required this.displayName,
    this.avatarUrl,
    this.avatarVersion = 0,
    this.headline,
    required this.chatAvailable,
    required this.relationshipCapability,
  });

  final String subAccountId;
  final String username;
  final String displayName;
  final String? avatarUrl;
  final int avatarVersion;
  final String? headline;
  final bool chatAvailable;
  final SocialRelationshipCapabilityView relationshipCapability;

  factory SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
    SocialRelationSearchItemWireDto w,
  ) {
    final subAccountId = w.subAccountId;
    final displayName = w.displayName.isNotEmpty ? w.displayName : subAccountId;
    final username = w.username.isNotEmpty ? w.username : subAccountId;
    final capView =
        SocialRelationshipCapabilityView.fromSocialRelationshipCapabilityWire(
          w.relationshipCapability ?? SocialRelationshipCapabilityWireDto(),
        );
    return SocialRelationSearchItemView(
      subAccountId: subAccountId,
      username: username,
      displayName: displayName,
      avatarUrl: w.avatarUrl == null
          ? null
          : resolveAvatarImageUrl(w.avatarUrl, avatarVersion: w.avatarVersion),
      avatarVersion: w.avatarVersion,
      headline: w.headline,
      chatAvailable: capView.canOpenConversation,
      relationshipCapability: capView,
    );
  }

  factory SocialRelationSearchItemView.fromProjection(
    SocialRelationSearchItemProjection projection,
  ) {
    final subAccountId = projection.subAccountId;
    final displayName = projection.displayName.isNotEmpty
        ? projection.displayName
        : subAccountId;
    final username = projection.username.isNotEmpty
        ? projection.username
        : (projection.userHandle.isNotEmpty
              ? projection.userHandle
              : subAccountId);
    final capability = projection.relationshipCapability;
    final capView = capability == null
        ? const SocialRelationshipCapabilityView(
            relationState: 'not_following',
            canFollow: false,
            canUnfollow: false,
            canOpenConversation: false,
            canStartVoiceCall: false,
            canStartVideoCall: false,
          )
        : SocialRelationshipCapabilityView.fromProjection(capability);
    return SocialRelationSearchItemView(
      subAccountId: subAccountId,
      username: username,
      displayName: displayName,
      avatarUrl: projection.avatarUrl == null
          ? null
          : resolveAvatarImageUrl(
              projection.avatarUrl,
              avatarVersion: projection.avatarVersion,
            ),
      avatarVersion: projection.avatarVersion,
      headline: projection.headline,
      chatAvailable: projection.chatAvailable || capView.canOpenConversation,
      relationshipCapability: capView,
    );
  }
}

/// 联系人本地检索结果行（chat 本地检索单轨 ViewModel）。
///
/// 历史上曾是 `SearchContacts` 云端 operation 的 generated wire DTO；
/// B5 收敛为本地 sqlite 检索单轨后随 operation 一并去 wire 化，保留类名
/// 以稳定本地检索链（record/hit payload/coordinator）的类型引用。
class ChatContactSearchItemDto {
  const ChatContactSearchItemDto({
    this.contactId = '',
    this.displayName = '',
    this.avatarUrl,
    this.conversationId,
    this.conversationType,
    this.source,
    this.subtitle,
    this.highlightText,
    this.matchedField,
  });

  final String contactId;
  final String displayName;
  final String? avatarUrl;
  final String? conversationId;
  final String? conversationType;
  final String? source;
  final String? subtitle;
  final String? highlightText;
  final String? matchedField;

  ChatContactSearchItemDto copyWith({
    String? contactId,
    String? displayName,
    String? avatarUrl,
    String? conversationId,
    String? conversationType,
    String? source,
    String? subtitle,
    String? highlightText,
    String? matchedField,
  }) {
    return ChatContactSearchItemDto(
      contactId: contactId ?? this.contactId,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      conversationId: conversationId ?? this.conversationId,
      conversationType: conversationType ?? this.conversationType,
      source: source ?? this.source,
      subtitle: subtitle ?? this.subtitle,
      highlightText: highlightText ?? this.highlightText,
      matchedField: matchedField ?? this.matchedField,
    );
  }

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'contactId': contactId,
      'displayName': displayName,
      'avatarUrl': avatarUrl,
      'conversationId': conversationId,
      'conversationType': conversationType,
      'source': source,
      'subtitle': subtitle,
      'highlightText': highlightText,
      'matchedField': matchedField,
    };
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

  Map<String, Object?> toMap() => <String, Object?>{
    'conversationId': conversationId,
    'type': type,
    'title': title,
    if (avatarUrl != null) 'avatarUrl': avatarUrl,
    if (lastMessagePreview != null) 'lastMessagePreview': lastMessagePreview,
    if (lastMessageTime != null)
      'lastMessageTime': lastMessageTime!.toUtc().toIso8601String(),
    'memberCount': memberCount,
    if (circleId != null) 'circleId': circleId,
    if (circleGroupId != null) 'circleGroupId': circleGroupId,
    if (highlightText != null) 'highlightText': highlightText,
    if (matchedField != null) 'matchedField': matchedField,
  };
}

class MessageSearchItemView {
  const MessageSearchItemView({
    required this.messageId,
    required this.conversationId,
    this.conversationTitle,
    this.conversationAvatarUrl,
    this.senderPersonaId,
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
  final String? senderPersonaId;
  final String? senderDisplayName;
  final String? senderAvatarUrl;
  final String messageType;
  final String contentPreview;
  final int? seq;
  final DateTime timestamp;
  final String? highlightText;
  final String? matchedField;

  Map<String, Object?> toMap() => <String, Object?>{
    'messageId': messageId,
    'conversationId': conversationId,
    if (conversationTitle != null) 'conversationTitle': conversationTitle,
    if (conversationAvatarUrl != null)
      'conversationAvatarUrl': conversationAvatarUrl,
    if (senderPersonaId != null) 'senderPersonaId': senderPersonaId,
    if (senderDisplayName != null) 'senderDisplayName': senderDisplayName,
    if (senderAvatarUrl != null) 'senderAvatarUrl': senderAvatarUrl,
    'messageType': messageType,
    'contentPreview': contentPreview,
    if (seq != null) 'seq': seq,
    'timestamp': timestamp.toUtc().toIso8601String(),
    if (highlightText != null) 'highlightText': highlightText,
    if (matchedField != null) 'matchedField': matchedField,
  };
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
