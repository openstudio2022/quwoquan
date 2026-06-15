import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/conversation_avatar.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/cloud/runtime/models/recent_search_read_presentation.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/search/models/search_result_tab_spec.dart';
import 'package:quwoquan_app/ui/search/providers/search_coordinator.dart';

/// 搜索域统一语义 token。
///
/// 字体四级：
/// - L1 区块标题 [sectionTitleSize] + [sectionTitleWeight] + foregroundPrimary
/// - L2 正文/列表主文本 [bodySize] + [bodyWeight] + foregroundPrimary
/// - L3 卡片标题 [cardTitleSize] + [bodyWeight] + foregroundPrimary
/// - L4 辅助说明 [captionSize] + [bodyWeight] + foregroundSecondary
///
/// 低频工具栏：[toolbarSize] + [toolbarWeight] + foregroundTertiary，
/// 删除态操作 [toolbarSize] + [toolbarActionWeight] + foregroundSecondary。
///
/// 颜色三级：主文本 foregroundPrimary / 辅助 foregroundSecondary /
/// 低频工具栏与占位 foregroundTertiary；仅提交与可点链接使用 primaryColor。
class _SearchTokens {
  _SearchTokens._();

  // ===== 字体层级 =====
  static const double sectionTitleSize = AppTypography.iosBody; // L1 17
  static const FontWeight sectionTitleWeight = AppTypography.semiBold;
  static const double bodySize = AppTypography.iosCallout; // L2 16
  static const double cardTitleSize = AppTypography.iosFootnote; // L3 13
  static const double captionSize = AppTypography.iosCaption1; // L4 12
  static const double toolbarSize = AppTypography.iosSubheadline; // 工具栏 15
  static const FontWeight bodyWeight = AppTypography.regular;
  static const FontWeight toolbarWeight = AppTypography.regular;
  static const FontWeight toolbarActionWeight = AppTypography.medium;

  // ===== 间距层级 =====
  static const double tabToContentGap = AppSpacing.interGroupSm;
  static const double headerContentGap = AppSpacing.intraGroupSm;
  static const double sectionGap = AppSpacing.interGroupLg;
  static const double historyColumnGap = AppSpacing.interGroupMd;
  static const double historyRowGap = AppSpacing.intraGroupLg;
  static const double inspirationGridGap = AppSpacing.intraGroupSm;

  /// 搜索页正文左右边距：窄屏 containerMd，宽屏 containerLg。
  static double contentHorizontal(BuildContext context) =>
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerMd,
        regular: AppSpacing.containerMd,
        expanded: AppSpacing.containerLg,
      );
}

class GlobalSearchPage extends ConsumerStatefulWidget {
  const GlobalSearchPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<GlobalSearchPage> createState() => _GlobalSearchPageState();
}

class _GlobalSearchPageState extends ConsumerState<GlobalSearchPage> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;

  SearchCoordinator get _coordinator =>
      ref.read(searchCoordinatorProvider(widget.launchContext).notifier);

  SearchSessionState get _searchSession =>
      ref.read(searchCoordinatorProvider(widget.launchContext));

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(
      text: widget.launchContext.prefilledQuery,
    );
    _focusNode = FocusNode();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(searchCoordinatorProvider(widget.launchContext));
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final backgroundColor = SettingsSemanticConstants.pageBackground(isDark);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    _syncControllerText(state.query);

    return AppFullscreenModalSurface(
      surfaceKey: TestKeys.fullscreenModalSurface,
      backgroundColor: backgroundColor,
      safeAreaTop: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildSearchChrome(state, isDark, fgSecondary, backgroundColor),
          Expanded(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                _SearchTokens.contentHorizontal(context),
                AppSpacing.containerSm,
                _SearchTokens.contentHorizontal(context),
                AppSpacing.containerLg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _buildFixedTabBar(state: state, isDark: isDark),
                  SizedBox(height: _SearchTokens.tabToContentGap),
                  Expanded(
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 180),
                      child: switch (state.viewMode) {
                        SearchViewMode.historyBrowse => _buildHistoryView(
                          key: const ValueKey<String>('search_history_browse'),
                          state: state,
                          fgSecondary: fgSecondary,
                          isDark: isDark,
                        ),
                        SearchViewMode.historyManage => _buildHistoryView(
                          key: const ValueKey<String>('search_history_manage'),
                          state: state,
                          fgSecondary: fgSecondary,
                          isDark: isDark,
                        ),
                        SearchViewMode.liveSuggestions => _buildSuggestionView(
                          key: const ValueKey<String>(
                            'search_live_suggestions',
                          ),
                          state: state,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          isDark: isDark,
                        ),
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchChrome(
    SearchSessionState state,
    bool isDark,
    Color fgSecondary,
    Color backgroundColor,
  ) {
    final topInset = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );
    return DecoratedBox(
      decoration: BoxDecoration(color: backgroundColor),
      child: Padding(
        padding: EdgeInsets.only(top: topInset),
        child: SizedBox(
          height: AppSpacing.appChromeTopBarHeight(context),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: _SearchTokens.contentHorizontal(context),
            ),
            child: _buildSearchBar(state, isDark, fgSecondary),
          ),
        ),
      ),
    );
  }

  Widget _buildSearchBar(
    SearchSessionState state,
    bool isDark,
    Color fgSecondary,
  ) {
    final fieldBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final trailingInset = state.isLoading
        ? AppSpacing.appChromeActionButtonSize + AppSpacing.intraGroupSm
        : AppSpacing.containerSm;
    final hasSearchText = state.query.trim().isNotEmpty;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: Size.square(AppSpacing.appChromeActionButtonSize),
          onPressed: _handleClose,
          child: Icon(
            CupertinoIcons.chevron_back,
            color: fgSecondary,
            size: AppSpacing.appChromeActionIconSize,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        Expanded(
          child: Stack(
            alignment: Alignment.centerRight,
            children: [
              AppSearchField(
                key: const ValueKey<String>('global_search_field'),
                controller: _controller,
                focusNode: _focusNode,
                autofocus: true,
                placeholder: UITextConstants.globalSearchTitle,
                onChanged: (value) => _coordinator.updateQuery(value),
                onSubmitted: _handleSearchSubmitted,
                backgroundColor: fieldBackground,
                elevated: false,
                padding: EdgeInsetsDirectional.only(
                  start: AppSpacing.containerSm,
                  end: trailingInset,
                ),
              ),
              if (state.isLoading)
                PositionedDirectional(
                  end: 0,
                  top: 0,
                  bottom: 0,
                  child: Center(
                    child: SizedBox(
                      width: AppSpacing.appChromeActionButtonSize,
                      child: CupertinoActivityIndicator(radius: 8),
                    ),
                  ),
                ),
            ],
          ),
        ),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 160),
          child: hasSearchText
              ? Padding(
                  key: const ValueKey<String>('global_search_submit_visible'),
                  padding: EdgeInsetsDirectional.only(
                    start: AppSpacing.intraGroupXs,
                  ),
                  child: CupertinoButton(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerXs,
                    ),
                    minimumSize: const Size(
                      0,
                      AppSpacing.appChromeTextActionMinHeight,
                    ),
                    onPressed: () => _handleSearchSubmitted(_controller.text),
                    child: Text(
                      UITextConstants.search,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.medium,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ),
                )
              : const SizedBox.shrink(
                  key: ValueKey<String>('global_search_submit_hidden'),
                ),
        ),
      ],
    );
  }

  Widget _buildFixedTabBar({
    required SearchSessionState state,
    required bool isDark,
  }) {
    final tabs = SearchResultTabSpec.fixedTabs;
    final activeIndex = tabs.indexWhere(
      (tab) => tab.id == SearchResultTabIds.all,
    );
    return SecondaryCapsuleTabBar(
      isDark: isDark,
      tabs: tabs.map((tab) => tab.label).toList(growable: false),
      activeIndex: activeIndex < 0 ? 0 : activeIndex,
      onTap: (index) {
        final query = state.query.trim();
        if (query.isEmpty) {
          _focusNode.requestFocus();
          return;
        }
        _openNetworkResults(query, initialTabId: tabs[index].id);
      },
    );
  }

  bool _allowsNetworkResults(SearchObjectSelection selection) {
    return selection.normalized().enabledContentTypes.isNotEmpty;
  }

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
    return <Widget>[
      if (inspiration.todayIntersections.isNotEmpty)
        _TodayIntersectionSection(
          items: inspiration.todayIntersections,
          isDark: isDark,
          onTap: (item) => _openNetworkResults(
            item.query ?? item.title,
            initialTabId: 'all',
          ),
        ),
      if (inspiration.todayIntersections.isNotEmpty)
        SizedBox(height: _SearchTokens.sectionGap),
      if (inspiration.hotCircles.isNotEmpty)
        _InspirationCardGridSection(
          title: '热门圈子',
          items: inspiration.hotCircles,
          isDark: isDark,
          fallbackIcon: CupertinoIcons.person_3_fill,
          onTap: (item) => _openNetworkResults(
            item.query ?? item.title,
            initialTabId: 'all',
          ),
        ),
      if (inspiration.hotCircles.isNotEmpty)
        SizedBox(height: _SearchTokens.sectionGap),
      if (inspiration.hotLocations.isNotEmpty)
        _InspirationCardGridSection(
          title: '热门地点',
          items: inspiration.hotLocations,
          isDark: isDark,
          fallbackIcon: CupertinoIcons.location_solid,
          onTap: (item) => _openNetworkResults(
            item.query ?? item.title,
            initialTabId: 'all',
          ),
        ),
      if (inspiration.hotLocations.isNotEmpty)
        SizedBox(height: _SearchTokens.sectionGap),
      if (inspiration.people.isNotEmpty)
        _InspirationPeopleSection(
          people: inspiration.people,
          isDark: isDark,
          onTap: (person) => _openUserProfile(person.id),
        ),
    ];
  }

  Widget _buildSuggestionView({
    required Key key,
    required SearchSessionState state,
    required Color fgPrimary,
    required Color fgSecondary,
    required bool isDark,
  }) {
    if (state.isLoading && state.suggestionSections.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state.suggestionSections.isEmpty) {
      return Center(
        key: key,
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Text(
            '没有找到匹配结果',
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              color: fgSecondary,
            ),
          ),
        ),
      );
    }
    return ListView.builder(
      key: key,
      padding: EdgeInsets.only(
        top: AppSpacing.containerXs,
        bottom: AppSpacing.containerMd,
      ),
      itemCount: state.suggestionSections.length,
      itemBuilder: (context, index) {
        final section = state.suggestionSections[index];
        return Padding(
          padding: EdgeInsets.only(
            bottom: index == state.suggestionSections.length - 1
                ? 0
                : _SearchTokens.sectionGap,
          ),
          child: _buildSuggestionSection(
            section: section,
            query: state.query.trim(),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
            isDark: isDark,
          ),
        );
      },
    );
  }

  Widget _buildSuggestionSection({
    required SearchSuggestionSection section,
    required String query,
    required Color fgPrimary,
    required Color fgSecondary,
    required bool isDark,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SearchSectionHeader(title: section.title),
        SizedBox(height: _SearchTokens.headerContentGap),
        switch (section.kind) {
          SearchSuggestionSectionKind.contacts ||
          SearchSuggestionSectionKind.followedPeople =>
            _buildAvatarSuggestionGrid(
              section: section,
              query: query,
              isDark: isDark,
            ),
          SearchSuggestionSectionKind.circles ||
          SearchSuggestionSectionKind.locations => _buildObjectSuggestionGrid(
            section: section,
            query: query,
            isDark: isDark,
          ),
          SearchSuggestionSectionKind.network => _buildNetworkSuggestionTags(
            section: section,
            query: query,
            isDark: isDark,
          ),
          SearchSuggestionSectionKind.chatRecords => _buildSuggestionListCard(
            section: section,
            query: query,
            isDark: isDark,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
        },
      ],
    );
  }

  Widget _buildSuggestionListCard({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return _SuggestionSurface(
      isDark: isDark,
      child: Column(
        children: [
          for (var i = 0; i < section.visibleItems.length; i++) ...[
            _buildSuggestionItem(
              item: section.visibleItems[i],
              query: query,
              isDark: isDark,
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
            ),
            if (i != section.visibleItems.length - 1 || section.showsMoreEntry)
              _DividerLine(isDark: isDark),
          ],
          if (section.showsMoreEntry)
            _MoreActionRow(
              label: section.moreLabel ?? '查看更多',
              onTap: () {
                switch (section.kind) {
                  case SearchSuggestionSectionKind.contacts:
                    _coordinator.expandContacts();
                  case SearchSuggestionSectionKind.chatRecords:
                    _coordinator.expandChatRecords();
                  case SearchSuggestionSectionKind.circles:
                  case SearchSuggestionSectionKind.locations:
                  case SearchSuggestionSectionKind.followedPeople:
                  case SearchSuggestionSectionKind.network:
                    return;
                }
              },
            ),
        ],
      ),
    );
  }

  Widget _buildAvatarSuggestionGrid({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
  }) {
    return _SuggestionSurface(
      isDark: isDark,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: section.visibleItems.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 4,
            crossAxisSpacing: _SearchTokens.inspirationGridGap,
            mainAxisSpacing: _SearchTokens.inspirationGridGap,
            childAspectRatio: 0.64,
          ),
          itemBuilder: (context, index) {
            final entry = section.visibleItems[index];
            return _AvatarSuggestionCard(
              entry: entry,
              query: query,
              isDark: isDark,
              onTap: () => _handleGridSuggestionTap(entry),
            );
          },
        ),
      ),
    );
  }

  Widget _buildObjectSuggestionGrid({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
  }) {
    return _SuggestionSurface(
      isDark: isDark,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: section.visibleItems.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 3,
            crossAxisSpacing: _SearchTokens.inspirationGridGap,
            mainAxisSpacing: _SearchTokens.inspirationGridGap,
            childAspectRatio: 0.78,
          ),
          itemBuilder: (context, index) {
            final entry = section.visibleItems[index];
            return _ObjectSuggestionCard(
              entry: entry,
              query: query,
              isDark: isDark,
              onTap: () => _handleGridSuggestionTap(entry),
            );
          },
        ),
      ),
    );
  }

  Widget _buildNetworkSuggestionTags({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
  }) {
    return _SuggestionSurface(
      isDark: isDark,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: [
            for (final entry in section.visibleItems)
              _NetworkSuggestionPill(
                entry: entry,
                isDark: isDark,
                onTap: () => _handleGridSuggestionTap(entry),
              ),
          ],
        ),
      ),
    );
  }

  void _handleGridSuggestionTap(SearchSuggestionEntry entry) {
    switch (entry.kind) {
      case SearchSuggestionEntryKind.contact:
        final contact = entry.cast<ContactSearchSuggestion>();
        _openConversation(contact.conversationId);
      case SearchSuggestionEntryKind.chatRecord:
        final record = entry.cast<ChatRecordSearchSuggestion>();
        _openConversation(
          record.conversationId,
          messageAnchorId: record.messageAnchorId,
        );
      case SearchSuggestionEntryKind.circle:
        final circle = entry.cast<CircleSearchItemView>();
        _openCircle(circle.circleId);
      case SearchSuggestionEntryKind.location:
        final location = entry.cast<LocationPoiDto>();
        _openNetworkResults(location.name, initialTabId: 'all');
      case SearchSuggestionEntryKind.followedPerson:
        final person = entry.cast<SocialRelationSearchItemView>();
        _openUserProfile(person.subAccountId);
      case SearchSuggestionEntryKind.network:
        final network = entry.cast<NetworkSearchSuggestion>();
        _openNetworkResults(network.query, initialTabId: network.initialTabId);
    }
  }

  Widget _buildSuggestionItem({
    required SearchSuggestionEntry item,
    required String query,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    switch (item.kind) {
      case SearchSuggestionEntryKind.contact:
        final contact = item.cast<ContactSearchSuggestion>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: contact.avatarUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_fill,
          ),
          title: _highlightedText(
            contact.displayName,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            contact.subtitle ?? '联系人',
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openConversation(contact.conversationId),
        );
      case SearchSuggestionEntryKind.chatRecord:
        final record = item.cast<ChatRecordSearchSuggestion>();
        return _ChatRecordTile(
          suggestion: record,
          query: query,
          isDark: isDark,
          onTap: () => _openConversation(
            record.conversationId,
            messageAnchorId: record.messageAnchorId,
          ),
        );
      case SearchSuggestionEntryKind.circle:
        final circle = item.cast<CircleSearchItemView>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: circle.coverUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_3_fill,
          ),
          title: _highlightedText(
            circle.name,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            circle.description?.trim().isNotEmpty == true
                ? circle.description!.trim()
                : (circle.subCategory?.trim().isNotEmpty == true
                      ? circle.subCategory!.trim()
                      : '圈子'),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openCircle(circle.circleId),
        );
      case SearchSuggestionEntryKind.location:
        final location = item.cast<LocationPoiDto>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: null,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.location_solid,
          ),
          title: _highlightedText(
            location.name,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            (location.address ?? '').trim().isNotEmpty
                ? location.address!.trim()
                : '已关注地点',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openNetworkResults(location.name, initialTabId: 'all'),
        );
      case SearchSuggestionEntryKind.followedPerson:
        final person = item.cast<SocialRelationSearchItemView>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: person.avatarUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_crop_circle_fill,
          ),
          title: _highlightedText(
            person.displayName,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            person.headline?.trim().isNotEmpty == true
                ? person.headline!.trim()
                : '已关注 · 共同兴趣相关',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openUserProfile(person.subAccountId),
        );
      case SearchSuggestionEntryKind.network:
        final network = item.cast<NetworkSearchSuggestion>();
        return _BasicSuggestionTile(
          leading: Icon(
            CupertinoIcons.search,
            color: AppColors.primaryColor,
            size: AppSpacing.iconMedium,
          ),
          title: _highlightedText(
            network.displayTitle,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            network.subtitle ?? '',
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          trailing: Icon(
            CupertinoIcons.chevron_forward,
            color: fgSecondary,
            size: AppSpacing.iconSmall,
          ),
          onTap: () => _openNetworkResults(
            network.query,
            initialTabId: network.initialTabId,
          ),
        );
    }
  }

  void _openConversation(String conversationId, {String? messageAnchorId}) {
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(
      AppRoutePaths.chatDetail(id: conversationId),
      extra: messageAnchorId == null
          ? null
          : SearchConversationAnchorContext(
              messageAnchorId: messageAnchorId,
              sourceQuery: _searchSession.query.trim(),
            ),
    );
  }

  void _openCircle(String circleId) {
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(AppRoutePaths.circleDetail(id: circleId));
  }

  void _openUserProfile(String userId) {
    final normalized = userId.trim();
    if (normalized.isEmpty) {
      return;
    }
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(AppRoutePaths.userProfile(username: normalized));
  }

  void _openNetworkResults(String query, {String? initialTabId}) {
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return;
    }
    final selection = _searchSession.selection.normalized();
    final effectiveInitialTabId =
        initialTabId ?? _defaultNetworkTabIdForSelection(selection);
    unawaited(_coordinator.rememberCurrentQuery(query: trimmedQuery));
    context.push(
      AppRoutePaths.globalSearchNetworkResults(
        query: trimmedQuery,
        tab: effectiveInitialTabId,
      ),
      extra: widget.launchContext.copyWith(
        prefilledQuery: trimmedQuery,
        initialNetworkTabId: effectiveInitialTabId,
        initialScope: _searchSession.scope,
        initialFacet: selection.toFacet(),
        searchObjectSelection: selection,
        restoreState: false,
      ),
    );
  }

  String _defaultNetworkTabIdForSelection(SearchObjectSelection selection) {
    return 'all';
  }

  void _handleSearchSubmitted(String value) {
    final trimmedValue = value.trim();
    _coordinator.updateQuery(trimmedValue, immediate: true);
    if (trimmedValue.isEmpty) {
      return;
    }
    if (!_allowsNetworkResults(_searchSession.selection)) {
      _focusNode.unfocus();
      return;
    }
    _openNetworkResults(trimmedValue);
  }

  Future<void> _confirmClearHistory() async {
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text('清空搜索历史'),
          content: const Padding(
            padding: EdgeInsets.only(top: AppSpacing.containerXs),
            child: Text('将移除全部搜索历史记录，且无法恢复。'),
          ),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('取消'),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('清空'),
            ),
          ],
        );
      },
    );
    if (confirmed == true) {
      await _coordinator.clearRecentSearches();
    }
  }

  void _handleClose() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.home);
  }

  void _syncControllerText(String query) {
    if (_controller.text == query) {
      return;
    }
    _controller.value = TextEditingValue(
      text: query,
      selection: TextSelection.collapsed(offset: query.length),
    );
  }
}

class _SearchHistoryToolbar extends StatelessWidget {
  const _SearchHistoryToolbar({
    required this.expanded,
    required this.managing,
    required this.onToggleExpanded,
    required this.onStartManaging,
    required this.onClearAll,
    required this.onDone,
  });

  final bool expanded;
  final bool managing;
  final VoidCallback onToggleExpanded;
  final VoidCallback onStartManaging;
  final VoidCallback onClearAll;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgTertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final divider = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    return Row(
      children: [
        Expanded(
          child: Text(
            '搜索历史',
            style: TextStyle(
              fontSize: _SearchTokens.toolbarSize,
              fontWeight: _SearchTokens.toolbarWeight,
              color: fgTertiary,
            ),
          ),
        ),
        if (managing) ...[
          CupertinoButton(
            key: TestKeys.searchHistoryClearButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onClearAll,
            child: Text(
              '全部删除',
              style: TextStyle(
                fontSize: _SearchTokens.toolbarSize,
                fontWeight: _SearchTokens.toolbarActionWeight,
                color: fgSecondary,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.interGroupMd),
          CupertinoButton(
            key: TestKeys.searchHistoryDoneButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onDone,
            child: Text(
              '完成',
              style: TextStyle(
                fontSize: _SearchTokens.toolbarSize,
                fontWeight: _SearchTokens.toolbarActionWeight,
                color: fgSecondary,
              ),
            ),
          ),
        ] else ...[
          CupertinoButton(
            key: TestKeys.searchHistoryExpandButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onToggleExpanded,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  expanded ? '收起' : '展开',
                  style: TextStyle(
                    fontSize: _SearchTokens.toolbarSize,
                    fontWeight: _SearchTokens.toolbarWeight,
                    color: fgTertiary,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
                Icon(
                  expanded
                      ? CupertinoIcons.chevron_up
                      : CupertinoIcons.chevron_down,
                  size: AppSpacing.iconSmall,
                  color: fgTertiary,
                ),
              ],
            ),
          ),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.interGroupSm),
            child: SizedBox(
              width: AppSpacing.hairline,
              height: AppSpacing.iconMedium,
              child: DecoratedBox(decoration: BoxDecoration(color: divider)),
            ),
          ),
          CupertinoButton(
            key: TestKeys.searchHistoryManageButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
            onPressed: onStartManaging,
            child: Icon(
              CupertinoIcons.delete,
              size: AppSpacing.iconMedium,
              color: fgTertiary,
            ),
          ),
        ],
      ],
    );
  }
}

class _SearchHistoryGridItem extends StatelessWidget {
  const _SearchHistoryGridItem({
    required this.entry,
    required this.isDark,
    required this.managing,
    required this.onTap,
    required this.onRemove,
  });

  final RecentSearchEntryView entry;
  final bool isDark;
  final bool managing;
  final VoidCallback? onTap;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final pres = RecentSearchReadPresentation.fromEntry(entry);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgTertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: managing ? () {} : onTap,
      child: Row(
        children: [
          Expanded(
            child: Text(
              pres.displayQuery,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: _SearchTokens.bodySize,
                fontWeight: _SearchTokens.bodyWeight,
                color: fgPrimary,
                height: AppTypography.lineHeightTight,
              ),
            ),
          ),
          if (managing && onRemove != null) ...[
            SizedBox(width: AppSpacing.intraGroupSm),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onRemove,
              child: SizedBox.square(
                dimension: AppSpacing.iconButtonMinSizeSm,
                child: Center(
                  child: Icon(
                    CupertinoIcons.xmark,
                    size: AppSpacing.iconSmall,
                    color: fgTertiary,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _SearchSectionHeader extends StatelessWidget {
  const _SearchSectionHeader({
    required this.title,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: TextStyle(
              fontSize: _SearchTokens.sectionTitleSize,
              fontWeight: _SearchTokens.sectionTitleWeight,
              color: fgPrimary,
            ),
          ),
        ),
        if (actionLabel != null && onAction != null)
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onAction,
            child: Text(
              actionLabel!,
              style: TextStyle(
                fontSize: _SearchTokens.toolbarSize,
                fontWeight: _SearchTokens.toolbarWeight,
                color: fgSecondary,
              ),
            ),
          ),
      ],
    );
  }
}

class _RecentSearchPill extends StatelessWidget {
  const _RecentSearchPill({
    required this.entry,
    required this.isDark,
    required this.onTap,
  });

  final RecentSearchEntryView entry;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final pres = RecentSearchReadPresentation.fromEntry(entry);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.toolbarMinTouchHeight),
      onPressed: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupXs,
          ),
          child: Text(
            pres.displayQuery,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: _SearchTokens.cardTitleSize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

class _TodayIntersectionSection extends StatelessWidget {
  const _TodayIntersectionSection({
    required this.items,
    required this.isDark,
    required this.onTap,
  });

  final List<SearchInspirationChipView> items;
  final bool isDark;
  final ValueChanged<SearchInspirationChipView> onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SearchSectionHeader(title: '今日交集'),
        SizedBox(height: _SearchTokens.headerContentGap),
        GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: items.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 4,
            crossAxisSpacing: _SearchTokens.inspirationGridGap,
            mainAxisSpacing: _SearchTokens.inspirationGridGap,
            childAspectRatio: 0.9,
          ),
          itemBuilder: (context, index) {
            final item = items[index];
            return _InspirationTextCard(
              title: item.title,
              subtitle: item.subtitle,
              isDark: isDark,
              onTap: () => onTap(item),
            );
          },
        ),
      ],
    );
  }
}

class _InspirationCardGridSection extends StatelessWidget {
  const _InspirationCardGridSection({
    required this.title,
    required this.items,
    required this.isDark,
    required this.fallbackIcon,
    required this.onTap,
  });

  final String title;
  final List<SearchInspirationCardView> items;
  final bool isDark;
  final IconData fallbackIcon;
  final ValueChanged<SearchInspirationCardView> onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SearchSectionHeader(title: title),
        SizedBox(height: _SearchTokens.headerContentGap),
        GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: items.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 3,
            crossAxisSpacing: _SearchTokens.inspirationGridGap,
            mainAxisSpacing: _SearchTokens.inspirationGridGap,
            childAspectRatio: 0.82,
          ),
          itemBuilder: (context, index) {
            final item = items[index];
            return _InspirationGridCard(
              item: item,
              isDark: isDark,
              fallbackIcon: fallbackIcon,
              onTap: () => onTap(item),
            );
          },
        ),
      ],
    );
  }
}

class _InspirationTextCard extends StatelessWidget {
  const _InspirationTextCard({
    required this.title,
    required this.subtitle,
    required this.isDark,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.toolbarMinTouchHeight),
      onPressed: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          border: Border.all(color: border),
        ),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: _SearchTokens.cardTitleSize,
                  fontWeight: _SearchTokens.bodyWeight,
                  color: fgPrimary,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                subtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: _SearchTokens.captionSize,
                  fontWeight: _SearchTokens.bodyWeight,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InspirationGridCard extends StatelessWidget {
  const _InspirationGridCard({
    required this.item,
    required this.isDark,
    required this.fallbackIcon,
    required this.onTap,
  });

  final SearchInspirationCardView item;
  final bool isDark;
  final IconData fallbackIcon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final imageUrl = (item.coverUrl ?? '').trim();
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.toolbarMinTouchHeight),
      onPressed: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.intraGroupXs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(
                    AppSpacing.smallBorderRadius,
                  ),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.backgroundSecondary,
                      ),
                    ),
                    child: imageUrl.isEmpty
                        ? Icon(
                            fallbackIcon,
                            size: AppSpacing.iconMedium,
                            color: fgSecondary,
                          )
                        : Image.network(
                            imageUrl,
                            fit: BoxFit.cover,
                            errorBuilder: (context, error, stackTrace) {
                              return Icon(
                                fallbackIcon,
                                size: AppSpacing.iconMedium,
                                color: fgSecondary,
                              );
                            },
                          ),
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                item.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: _SearchTokens.cardTitleSize,
                  fontWeight: _SearchTokens.bodyWeight,
                  color: fgPrimary,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs / 2),
              Text(
                item.subtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InspirationPeopleSection extends StatelessWidget {
  const _InspirationPeopleSection({
    required this.people,
    required this.isDark,
    required this.onTap,
  });

  final List<SearchInspirationPersonView> people;
  final bool isDark;
  final ValueChanged<SearchInspirationPersonView> onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _SearchSectionHeader(title: '同趣的人'),
        SizedBox(height: _SearchTokens.headerContentGap),
        GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: people.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 4,
            crossAxisSpacing: _SearchTokens.inspirationGridGap,
            mainAxisSpacing: _SearchTokens.inspirationGridGap,
            childAspectRatio: 0.62,
          ),
          itemBuilder: (context, index) {
            final person = people[index];
            return _InspirationPersonCard(
              person: person,
              isDark: isDark,
              onTap: () => onTap(person),
            );
          },
        ),
      ],
    );
  }
}

class _InspirationPersonCard extends StatelessWidget {
  const _InspirationPersonCard({
    required this.person,
    required this.isDark,
    required this.onTap,
  });

  final SearchInspirationPersonView person;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.toolbarMinTouchHeight),
      onPressed: onTap,
      child: Column(
        children: [
          _buildConversationLeading(
            avatarUrl: person.avatarUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_crop_circle_fill,
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            person.displayName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: _SearchTokens.cardTitleSize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          Text(
            person.headline,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          Text(
            person.reason,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _SuggestionSurface extends StatelessWidget {
  const _SuggestionSurface({required this.isDark, required this.child});

  final bool isDark;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorSubtle,
          ),
        ),
      ),
      child: child,
    );
  }
}

class _AvatarSuggestionCard extends StatelessWidget {
  const _AvatarSuggestionCard({
    required this.entry,
    required this.query,
    required this.isDark,
    required this.onTap,
  });

  final SearchSuggestionEntry entry;
  final String query;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final data = switch (entry.kind) {
      SearchSuggestionEntryKind.contact => _AvatarSuggestionData.fromContact(
        entry.cast<ContactSearchSuggestion>(),
      ),
      SearchSuggestionEntryKind.followedPerson =>
        _AvatarSuggestionData.fromPerson(
          entry.cast<SocialRelationSearchItemView>(),
        ),
      _ => const _AvatarSuggestionData(
        title: '',
        subtitle: '',
        reason: '',
        avatarUrl: null,
      ),
    };
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.toolbarMinTouchHeight),
      onPressed: onTap,
      child: Column(
        children: [
          _buildConversationLeading(
            avatarUrl: data.avatarUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_crop_circle_fill,
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          _highlightedText(
            data.title,
            query,
            TextStyle(
              fontSize: _SearchTokens.cardTitleSize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          Text(
            data.subtitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          if (data.reason.trim().isNotEmpty) ...[
            SizedBox(height: AppSpacing.intraGroupXs / 2),
            Text(
              data.reason,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: fgSecondary,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ObjectSuggestionCard extends StatelessWidget {
  const _ObjectSuggestionCard({
    required this.entry,
    required this.query,
    required this.isDark,
    required this.onTap,
  });

  final SearchSuggestionEntry entry;
  final String query;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final data = switch (entry.kind) {
      SearchSuggestionEntryKind.circle => _ObjectSuggestionData.fromCircle(
        entry.cast<CircleSearchItemView>(),
      ),
      SearchSuggestionEntryKind.location => _ObjectSuggestionData.fromLocation(
        entry.cast<LocationPoiDto>(),
      ),
      _ => const _ObjectSuggestionData(
        title: '',
        subtitle: '',
        coverUrl: null,
        fallbackIcon: CupertinoIcons.search,
      ),
    };
    final coverUrl = (data.coverUrl ?? '').trim();
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.toolbarMinTouchHeight),
      onPressed: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.backgroundSecondary,
                  ),
                ),
                child: coverUrl.isEmpty
                    ? Icon(
                        data.fallbackIcon,
                        size: AppSpacing.iconMedium,
                        color: fgSecondary,
                      )
                    : Image.network(
                        coverUrl,
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) {
                          return Icon(
                            data.fallbackIcon,
                            size: AppSpacing.iconMedium,
                            color: fgSecondary,
                          );
                        },
                      ),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          _highlightedText(
            data.title,
            query,
            TextStyle(
              fontSize: _SearchTokens.cardTitleSize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          Text(
            data.subtitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _NetworkSuggestionPill extends StatelessWidget {
  const _NetworkSuggestionPill({
    required this.entry,
    required this.isDark,
    required this.onTap,
  });

  final SearchSuggestionEntry entry;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final network = entry.cast<NetworkSearchSuggestion>();
    return _RecentSearchPill(
      entry: RecentSearchEntryView(
        entryId: '${network.query}_${network.initialTabId ?? ''}',
        query: network.displayTitle,
        scope: SearchScope.all,
        facet: null,
        updatedAt: DateTime.now(),
      ),
      isDark: isDark,
      onTap: onTap,
    );
  }
}

class _AvatarSuggestionData {
  const _AvatarSuggestionData({
    required this.title,
    required this.subtitle,
    required this.reason,
    required this.avatarUrl,
  });

  final String title;
  final String subtitle;
  final String reason;
  final String? avatarUrl;

  factory _AvatarSuggestionData.fromContact(ContactSearchSuggestion item) {
    return _AvatarSuggestionData(
      title: item.displayName,
      subtitle: item.subtitle ?? '共同圈子 2 个',
      reason: '',
      avatarUrl: item.avatarUrl,
    );
  }

  factory _AvatarSuggestionData.fromPerson(SocialRelationSearchItemView item) {
    return _AvatarSuggestionData(
      title: item.displayName,
      subtitle: item.relationshipCapability.canUnfollow ? '已关注' : '同趣的人',
      reason: '共同兴趣 3 个',
      avatarUrl: item.avatarUrl,
    );
  }
}

class _ObjectSuggestionData {
  const _ObjectSuggestionData({
    required this.title,
    required this.subtitle,
    required this.coverUrl,
    required this.fallbackIcon,
  });

  final String title;
  final String subtitle;
  final String? coverUrl;
  final IconData fallbackIcon;

  factory _ObjectSuggestionData.fromCircle(CircleSearchItemView item) {
    return _ObjectSuggestionData(
      title: item.name,
      subtitle: '已加入',
      coverUrl: item.coverUrl,
      fallbackIcon: CupertinoIcons.person_3_fill,
    );
  }

  factory _ObjectSuggestionData.fromLocation(LocationPoiDto item) {
    return _ObjectSuggestionData(
      title: item.name,
      subtitle: '已关注',
      coverUrl: null,
      fallbackIcon: CupertinoIcons.location_solid,
    );
  }
}

class _BasicSuggestionTile extends StatelessWidget {
  const _BasicSuggestionTile({
    required this.leading,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.trailing,
  });

  final Widget leading;
  final Widget title;
  final Widget? subtitle;
  final Widget? trailing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          leading,
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                title,
                if (subtitle case final subtitleWidget?) ...[
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  subtitleWidget,
                ],
              ],
            ),
          ),
          if (trailing case final trailingWidget?) ...[
            SizedBox(width: AppSpacing.containerSm),
            trailingWidget,
          ],
        ],
      ),
    );
  }
}

class _ChatRecordTile extends StatelessWidget {
  const _ChatRecordTile({
    required this.suggestion,
    required this.query,
    required this.isDark,
    required this.onTap,
  });

  final ChatRecordSearchSuggestion suggestion;
  final String query;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return CupertinoButton(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ConversationAvatar(
            conversationId: suggestion.conversationId,
            conversationType: suggestion.conversationType,
            title: suggestion.conversationTitle,
            avatarUrl: suggestion.avatarUrl ?? '',
            size: AppSpacing.avatarUserMd,
            borderRadius: AppSpacing.avatarUserMd / 2,
            groupFallbackIcon: CupertinoIcons.person_2_fill,
            directFallbackIcon: CupertinoIcons.chat_bubble_2_fill,
          ),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _highlightedText(
                        suggestion.conversationTitle,
                        query,
                        TextStyle(
                          fontSize: _SearchTokens.bodySize,
                          fontWeight: _SearchTokens.bodyWeight,
                          color: fgPrimary,
                        ),
                      ),
                    ),
                    if (suggestion.timestamp case final timestamp?)
                      Text(
                        _formatDayLabel(timestamp),
                        style: TextStyle(
                          fontSize: AppTypography.iosCaption1,
                          color: fgSecondary,
                        ),
                      ),
                  ],
                ),
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                _highlightedText(
                  suggestion.matchedPreview,
                  query,
                  TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary,
                  ),
                  maxLines: 2,
                ),
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  '共 ${suggestion.matchCount} 条相关的聊天记录',
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.primaryColor,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MoreActionRow extends StatelessWidget {
  const _MoreActionRow({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = CupertinoColors.secondaryLabel.resolveFrom(context);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: fgSecondary,
          ),
        ),
      ),
    );
  }
}

class _DividerLine extends StatelessWidget {
  const _DividerLine({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Container(
        height: AppSpacing.one,
        color: AppColorsFunctional.getColor(isDark, ColorType.separatorSubtle),
      ),
    );
  }
}

Widget _highlightedText(
  String text,
  String query,
  TextStyle style, {
  int maxLines = 1,
}) {
  final trimmedQuery = query.trim();
  if (text.trim().isEmpty) {
    return Text('', style: style);
  }
  if (trimmedQuery.isEmpty) {
    return Text(
      text,
      maxLines: maxLines,
      overflow: TextOverflow.ellipsis,
      style: style,
    );
  }
  final pattern = RegExp(RegExp.escape(trimmedQuery), caseSensitive: false);
  final matches = pattern.allMatches(text).toList(growable: false);
  if (matches.isEmpty) {
    return Text(
      text,
      maxLines: maxLines,
      overflow: TextOverflow.ellipsis,
      style: style,
    );
  }
  final spans = <TextSpan>[];
  var cursor = 0;
  for (final match in matches) {
    if (match.start > cursor) {
      spans.add(
        TextSpan(text: text.substring(cursor, match.start), style: style),
      );
    }
    spans.add(
      TextSpan(
        text: text.substring(match.start, match.end),
        style: style.copyWith(
          color: AppColors.primaryColor,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
    cursor = match.end;
  }
  if (cursor < text.length) {
    spans.add(TextSpan(text: text.substring(cursor), style: style));
  }
  return Text.rich(
    TextSpan(children: spans),
    maxLines: maxLines,
    overflow: TextOverflow.ellipsis,
  );
}

Widget _buildConversationLeading({
  required String? avatarUrl,
  required bool isDark,
  required IconData fallbackIcon,
}) {
  final effectiveImageUrl = (avatarUrl ?? '').trim();
  if (effectiveImageUrl.isNotEmpty) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.avatarUserMd / 2),
      child: Container(
        width: AppSpacing.avatarUserMd,
        height: AppSpacing.avatarUserMd,
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundSecondary,
        ),
        child: Image.network(
          effectiveImageUrl,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) {
            return Icon(
              fallbackIcon,
              size: AppSpacing.iconMedium,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            );
          },
        ),
      ),
    );
  }
  return ClipRRect(
    borderRadius: BorderRadius.circular(AppSpacing.avatarUserMd / 2),
    child: Container(
      width: AppSpacing.avatarUserMd,
      height: AppSpacing.avatarUserMd,
      color: AppColorsFunctional.getColor(
        isDark,
        ColorType.backgroundSecondary,
      ),
      child: Icon(
        fallbackIcon,
        size: AppSpacing.iconMedium,
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.foregroundSecondary,
        ),
      ),
    ),
  );
}

String _formatDayLabel(DateTime value) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final target = DateTime(value.year, value.month, value.day);
  final difference = today.difference(target).inDays;
  if (difference <= 0) {
    return '今天';
  }
  if (difference == 1) {
    return '昨天';
  }
  return '${value.month}月${value.day}日';
}
