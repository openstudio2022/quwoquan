import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/search_location_suggestion_view.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';

enum SearchSuggestionSectionKind {
  contacts,
  chatRecords,
  circles,
  locations,
  followedPeople,
  network;

  String get title => switch (this) {
    SearchSuggestionSectionKind.contacts => '联系人',
    SearchSuggestionSectionKind.chatRecords => '聊天记录',
    SearchSuggestionSectionKind.circles => '已加入圈子',
    SearchSuggestionSectionKind.locations => '已关注地点',
    SearchSuggestionSectionKind.followedPeople => '人',
    SearchSuggestionSectionKind.network => '搜索网络结果',
  };
}

class ContactSearchSuggestion {
  const ContactSearchSuggestion({
    required this.contactId,
    required this.userHandle,
    required this.displayName,
    required this.conversationId,
    this.avatarUrl,
    this.subtitle,
  });

  final String contactId;
  final String userHandle;
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
    this.homepageId,
    this.coverUrl,
    this.coverAssetId,
    this.coverAccessMode,
  });

  final String query;
  final String? title;
  final String? subtitle;
  final String? initialTabId;
  final String? homepageId;
  final String? coverUrl;

  /// 主页封面的配对资产标识与交付访问模式（DEC-033）；research 相位
  /// 的 coverUrl 是相对私有 CAS 引用，按 coverAssetId 换短签。
  final String? coverAssetId;
  final MediaDeliveryAccessMode? coverAccessMode;

  String get displayTitle => title ?? query;
  bool get isHomepagePreview => homepageId?.trim().isNotEmpty == true;
}

class SearchHighlightSpan {
  const SearchHighlightSpan({required this.text, this.isMatch = false});

  final String text;
  final bool isMatch;

  static List<SearchHighlightSpan> build({
    required String text,
    required String keyword,
  }) {
    final source = text;
    final query = keyword.trim();
    if (source.isEmpty || query.isEmpty) {
      return <SearchHighlightSpan>[SearchHighlightSpan(text: source)];
    }
    final lowerSource = source.toLowerCase();
    final lowerQuery = query.toLowerCase();
    final spans = <SearchHighlightSpan>[];
    var cursor = 0;
    while (cursor < source.length) {
      final index = lowerSource.indexOf(lowerQuery, cursor);
      if (index < 0) {
        spans.add(SearchHighlightSpan(text: source.substring(cursor)));
        break;
      }
      if (index > cursor) {
        spans.add(SearchHighlightSpan(text: source.substring(cursor, index)));
      }
      final end = index + query.length;
      spans.add(
        SearchHighlightSpan(text: source.substring(index, end), isMatch: true),
      );
      cursor = end;
    }
    return spans.where((span) => span.text.isNotEmpty).toList(growable: false);
  }
}

enum SearchSuggestionEntryKind {
  contact,
  chatRecord,
  circle,
  location,
  followedPerson,
  network,
}

class SearchSuggestionEntry {
  const SearchSuggestionEntry._({required this.kind, required this.payload});

  final SearchSuggestionEntryKind kind;
  final Object payload;

  const SearchSuggestionEntry.contact(ContactSearchSuggestion value)
    : this._(kind: SearchSuggestionEntryKind.contact, payload: value);
  const SearchSuggestionEntry.chatRecord(ChatRecordSearchSuggestion value)
    : this._(kind: SearchSuggestionEntryKind.chatRecord, payload: value);
  const SearchSuggestionEntry.circle(CircleSearchHitViewData value)
    : this._(kind: SearchSuggestionEntryKind.circle, payload: value);
  const SearchSuggestionEntry.location(SearchLocationSuggestionViewData value)
    : this._(kind: SearchSuggestionEntryKind.location, payload: value);
  const SearchSuggestionEntry.followedPerson(
    SocialRelationSearchItemViewData value,
  ) : this._(kind: SearchSuggestionEntryKind.followedPerson, payload: value);
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
