import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_search_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_request_wait_controller.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

part 'search_coordinator_support.dart';
part 'search_coordinator_execution.dart';
part 'search_coordinator_suggestions.dart';

final searchCoordinatorProvider = NotifierProvider.autoDispose
    .family<SearchCoordinator, SearchSessionState, SearchLaunchContext>(
      SearchCoordinator.new,
    );

class SearchCoordinator extends Notifier<SearchSessionState> {
  SearchCoordinator(this._launchContext);

  final SearchLaunchContext _launchContext;

  @override
  SearchSessionState build() {
    ref.onDispose(() {
      _debounceTimer?.cancel();
      _searchRequestToken += 1;
      _waitController.dispose();
    });
    final initial = SearchSessionState(
      launchContext: _launchContext,
      query: _launchContext.prefilledQuery,
      scope: _launchContext.initialScope,
      selection: _resolveInitialSelection(_launchContext),
    );
    Future.microtask(() {
      if (!ref.mounted) {
        return;
      }
      unawaited(hydrateRecentSearches());
      unawaited(hydrateSearchInspiration());
      if (state.hasQuery) {
        scheduleSearch(immediate: true);
      }
    });
    return initial;
  }

  static const Duration _searchDebounce = Duration(milliseconds: 180);
  static const int _localMatchLimit = 3;
  static const int _conversationSearchLimit = 12;
  static const int _maxNetworkSuggestions = 6;

  final SearchRecentHistoryStore _localStore = const SearchRecentHistoryStore();
  final AppRequestWaitController _waitController = AppRequestWaitController();

  Timer? _debounceTimer;
  int _searchRequestToken = 0;

  static SearchObjectSelection _resolveInitialSelection(
    SearchLaunchContext launchContext,
  ) {
    final explicitSelection = launchContext.searchObjectSelection.normalized();
    if (!explicitSelection.isEmpty) {
      return explicitSelection;
    }
    final facetSelection = SearchObjectSelection.fromFacet(
      launchContext.initialFacet,
    );
    if (!facetSelection.isEmpty) {
      return facetSelection;
    }
    return SearchObjectSelection.fromSearchScope(launchContext.initialScope);
  }

  void _setState(SearchSessionState next) {
    if (!ref.mounted) {
      return;
    }
    state = next;
  }

  SearchSessionState get _currentState => state;

  bool get _isMounted => ref.mounted;

  Ref get _coordinatorRef => ref;

  void updateQuery(String query, {bool immediate = false}) {
    final trimmedQuery = query.trim();
    _debounceTimer?.cancel();
    _invalidateActiveSearch();
    _setState(
      state.copyWith(
        query: query,
        isManagingHistory: false,
        areContactsExpanded: false,
        areChatRecordsExpanded: false,
        suggestionSections: const <SearchSuggestionSection>[],
        isLoading: trimmedQuery.isNotEmpty,
        isNetworkLoading: false,
        isSlow: false,
        isPartial: false,
        failure: () => null,
      ),
    );
    if (trimmedQuery.isEmpty) {
      return;
    }
    scheduleSearch(immediate: immediate);
  }

  void updateSelection(SearchObjectSelection selection) {
    final normalizedSelection = selection.normalized();
    if (setEquals(
          state.selection.normalizedTargets,
          normalizedSelection.normalizedTargets,
        ) &&
        setEquals(
          state.selection.contentTypes,
          normalizedSelection.contentTypes,
        )) {
      return;
    }
    _invalidateActiveSearch();
    _setState(
      state.copyWith(
        selection: normalizedSelection,
        launchContext: state.launchContext.copyWith(
          searchObjectSelection: normalizedSelection,
          initialFacet: normalizedSelection.toFacet(),
        ),
        suggestionSections: const <SearchSuggestionSection>[],
        isLoading: state.hasQuery,
        isNetworkLoading: false,
        isSlow: false,
        isPartial: false,
        failure: () => null,
      ),
    );
    if (state.hasQuery) {
      scheduleSearch(immediate: true);
    }
  }

  void startManagingHistory() {
    if (state.hasQuery || state.recentSearches.isEmpty) {
      return;
    }
    _setState(state.copyWith(isManagingHistory: true, isHistoryExpanded: true));
  }

  void finishManagingHistory() {
    _setState(
      state.copyWith(isManagingHistory: false, isHistoryExpanded: false),
    );
  }

  void toggleHistoryExpanded() {
    if (state.recentSearches.isEmpty) {
      return;
    }
    _setState(state.copyWith(isHistoryExpanded: !state.isHistoryExpanded));
  }

  void expandContacts() {
    if (state.areContactsExpanded) {
      return;
    }
    _setState(
      state.copyWith(
        areContactsExpanded: true,
        suggestionSections: _applyExpansionFlags(
          state.suggestionSections,
          contactsExpanded: true,
        ),
      ),
    );
  }

  void expandChatRecords() {
    if (state.areChatRecordsExpanded) {
      return;
    }
    _setState(
      state.copyWith(
        areChatRecordsExpanded: true,
        suggestionSections: _applyExpansionFlags(
          state.suggestionSections,
          chatRecordsExpanded: true,
        ),
      ),
    );
  }

  void scheduleSearch({bool immediate = false}) {
    _debounceTimer?.cancel();
    if (immediate) {
      unawaited(_performSearch());
      return;
    }
    _debounceTimer = Timer(_searchDebounce, () => unawaited(_performSearch()));
  }

  Future<void> hydrateRecentSearches() async {
    _setState(state.copyWith(isHydratingHistory: true));
    final localEntries = await _localStore.load();
    if (ref.mounted && localEntries.isNotEmpty) {
      _setState(state.copyWith(recentSearches: localEntries));
    }
    try {
      final remoteEntries = await ref
          .read(userProfileRepositoryProvider)
          .listRecentSearches();
      final merged = _mergeHistory(localEntries, remoteEntries);
      if (!ref.mounted) {
        return;
      }
      _setState(
        state.copyWith(recentSearches: merged, isHydratingHistory: false),
      );
      await _localStore.save(merged);
      final remoteKeys = remoteEntries.map(_historyKeyForEntry).toSet();
      for (final entry in localEntries) {
        if (remoteKeys.contains(_historyKeyForEntry(entry))) {
          continue;
        }
        unawaited(
          ref
              .read(userProfileRepositoryProvider)
              .upsertRecentSearch(
                query: entry.query,
                scope: entry.scope,
                facet: entry.facet,
              ),
        );
      }
    } catch (_) {
      if (!ref.mounted) {
        return;
      }
      _setState(state.copyWith(isHydratingHistory: false));
    }
  }
}
