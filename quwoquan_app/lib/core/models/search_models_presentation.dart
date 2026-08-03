part of 'search_models.dart';

enum SearchViewMode { historyBrowse, historyManage, liveSuggestions }

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
  });

  final String query;
  final String? title;
  final String? subtitle;
  final String? initialTabId;
  final String? homepageId;
  final String? coverUrl;

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

class SearchHomeState {
  const SearchHomeState({
    this.history = const <RecentSearchEntryView>[],
    this.guessKeywords = const <NetworkSearchSuggestion>[],
    this.discoverCircles = const <SearchInspirationCardView>[],
    this.discoverLocations = const <SearchInspirationCardView>[],
  });

  final List<RecentSearchEntryView> history;
  final List<NetworkSearchSuggestion> guessKeywords;
  final List<SearchInspirationCardView> discoverCircles;
  final List<SearchInspirationCardView> discoverLocations;
}

class SearchLocalMatchesState {
  const SearchLocalMatchesState({
    this.contacts = const <SearchSuggestionEntry>[],
    this.chatRecords = const <SearchSuggestionEntry>[],
    this.circles = const <SearchSuggestionEntry>[],
    this.places = const <SearchSuggestionEntry>[],
    this.people = const <SearchSuggestionEntry>[],
    this.keywordTerms = const <SearchSuggestionEntry>[],
  });

  final List<SearchSuggestionEntry> contacts;
  final List<SearchSuggestionEntry> chatRecords;
  final List<SearchSuggestionEntry> circles;
  final List<SearchSuggestionEntry> places;
  final List<SearchSuggestionEntry> people;
  final List<SearchSuggestionEntry> keywordTerms;
}

enum UnifiedSearchResultItemKind {
  intersection,
  circle,
  place,
  person,
  article,
  image,
  video,
  relatedSearchTerms,
}

class RelatedSearchTermCardView {
  const RelatedSearchTermCardView({required this.terms});

  final List<NetworkSearchSuggestion> terms;

  RelatedSearchTermCardView limited() {
    return RelatedSearchTermCardView(
      terms: terms.take(5).toList(growable: false),
    );
  }
}

class UnifiedSearchResultStream {
  const UnifiedSearchResultStream({
    this.connectedGroups = const <Object>[],
    this.globalMixedGroups = const <Object>[],
    this.tabSpecificCollections = const <String, List<Object>>{},
  });

  final List<Object> connectedGroups;
  final List<Object> globalMixedGroups;
  final Map<String, List<Object>> tabSpecificCollections;
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
  const SearchSuggestionEntry.followedPerson(SocialRelationSearchItemViewData value)
    : this._(kind: SearchSuggestionEntryKind.followedPerson, payload: value);
  const SearchSuggestionEntry.network(NetworkSearchSuggestion value)
    : this._(kind: SearchSuggestionEntryKind.network, payload: value);

  T cast<T>() => payload as T;
}

/// 搜索页自有的位置建议模型；Integration POI 与 Search place 投影在此汇合，
/// 不用伪造经纬度把后者冒充 Cloud `LocationPoi`。
final class SearchLocationSuggestionViewData {
  const SearchLocationSuggestionViewData({
    required this.id,
    required this.name,
    this.address,
  });

  factory SearchLocationSuggestionViewData.fromWire(LocationPoi wire) =>
      SearchLocationSuggestionViewData(
        id: wire.id,
        name: wire.name,
        address: wire.address,
      );

  final String id;
  final String name;
  final String? address;
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

class SearchInspirationChipView {
  const SearchInspirationChipView({
    required this.title,
    required this.subtitle,
    this.query,
  });

  final String title;
  final String subtitle;
  final String? query;
}

class SearchInspirationCardView {
  const SearchInspirationCardView({
    required this.id,
    required this.title,
    required this.subtitle,
    this.coverUrl,
    this.query,
  });

  final String id;
  final String title;
  final String subtitle;
  final String? coverUrl;
  final String? query;
}

class SearchInspirationPersonView {
  const SearchInspirationPersonView({
    required this.id,
    required this.displayName,
    required this.headline,
    required this.reason,
    this.avatarUrl,
  });

  final String id;
  final String displayName;
  final String headline;
  final String reason;
  final String? avatarUrl;
}

class SearchInspirationState {
  const SearchInspirationState({
    this.todayIntersections = const <SearchInspirationChipView>[],
    this.guessKeywords = const <NetworkSearchSuggestion>[],
    this.guessBatchIndex = 0,
    this.discoverCircles = const <SearchInspirationCardView>[],
    this.discoverLocations = const <SearchInspirationCardView>[],
    this.people = const <SearchInspirationPersonView>[],
    this.isLoading = false,
  });

  final List<SearchInspirationChipView> todayIntersections;
  final List<NetworkSearchSuggestion> guessKeywords;
  final int guessBatchIndex;
  final List<SearchInspirationCardView> discoverCircles;
  final List<SearchInspirationCardView> discoverLocations;
  final List<SearchInspirationPersonView> people;
  final bool isLoading;

  bool get isEmpty =>
      todayIntersections.isEmpty &&
      guessKeywords.isEmpty &&
      discoverCircles.isEmpty &&
      discoverLocations.isEmpty &&
      people.isEmpty;

  SearchInspirationState copyWith({
    List<SearchInspirationChipView>? todayIntersections,
    List<NetworkSearchSuggestion>? guessKeywords,
    int? guessBatchIndex,
    List<SearchInspirationCardView>? discoverCircles,
    List<SearchInspirationCardView>? discoverLocations,
    List<SearchInspirationPersonView>? people,
    bool? isLoading,
  }) {
    return SearchInspirationState(
      todayIntersections: todayIntersections ?? this.todayIntersections,
      guessKeywords: guessKeywords ?? this.guessKeywords,
      guessBatchIndex: guessBatchIndex ?? this.guessBatchIndex,
      discoverCircles: discoverCircles ?? this.discoverCircles,
      discoverLocations: discoverLocations ?? this.discoverLocations,
      people: people ?? this.people,
      isLoading: isLoading ?? this.isLoading,
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
    this.inspiration = const SearchInspirationState(),
    this.isLoading = false,
    this.isNetworkLoading = false,
    this.isSlow = false,
    this.isPartial = false,
    this.failure,
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
  final SearchInspirationState inspiration;
  final bool isLoading;
  final bool isNetworkLoading;
  final bool isSlow;
  final bool isPartial;
  final Object? failure;
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
    SearchInspirationState? inspiration,
    bool? isLoading,
    bool? isNetworkLoading,
    bool? isSlow,
    bool? isPartial,
    ValueGetter<Object?>? failure,
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
      inspiration: inspiration ?? this.inspiration,
      isLoading: isLoading ?? this.isLoading,
      isNetworkLoading: isNetworkLoading ?? this.isNetworkLoading,
      isSlow: isSlow ?? this.isSlow,
      isPartial: isPartial ?? this.isPartial,
      failure: failure != null ? failure() : this.failure,
      isHydratingHistory: isHydratingHistory ?? this.isHydratingHistory,
      isManagingHistory: isManagingHistory ?? this.isManagingHistory,
      isHistoryExpanded: isHistoryExpanded ?? this.isHistoryExpanded,
      areContactsExpanded: areContactsExpanded ?? this.areContactsExpanded,
      areChatRecordsExpanded:
          areChatRecordsExpanded ?? this.areChatRecordsExpanded,
    );
  }
}
