import 'package:flutter/foundation.dart' show ValueGetter;
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_entry_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_inspiration_models.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_suggestion_models.dart';

enum SearchViewMode { historyBrowse, historyManage, liveSuggestions }

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
