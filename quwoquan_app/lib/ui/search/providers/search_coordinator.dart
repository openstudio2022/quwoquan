import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:shared_preferences/shared_preferences.dart';

final searchCoordinatorProvider = ChangeNotifierProvider.autoDispose
    .family<SearchCoordinator, SearchLaunchContext>((ref, launchContext) {
      return SearchCoordinator(ref, launchContext);
    });

class SearchCoordinator extends ChangeNotifier {
  SearchCoordinator(this._ref, SearchLaunchContext launchContext)
    : _localStore = const SearchRecentHistoryStore(),
      _state = SearchSessionState(
        launchContext: launchContext,
        query: launchContext.prefilledQuery,
        scope: launchContext.initialScope,
        selectedFacet: launchContext.initialFacet,
      ) {
    unawaited(hydrateRecentSearches());
    if (_state.hasQuery) {
      scheduleSearch(immediate: true);
    }
  }

  final Ref _ref;
  final SearchRecentHistoryStore _localStore;
  SearchSessionState _state;
  Timer? _debounceTimer;
  int _searchRequestToken = 0;
  bool _disposed = false;

  static const Duration _searchDebounce = Duration(milliseconds: 250);
  static const int _sectionLimit = 6;

  SearchSessionState get state => _state;

  void _setState(SearchSessionState next) {
    if (_disposed) {
      return;
    }
    _state = next;
    notifyListeners();
  }

  void updateQuery(
    String query, {
    bool immediate = false,
    bool persistToHistory = false,
  }) {
    final trimmedQuery = query.trim();
    _setState(state.copyWith(
      query: query,
      sections: trimmedQuery.isEmpty ? const <SearchSection>[] : null,
      isLoading: trimmedQuery.isEmpty ? false : state.isLoading,
    ));
    if (trimmedQuery.isEmpty) {
      _debounceTimer?.cancel();
      return;
    }
    scheduleSearch(
      immediate: immediate,
      persistToHistory: persistToHistory,
    );
  }

  void updateScope(SearchScope scope) {
    _setState(state.copyWith(
      scope: scope,
      selectedFacet: () => scope == SearchScope.circles ? state.selectedFacet : null,
      sections: state.hasQuery ? state.sections : const <SearchSection>[],
    ));
    if (state.hasQuery) {
      scheduleSearch(immediate: true);
    }
  }

  void updateFacet(String? facet) {
    _setState(state.copyWith(selectedFacet: () => facet));
    if (state.hasQuery) {
      scheduleSearch(immediate: true);
    }
  }

  void setVoiceRunning(bool running) {
    _setState(state.copyWith(isVoiceRunning: running));
  }

  void scheduleSearch({
    bool immediate = false,
    bool persistToHistory = false,
  }) {
    _debounceTimer?.cancel();
    if (immediate) {
      unawaited(
        _performSearch(
          persistToHistory: persistToHistory,
        ),
      );
      return;
    }
    _debounceTimer = Timer(
      _searchDebounce,
      () => unawaited(
        _performSearch(
          persistToHistory: persistToHistory,
        ),
      ),
    );
  }

  Future<void> hydrateRecentSearches() async {
    _setState(state.copyWith(isHydratingHistory: true));
    final localEntries = await _localStore.load();
    if (!_disposed && localEntries.isNotEmpty) {
      _setState(state.copyWith(recentSearches: localEntries));
    }
    try {
      final remoteEntries = await _ref
          .read(userProfileRepositoryProvider)
          .listRecentSearches();
      final merged = _mergeHistory(localEntries, remoteEntries);
      if (_disposed) {
        return;
      }
      _setState(state.copyWith(
        recentSearches: merged,
        isHydratingHistory: false,
      ));
      await _localStore.save(merged);
      final remoteKeys = remoteEntries.map(_historyKeyForEntry).toSet();
      for (final entry in localEntries) {
        if (remoteKeys.contains(_historyKeyForEntry(entry))) {
          continue;
        }
        unawaited(
          _ref.read(userProfileRepositoryProvider).upsertRecentSearch(
            query: entry.query,
            scope: entry.scope,
            facet: entry.facet,
          ),
        );
      }
    } catch (_) {
      if (_disposed) {
        return;
      }
      _setState(state.copyWith(isHydratingHistory: false));
    }
  }

  Future<void> useRecentSearch(RecentSearchEntryView entry) async {
    _setState(state.copyWith(
      query: entry.query,
      scope: entry.scope,
      selectedFacet: () => entry.facet,
    ));
    scheduleSearch(immediate: true);
  }

  Future<void> rememberCurrentQuery() {
    return _rememberQuery(
      query: state.query,
      scope: state.scope,
      facet: state.selectedFacet,
    );
  }

  Future<void> removeRecentSearch(String entryId) async {
    final nextEntries = state.recentSearches
        .where((entry) => entry.entryId != entryId)
        .toList(growable: false);
    _setState(state.copyWith(recentSearches: nextEntries));
    await _localStore.save(nextEntries);
    try {
      await _ref.read(userProfileRepositoryProvider).deleteRecentSearch(entryId);
    } catch (_) {
      // Keep local-first delete even when remote cleanup fails.
    }
  }

  Future<void> clearRecentSearches() async {
    _setState(state.copyWith(recentSearches: const <RecentSearchEntryView>[]));
    await _localStore.clear();
    try {
      await _ref.read(userProfileRepositoryProvider).clearRecentSearches();
    } catch (_) {
      // Keep local-first clear even when remote cleanup fails.
    }
  }

  Future<void> _performSearch({bool persistToHistory = false}) async {
    final query = state.query.trim();
    if (query.isEmpty) {
      if (!_disposed) {
        _setState(state.copyWith(
          isLoading: false,
          sections: const <SearchSection>[],
        ));
      }
      return;
    }
    final token = ++_searchRequestToken;
    if (!_disposed) {
      _setState(state.copyWith(isLoading: true));
    }
    final scope = state.scope;
    final selectedFacet = state.selectedFacet;
    final sections = await _buildSections(
      query: query,
      scope: scope,
      selectedFacet: selectedFacet,
    );
    if (_disposed || token != _searchRequestToken) {
      return;
    }
    _setState(state.copyWith(
      sections: sections,
      isLoading: false,
    ));
    if (persistToHistory) {
      await _rememberQuery(
        query: query,
        scope: scope,
        facet: selectedFacet,
      );
    }
  }

  Future<List<SearchSection>> _buildSections({
    required String query,
    required SearchScope scope,
    required String? selectedFacet,
  }) async {
    final wantsContent = scope == SearchScope.all || scope == SearchScope.content;
    final wantsPeople =
        scope == SearchScope.all || scope == SearchScope.socialRelation;
    final wantsMessages =
        scope == SearchScope.all || scope == SearchScope.messages;
    final wantsCircles =
        scope == SearchScope.all || scope == SearchScope.circles;
    final circleSearchFuture = wantsCircles
        ? _ref.read(circleRepositoryProvider).searchCircles(
            query: query,
            subCategory: selectedFacet,
            limit: _sectionLimit,
          )
        : null;

    final futures = <Future<SearchSection>>[
      if (wantsContent)
        _loadSection(
          kind: SearchSectionKind.content,
          loader: () async {
            final items = await _ref
                .read(contentRepositoryProvider)
                .searchPosts(
              query: query,
              limit: _sectionLimit,
            );
            return items
                .map<SearchResultItem>(SearchResultItem.post)
                .toList(growable: false);
          },
        ),
      if (wantsPeople)
        _loadSection(
          kind: SearchSectionKind.socialRelation,
          loader: () async {
            final items = await _ref
                .read(userProfileRepositoryProvider)
                .searchSocialRelations(
                  query: query,
                  limit: _sectionLimit,
                );
            return items
                .map<SearchResultItem>(SearchResultItem.socialRelation)
                .toList(growable: false);
          },
        ),
      if (wantsMessages)
        _loadSection(
          kind: SearchSectionKind.messages,
          loader: () async {
            final chatRepository = _ref.read(chatRepositoryProvider);
            final conversationFuture = chatRepository.searchConversations(
              query: query,
              limit: _sectionLimit ~/ 2 + 1,
            );
            final messageFuture = chatRepository.searchMessages(
              query: query,
              limit: _sectionLimit ~/ 2 + 1,
            );
            final results = await Future.wait([
              conversationFuture,
              messageFuture,
            ]);
            final conversations = results[0]
                .cast<ConversationSearchItemView>()
                .map<SearchResultItem>(SearchResultItem.conversation);
            final messages = results[1]
                .cast<MessageSearchItemView>()
                .map<SearchResultItem>(SearchResultItem.message);
            return <SearchResultItem>[
              ...conversations,
              ...messages,
            ].take(_sectionLimit).toList(growable: false);
          },
        ),
      if (wantsCircles)
        _loadSection(
          kind: SearchSectionKind.circleFacets,
          loader: () async {
            final result = await circleSearchFuture!;
            return result.facetBuckets
                .map<SearchResultItem>(SearchResultItem.circleFacet)
                .toList(growable: false);
          },
        ),
      if (wantsCircles)
        _loadSection(
          kind: SearchSectionKind.circles,
          loader: () async {
            final result = await circleSearchFuture!;
            return result.items
                .map<SearchResultItem>(SearchResultItem.circle)
                .toList(growable: false);
          },
        ),
    ];
    final sections = await Future.wait(futures);
    return sections
        .where(
          (section) =>
              section.items.isNotEmpty || section.degraded || scope == SearchScope.circles,
        )
        .toList(growable: false);
  }

  Future<SearchSection> _loadSection({
    required SearchSectionKind kind,
    required Future<List<SearchResultItem>> Function() loader,
  }) async {
    try {
      final items = await loader();
      return SearchSection(kind: kind, items: items);
    } catch (_) {
      return SearchSection(
        kind: kind,
        items: const <SearchResultItem>[],
        degraded: true,
        errorMessage: '当前结果暂不可用',
      );
    }
  }

  Future<void> _rememberQuery({
    required String query,
    required SearchScope scope,
    required String? facet,
  }) async {
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return;
    }
    final now = DateTime.now();
    final seed = '${scope.wireValue}|${facet ?? ''}|${trimmedQuery.toLowerCase()}';
    final localEntry = RecentSearchEntryView(
      entryId: 'recent_${seed.hashCode.abs().toRadixString(16)}',
      query: trimmedQuery,
      scope: scope,
      facet: facet,
      updatedAt: now,
    );
    final merged = _mergeHistory(
      <RecentSearchEntryView>[localEntry],
      state.recentSearches,
    );
    _setState(state.copyWith(recentSearches: merged));
    await _localStore.save(merged);
    try {
      final remoteEntry = await _ref
          .read(userProfileRepositoryProvider)
          .upsertRecentSearch(
            query: trimmedQuery,
            scope: scope,
            facet: facet,
          );
      final nextEntries = _mergeHistory(<RecentSearchEntryView>[remoteEntry], merged);
      if (_disposed) {
        return;
      }
      _setState(state.copyWith(recentSearches: nextEntries));
      await _localStore.save(nextEntries);
    } catch (_) {
      // Local-first history remains available while remote sync degrades.
    }
  }

  List<RecentSearchEntryView> _mergeHistory(
    List<RecentSearchEntryView> primary,
    List<RecentSearchEntryView> secondary,
  ) {
    final merged = <String, RecentSearchEntryView>{};
    for (final entry in [...primary, ...secondary]) {
      final key = _historyKeyForEntry(entry);
      final existing = merged[key];
      if (existing == null || entry.updatedAt.isAfter(existing.updatedAt)) {
        merged[key] = entry;
      }
    }
    final values = merged.values.toList(growable: false);
    values.sort((left, right) => right.updatedAt.compareTo(left.updatedAt));
    return values.take(12).toList(growable: false);
  }

  String _historyKeyForEntry(RecentSearchEntryView entry) {
    return '${entry.scope.wireValue}|${entry.facet ?? ''}|${entry.query.toLowerCase()}';
  }

  @override
  void dispose() {
    _disposed = true;
    _debounceTimer?.cancel();
    super.dispose();
  }
}

class SearchRecentHistoryStore {
  const SearchRecentHistoryStore();

  static const String _storageKey = 'global_search_recent_entries_v1';

  Future<List<RecentSearchEntryView>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_storageKey);
    if (raw == null || raw.trim().isEmpty) {
      return const <RecentSearchEntryView>[];
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return const <RecentSearchEntryView>[];
      }
      return decoded
          .whereType<Map>()
          .map(
            (item) =>
                RecentSearchEntryView.fromMap(item.cast<String, dynamic>()),
          )
          .where((item) => item.query.trim().isNotEmpty)
          .toList(growable: false);
    } catch (_) {
      return const <RecentSearchEntryView>[];
    }
  }

  Future<void> save(List<RecentSearchEntryView> entries) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _storageKey,
      jsonEncode(
        entries
            .map(
              (entry) => <String, dynamic>{
                'entryId': entry.entryId,
                'query': entry.query,
                'scope': entry.scope.wireValue,
                'facet': entry.facet,
                'updatedAt': entry.updatedAt.toIso8601String(),
              },
            )
            .toList(growable: false),
      ),
    );
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_storageKey);
  }
}
