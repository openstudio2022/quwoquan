import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show setEquals;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_request_wait_controller.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'search_coordinator_support.dart';
part 'search_coordinator_execution.dart';
part 'search_coordinator_suggestion_builders.dart';
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
    final ownerUserId = ref.watch(resolvedOwnerUserIdProvider).trim();
    final activeActorId = ref.watch(currentUserIdProvider).trim();
    final actorNamespace = ownerUserId.isEmpty
        ? 'guest'
        : '$ownerUserId::${activeActorId.isEmpty ? ownerUserId : activeActorId}';
    _localStore = SearchRecentHistoryStore(actorNamespace: actorNamespace);
    _pendingRecentUpsertKeys = <String>{};
    _pendingRecentDeleteKeys = <String>{};
    _recentUpsertTokens = <String, int>{};
    _recentUpsertSequence = 0;
    _recentClearToken = 0;
    _recentHistoryMutationRevision = 0;
    _pendingRecentClear = false;
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
  static const int _guessKeywordBatchSize = 10;
  static const int _recentSearchMaxEntries = 12;
  static const Set<String> _locationHomepageTypes = <String>{
    'hotel',
    'restaurant',
    'sight',
    'university',
    'museum',
    'heritage_site',
    'ancient_town',
    'religious_site',
    'check_in_spot',
    'natural_landscape',
    'park',
    'hot_spring',
    'theme_park',
  };

  late SearchRecentHistoryStore _localStore;
  final AppRequestWaitController _waitController = AppRequestWaitController();
  Set<String> _pendingRecentUpsertKeys = <String>{};
  Set<String> _pendingRecentDeleteKeys = <String>{};
  Map<String, int> _recentUpsertTokens = <String, int>{};
  int _recentUpsertSequence = 0;
  int _recentClearToken = 0;
  int _recentHistoryMutationRevision = 0;
  bool _pendingRecentClear = false;

  Timer? _debounceTimer;
  int _searchRequestToken = 0;
  List<NetworkSearchSuggestion> _hotQueryPool =
      const <NetworkSearchSuggestion>[];

  bool get canRefreshGuessKeywords =>
      _hotQueryPool.length > _guessKeywordBatchSize;

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
    final store = _localStore;
    final clearToken = _recentClearToken;
    final mutationRevision = _recentHistoryMutationRevision;
    _setState(state.copyWith(isHydratingHistory: true));
    // 本地 SharedPreferences 是游客态/离线的表现层缓存；
    // 登录态以 search 域 RecentSearchState 远端为真相源。
    var localSnapshot = const SearchRecentHistoryCacheSnapshot();
    try {
      localSnapshot = await store.load();
    } on Object catch (error) {
      if (error is FormatException) {
        await store.clear();
      }
      _recordRecentHistoryFailure(
        operation: 'local_cache_load',
        error: error,
        cacheInvalidated: error is FormatException,
      );
    }
    if (!ref.mounted ||
        !identical(store, _localStore) ||
        clearToken != _recentClearToken ||
        mutationRevision != _recentHistoryMutationRevision) {
      if (ref.mounted && identical(store, _localStore)) {
        _setState(state.copyWith(isHydratingHistory: false));
        unawaited(hydrateRecentSearches());
      }
      return;
    }
    _pendingRecentUpsertKeys = localSnapshot.pendingUpsertKeys.toSet();
    _pendingRecentDeleteKeys = localSnapshot.pendingDeleteKeys.toSet();
    _pendingRecentClear = localSnapshot.pendingClear;
    final localEntries = localSnapshot.entries
        .where((entry) {
          final historyKey = _historyKeyForEntry(entry);
          if (_pendingRecentDeleteKeys.contains(historyKey)) {
            return false;
          }
          return !_pendingRecentClear ||
              _pendingRecentUpsertKeys.contains(historyKey);
        })
        .toList(growable: false);
    if (localEntries.isNotEmpty) {
      _setState(state.copyWith(recentSearches: localEntries));
    }
    try {
      final slice = await ref
          .read(recentSearchQueryProvider)
          .listRecentSearches(ListRecentSearchesQuery());
      var remoteEntries = slice.items
          .map(_recentEntryFromContract)
          .toList(growable: false);
      if (!ref.mounted ||
          !identical(store, _localStore) ||
          clearToken != _recentClearToken ||
          mutationRevision != _recentHistoryMutationRevision) {
        if (ref.mounted && identical(store, _localStore)) {
          _setState(state.copyWith(isHydratingHistory: false));
          unawaited(hydrateRecentSearches());
        }
        return;
      }

      if (_pendingRecentClear) {
        try {
          await ref
              .read(recentSearchCommandWriterProvider)
              .clearRecentSearches(ClearRecentSearchesCommand());
          _pendingRecentClear = false;
          _pendingRecentDeleteKeys.clear();
          remoteEntries = const <RecentSearchEntryView>[];
        } on Object catch (error) {
          _recordRecentHistoryFailure(
            operation: 'remote_clear_retry',
            error: error,
          );
          await _saveRecentHistory(localEntries, store: store);
          _setState(
            state.copyWith(
              recentSearches: localEntries,
              isHydratingHistory: false,
            ),
          );
          return;
        }
      }

      final deleteHistoryKeys = _pendingRecentDeleteKeys.toSet();
      final deleteIntentTokens = <String, int?>{
        for (final historyKey in deleteHistoryKeys)
          historyKey: _recentUpsertTokens[historyKey],
      };
      final remoteEntriesByHistoryKey = <String, RecentSearchEntryView>{
        for (final entry in remoteEntries) _historyKeyForEntry(entry): entry,
      };
      for (final historyKey in deleteHistoryKeys) {
        final remoteEntry = remoteEntriesByHistoryKey[historyKey];
        if (remoteEntry == null) {
          if (deleteIntentTokens[historyKey] ==
              _recentUpsertTokens[historyKey]) {
            _pendingRecentDeleteKeys.remove(historyKey);
          } else if (_currentState.recentSearches.any(
            (entry) => _historyKeyForEntry(entry) == historyKey,
          )) {
            // 删除请求发出后用户又恢复了同一语义项；保留 upsert 回执，
            // 让后续 hydrate 重新确认 Remote 终态，不能让旧删除赢得竞态。
            _pendingRecentUpsertKeys.add(historyKey);
          }
          continue;
        }
        try {
          await ref
              .read(recentSearchCommandWriterProvider)
              .deleteRecentSearch(
                DeleteRecentSearchCommand(entryId: remoteEntry.entryId),
              );
          if (deleteIntentTokens[historyKey] ==
              _recentUpsertTokens[historyKey]) {
            _pendingRecentDeleteKeys.remove(historyKey);
          } else if (_currentState.recentSearches.any(
            (entry) => _historyKeyForEntry(entry) == historyKey,
          )) {
            _pendingRecentUpsertKeys.add(historyKey);
          }
        } on Object catch (error) {
          _recordRecentHistoryFailure(
            operation: 'remote_delete_retry',
            error: error,
          );
        }
      }

      final hiddenHistoryKeys = <String>{
        ...deleteHistoryKeys,
        ..._pendingRecentDeleteKeys,
      };
      final visibleRemoteEntries = remoteEntries
          .where(
            (entry) => !hiddenHistoryKeys.contains(_historyKeyForEntry(entry)),
          )
          .toList(growable: false);
      final remoteByHistoryKey = <String, RecentSearchEntryView>{
        for (final entry in visibleRemoteEntries)
          _historyKeyForEntry(entry): entry,
      };
      final failedPendingEntries = <RecentSearchEntryView>[];
      final canonicalBackfills = <RecentSearchEntryView>[];
      final unresolvedUpsertKeys = <String>{};
      final attemptedUpsertKeys = _pendingRecentUpsertKeys.toSet();
      final attemptedUpsertTokens = <String, int?>{
        for (final historyKey in attemptedUpsertKeys)
          historyKey: _recentUpsertTokens[historyKey],
      };
      final pendingBackfills =
          localSnapshot.entries.asMap().entries.toList(growable: false)
            ..sort((left, right) {
              final updatedAtOrder = left.value.updatedAt.compareTo(
                right.value.updatedAt,
              );
              if (updatedAtOrder != 0) {
                return updatedAtOrder;
              }
              // 本地顺序为 newest-first；同一时间戳下先回填尾部旧项，避免服务端
              // 以受理时间生成 canonical updatedAt 后把历史顺序整体反转。
              return right.key.compareTo(left.key);
            });
      for (final indexedEntry in pendingBackfills) {
        final entry = indexedEntry.value;
        final historyKey = _historyKeyForEntry(entry);
        if (!attemptedUpsertKeys.contains(historyKey) ||
            !_pendingRecentUpsertKeys.contains(historyKey) ||
            _pendingRecentDeleteKeys.contains(historyKey)) {
          continue;
        }
        if (remoteByHistoryKey.containsKey(historyKey)) {
          continue;
        }
        final canonicalEntry = await _backfillLocalRecentSearch(entry);
        if (canonicalEntry == null) {
          unresolvedUpsertKeys.add(historyKey);
          failedPendingEntries.add(entry);
        } else if (clearToken != _recentClearToken ||
            attemptedUpsertTokens[historyKey] !=
                _recentUpsertTokens[historyKey]) {
          if (_pendingRecentDeleteKeys.contains(historyKey) ||
              !_currentState.recentSearches.any(
                (current) => _historyKeyForEntry(current) == historyKey,
              )) {
            final deleted = await _deleteCanonicalRecentSearch(
              canonicalEntry,
              operation: 'remote_delete_after_obsolete_backfill',
            );
            if (deleted) {
              _pendingRecentDeleteKeys.remove(historyKey);
            }
          }
        } else if (_pendingRecentDeleteKeys.contains(historyKey)) {
          final deleted = await _deleteCanonicalRecentSearch(
            canonicalEntry,
            operation: 'remote_delete_after_backfill',
          );
          if (deleted) {
            _pendingRecentDeleteKeys.remove(historyKey);
          }
        } else {
          canonicalBackfills.add(canonicalEntry);
        }
      }
      if (clearToken != _recentClearToken ||
          mutationRevision != _recentHistoryMutationRevision) {
        await _saveRecentHistory(_currentState.recentSearches, store: store);
        _setState(_currentState.copyWith(isHydratingHistory: false));
        unawaited(hydrateRecentSearches());
        return;
      }
      for (final historyKey in attemptedUpsertKeys) {
        if (!unresolvedUpsertKeys.contains(historyKey) &&
            attemptedUpsertTokens[historyKey] ==
                _recentUpsertTokens[historyKey]) {
          _pendingRecentUpsertKeys.remove(historyKey);
          _recentUpsertTokens.remove(historyKey);
        }
      }

      var resolvedEntries = _mergeHistory(
        visibleRemoteEntries,
        failedPendingEntries,
      );
      for (final canonicalEntry in canonicalBackfills) {
        resolvedEntries = _replaceHistoryEntryWithCanonical(
          resolvedEntries,
          canonicalEntry,
        );
      }
      _setState(
        state.copyWith(
          recentSearches: resolvedEntries,
          isHydratingHistory: false,
        ),
      );
      await _saveRecentHistory(resolvedEntries, store: store);
    } on Object catch (error) {
      // 游客态/断网降级本地缓存；失败保留结构化日志，不合成远端成功。
      _recordRecentHistoryFailure(operation: 'remote_hydrate', error: error);
      if (!ref.mounted || !identical(store, _localStore)) {
        return;
      }
      _setState(_currentState.copyWith(isHydratingHistory: false));
    }
  }

  Future<RecentSearchEntryView?> _backfillLocalRecentSearch(
    RecentSearchEntryView entry,
  ) async {
    try {
      final remoteEntry = await ref
          .read(recentSearchCommandWriterProvider)
          .upsertRecentSearch(
            UpsertRecentSearchCommand(
              query: entry.query,
              scope: entry.scope.wireValue,
              facet: entry.facet,
            ),
          );
      return _recentEntryFromContract(remoteEntry);
    } on Object catch (error) {
      _recordRecentHistoryFailure(operation: 'remote_backfill', error: error);
      return null;
    }
  }

  Future<bool> _deleteCanonicalRecentSearch(
    RecentSearchEntryView entry, {
    required String operation,
  }) async {
    try {
      await ref
          .read(recentSearchCommandWriterProvider)
          .deleteRecentSearch(
            DeleteRecentSearchCommand(entryId: entry.entryId),
          );
      return true;
    } on Object catch (error) {
      _recordRecentHistoryFailure(operation: operation, error: error);
      return false;
    }
  }

  Future<void> _saveRecentHistory(
    List<RecentSearchEntryView> entries, {
    SearchRecentHistoryStore? store,
  }) {
    return (store ?? _localStore).save(
      SearchRecentHistoryCacheSnapshot(
        entries: entries,
        pendingUpsertKeys: _pendingRecentUpsertKeys,
        pendingDeleteKeys: _pendingRecentDeleteKeys,
        pendingClear: _pendingRecentClear,
      ),
    );
  }

  void _recordRecentHistoryFailure({
    required String operation,
    required Object error,
    bool cacheInvalidated = false,
  }) {
    ref
        .read(cacheTelemetrySinkProvider)
        .record('search.recent_history.degraded', <String, Object?>{
          'operation': operation,
          'errorType': error.runtimeType.toString(),
          'cacheInvalidated': cacheInvalidated,
        });
  }

  RecentSearchEntryView _recentEntryFromContract(RecentSearchEntry entry) {
    return RecentSearchEntryView(
      entryId: entry.entryId,
      query: entry.query,
      scope: SearchScope.fromWire(entry.scope),
      facet: entry.facet,
      updatedAt: entry.updatedAt ?? DateTime.now(),
    );
  }
}
