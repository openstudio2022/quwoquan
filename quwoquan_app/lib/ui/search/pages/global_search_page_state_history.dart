part of 'global_search_page.dart';

extension _GlobalSearchPageStateHistory on _GlobalSearchPageState {
  Widget _buildHistoryView({
    required Key key,
    required SearchSessionState state,
    required Color fgSecondary,
    required bool isDark,
  }) {
    if (state.isHydratingHistory && state.recentSearches.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }

    final historyColumns = _historyGridColumns(context);
    final collapsedHistoryCount = historyColumns * 5;
    final visibleEntries = state.isHistoryExpanded || state.isManagingHistory
        ? state.recentSearches
        : state.recentSearches
              .take(collapsedHistoryCount)
              .toList(growable: false);
    return ListView(
      key: key,
      padding: EdgeInsets.only(
        top: AppSpacing.containerXs,
        bottom: AppSpacing.containerMd,
      ),
      children: [
        if (state.recentSearches.isNotEmpty)
          _buildRecentSearchSection(
            entries: visibleEntries,
            columns: historyColumns,
            expanded: state.isHistoryExpanded,
            managing: state.isManagingHistory,
            isDark: isDark,
          ),
        if (state.recentSearches.isNotEmpty)
          SizedBox(height: _SearchTokens.sectionGap),
        ..._buildDefaultInspirationSections(state: state, isDark: isDark),
      ],
    );
  }

  Widget _buildRecentSearchSection({
    required List<RecentSearchEntryView> entries,
    required int columns,
    required bool expanded,
    required bool managing,
    required bool isDark,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SearchHistoryToolbar(
          expanded: expanded,
          managing: managing,
          onToggleExpanded: _coordinator.toggleHistoryExpanded,
          onStartManaging: _coordinator.startManagingHistory,
          onClearAll: () => unawaited(_confirmClearHistory()),
          onDone: _coordinator.finishManagingHistory,
        ),
        SizedBox(height: _SearchTokens.headerContentGap),
        GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: entries.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisExtent: AppSpacing.buttonHeightMd,
            crossAxisSpacing: _SearchTokens.historyColumnGap,
            mainAxisSpacing: _SearchTokens.historyRowGap,
          ),
          itemBuilder: (context, index) {
            final entry = entries[index];
            return _SearchHistoryGridItem(
              entry: entry,
              isDark: isDark,
              managing: managing,
              onTap: managing
                  ? null
                  : () => unawaited(_coordinator.useRecentSearch(entry)),
              onRemove: managing
                  ? () => unawaited(
                      _coordinator.removeRecentSearch(entry.entryId),
                    )
                  : null,
            );
          },
        ),
      ],
    );
  }

  int _historyGridColumns(BuildContext context) {
    return AppSpacing.responsiveValue(
      context,
      compact: 2,
      regular: 2,
      expanded: 3,
    ).round();
  }

  List<Widget> _buildDefaultInspirationSections({
    required SearchSessionState state,
    required bool isDark,
  }) {
    final inspiration = state.inspiration;
    if (inspiration.isLoading && inspiration.isEmpty) {
      return const <Widget>[Center(child: CupertinoActivityIndicator())];
    }
    final availableTabs = <_SearchHomeTab>{
      if (inspiration.guessKeywords.isNotEmpty) _SearchHomeTab.guess,
      if (inspiration.discoverCircles.isNotEmpty) _SearchHomeTab.circles,
      if (inspiration.discoverLocations.isNotEmpty) _SearchHomeTab.locations,
    };
    if (availableTabs.isEmpty) {
      return const <Widget>[];
    }
    final effectiveTab = availableTabs.contains(_activeHomeTab)
        ? _activeHomeTab
        : availableTabs.first;
    final content = switch (effectiveTab) {
      _SearchHomeTab.guess => _GuessKeywordSection(
        terms: inspiration.guessKeywords,
        isDark: isDark,
        showHeader: false,
        onTap: (item) => _openNetworkResults(item.query, initialTabId: 'all'),
      ),
      _SearchHomeTab.circles => _DiscoverEntityListSection(
        title: UITextConstants.searchHomeDiscoverCirclesTitle,
        items: inspiration.discoverCircles,
        isDark: isDark,
        showHeader: false,
        fallbackIcon: CupertinoIcons.person_3_fill,
        imageStyle: _DiscoverEntityImageStyle.avatar,
        onTap: (item) =>
            _openNetworkResults(item.query ?? item.title, initialTabId: 'all'),
      ),
      _SearchHomeTab.locations => _DiscoverEntityListSection(
        title: UITextConstants.searchHomeDiscoverLocationsTitle,
        items: inspiration.discoverLocations,
        isDark: isDark,
        showHeader: false,
        fallbackIcon: CupertinoIcons.location_solid,
        imageStyle: _DiscoverEntityImageStyle.cover,
        onTap: (item) =>
            _openNetworkResults(item.query ?? item.title, initialTabId: 'all'),
      ),
    };
    return <Widget>[
      _SearchHomeTabBar(
        activeTab: effectiveTab,
        availableTabs: availableTabs,
        onChanged: (tab) {
          _setState(() {
            _activeHomeTab = tab;
          });
        },
        onRefresh:
            effectiveTab == _SearchHomeTab.guess &&
                _coordinator.canRefreshGuessKeywords
            ? _coordinator.refreshGuessKeywords
            : null,
      ),
      SizedBox(height: _SearchTokens.headerContentGap),
      content,
    ];
  }
}
