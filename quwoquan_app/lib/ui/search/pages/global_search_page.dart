import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/conversation_avatar.dart';
import 'package:quwoquan_app/cloud/runtime/models/recent_search_read_presentation.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/ui/search/providers/search_coordinator.dart';

/// 搜索域统一语义 token。
///
/// 字体四级：
/// - L1 区块标题 [sectionTitleSize] + [sectionTitleWeight] + foregroundPrimary
/// - L2 正文/列表主文本 [bodySize] + [bodyWeight] + foregroundPrimary
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
  static const double captionSize = AppTypography.iosCaption1; // L4 12
  static const double toolbarSize = AppTypography.iosSubheadline; // 工具栏 15
  static const FontWeight bodyWeight = AppTypography.regular;
  static const FontWeight toolbarWeight = AppTypography.regular;
  static const FontWeight toolbarActionWeight = AppTypography.medium;

  // ===== 间距层级 =====
  static const double headerContentGap = AppSpacing.intraGroupSm;
  static const double sectionGap = AppSpacing.interGroupLg;
  static const double historyColumnGap = AppSpacing.interGroupMd;
  static const double historyRowGap = AppSpacing.intraGroupLg;

  /// 搜索页正文左右边距：窄屏 containerMd，宽屏 containerLg。
  static double contentHorizontal(BuildContext context) =>
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerMd,
        regular: AppSpacing.containerMd,
        expanded: AppSpacing.containerLg,
      );
}

enum _SearchHomeTab { guess, circles, locations }

class GlobalSearchPage extends ConsumerStatefulWidget {
  const GlobalSearchPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<GlobalSearchPage> createState() => _GlobalSearchPageState();
}

class _GlobalSearchPageState extends ConsumerState<GlobalSearchPage> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  _SearchHomeTab _activeHomeTab = _SearchHomeTab.guess;
  late final DateTime _pageEnteredAt;
  bool _didTrackPageImpression = false;
  ContentBehaviorTracker? _behaviorTracker;
  String? _feedRequestIdAtEnter;

  SearchCoordinator get _coordinator =>
      ref.read(searchCoordinatorProvider(widget.launchContext).notifier);

  SearchSessionState get _searchSession =>
      ref.read(searchCoordinatorProvider(widget.launchContext));

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    _controller = TextEditingController(
      text: widget.launchContext.prefilledQuery,
    );
    _focusNode = FocusNode();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _focusNode.requestFocus();
      _trackPageImpressionIfNeeded();
    });
  }

  @override
  void dispose() {
    _trackPageDwell();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _trackPageImpressionIfNeeded() {
    if (_didTrackPageImpression) {
      return;
    }
    _didTrackPageImpression = true;
    _behaviorTracker = ref.read(contentBehaviorTrackerProvider);
    _feedRequestIdAtEnter = ref
        .read(feedSessionProvider.notifier)
        .currentFeedRequestId;
    _behaviorTracker!.trackImpression(
      'global_search',
      contentType: 'search_page',
      referralSource: ReferralSource.search,
      feedRequestId: _feedRequestIdAtEnter,
      tags: <String>[widget.launchContext.entrySurfaceId],
    );
  }

  void _trackPageDwell() {
    final tracker = _behaviorTracker;
    if (tracker == null) {
      return;
    }
    final elapsedSeconds =
        DateTime.now().difference(_pageEnteredAt).inMilliseconds / 1000.0;
    tracker.trackDwell(
      'global_search',
      durationSeconds: elapsedSeconds,
      contentType: 'search_page',
      referralSource: ReferralSource.search,
      feedRequestId: _feedRequestIdAtEnter,
      tags: <String>[widget.launchContext.entrySurfaceId],
    );
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
    final content = switch (_activeHomeTab) {
      _SearchHomeTab.guess => _GuessKeywordSection(
        terms: inspiration.guessKeywords,
        isDark: isDark,
        showHeader: false,
        onTap: (item) => _openNetworkResults(item.query, initialTabId: 'all'),
      ),
      _SearchHomeTab.circles => _HotEntityListSection(
        title: '热门圈子',
        items: inspiration.hotCircles,
        isDark: isDark,
        showHeader: false,
        fallbackIcon: CupertinoIcons.person_3_fill,
        imageStyle: _HotEntityImageStyle.avatar,
        onTap: (item) =>
            _openNetworkResults(item.query ?? item.title, initialTabId: 'all'),
      ),
      _SearchHomeTab.locations => _HotEntityListSection(
        title: '热门地点',
        items: inspiration.hotLocations,
        isDark: isDark,
        showHeader: false,
        fallbackIcon: CupertinoIcons.location_solid,
        imageStyle: _HotEntityImageStyle.cover,
        onTap: (item) =>
            _openNetworkResults(item.query ?? item.title, initialTabId: 'all'),
      ),
    };
    return <Widget>[
      _SearchHomeTabBar(
        activeTab: _activeHomeTab,
        onChanged: (tab) {
          setState(() {
            _activeHomeTab = tab;
          });
        },
        onRefresh: _activeHomeTab == _SearchHomeTab.guess
            ? _coordinator.refreshGuessKeywords
            : null,
      ),
      SizedBox(height: _SearchTokens.headerContentGap),
      content,
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
          SearchSuggestionSectionKind.network => _buildKeywordSuggestionList(
            section: section,
            query: query,
            isDark: isDark,
          ),
          SearchSuggestionSectionKind.contacts ||
          SearchSuggestionSectionKind.followedPeople ||
          SearchSuggestionSectionKind.circles ||
          SearchSuggestionSectionKind.locations ||
          SearchSuggestionSectionKind.chatRecords => _buildPlainSuggestionList(
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

  Widget _buildPlainSuggestionList({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return Column(
      children: [
        for (var i = 0; i < section.visibleItems.length; i++) ...[
          _buildSuggestionItem(
            item: section.visibleItems[i],
            query: query,
            isDark: isDark,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          if (i != section.visibleItems.length - 1)
            _DividerLine(isDark: isDark),
        ],
      ],
    );
  }

  Widget _buildKeywordSuggestionList({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
  }) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Column(
      children: [
        for (var i = 0; i < section.visibleItems.length; i++) ...[
          _KeywordSuggestionRow(
            entry: section.visibleItems[i],
            query: query,
            color: fgPrimary,
            onTap: () => _handleGridSuggestionTap(section.visibleItems[i]),
          ),
          if (i != section.visibleItems.length - 1)
            _DividerLine(isDark: isDark),
        ],
      ],
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
                : '已关注',
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
  const _SearchSectionHeader({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
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
      ],
    );
  }
}

class _SearchHomeTabBar extends StatelessWidget {
  const _SearchHomeTabBar({
    required this.activeTab,
    required this.onChanged,
    this.onRefresh,
  });

  final _SearchHomeTab activeTab;
  final ValueChanged<_SearchHomeTab> onChanged;
  final VoidCallback? onRefresh;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final tabs = <_SearchHomeTab, String>{
      _SearchHomeTab.guess: '猜你想搜',
      _SearchHomeTab.circles: '热门圈子',
      _SearchHomeTab.locations: '热门地点',
    };
    return Row(
      children: [
        for (final entry in tabs.entries) ...[
          _SearchHomeTabButton(
            label: entry.value,
            selected: entry.key == activeTab,
            isDark: isDark,
            onTap: () => onChanged(entry.key),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
        ],
        const Spacer(),
        if (onRefresh != null)
          CupertinoButton(
            key: const ValueKey<String>('search_home_guess_refresh_button'),
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
            onPressed: onRefresh,
            child: Icon(
              CupertinoIcons.refresh,
              size: AppSpacing.iconMedium,
              color: AppColors.primaryColor,
            ),
          ),
      ],
    );
  }
}

class _SearchHomeTabButton extends StatelessWidget {
  const _SearchHomeTabButton({
    required this.label,
    required this.selected,
    required this.isDark,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: selected
              ? AppColors.primaryColor.withValues(alpha: 0.1)
              : CupertinoColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupXs,
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: selected
                  ? AppTypography.medium
                  : _SearchTokens.bodyWeight,
              color: selected ? AppColors.primaryColor : fgSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

class _GuessKeywordSection extends StatelessWidget {
  const _GuessKeywordSection({
    required this.terms,
    required this.isDark,
    this.showHeader = true,
    required this.onTap,
  });

  final List<NetworkSearchSuggestion> terms;
  final bool isDark;
  final bool showHeader;
  final ValueChanged<NetworkSearchSuggestion> onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showHeader) ...[
          const _SearchSectionHeader(title: '猜你想搜'),
          SizedBox(height: _SearchTokens.headerContentGap),
        ],
        GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: terms.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisExtent: AppSpacing.buttonHeightMd,
            crossAxisSpacing: _SearchTokens.historyColumnGap,
            mainAxisSpacing: _SearchTokens.historyRowGap,
          ),
          itemBuilder: (context, index) {
            final term = terms[index];
            return CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: () => onTap(term),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  term.displayTitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: _SearchTokens.bodySize,
                    fontWeight: _SearchTokens.bodyWeight,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundPrimary,
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ],
    );
  }
}

enum _HotEntityImageStyle { avatar, cover }

class _HotEntityListSection extends StatelessWidget {
  const _HotEntityListSection({
    required this.title,
    required this.items,
    required this.isDark,
    this.showHeader = true,
    required this.fallbackIcon,
    required this.imageStyle,
    required this.onTap,
  });

  final String title;
  final List<SearchInspirationCardView> items;
  final bool isDark;
  final bool showHeader;
  final IconData fallbackIcon;
  final _HotEntityImageStyle imageStyle;
  final ValueChanged<SearchInspirationCardView> onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showHeader) ...[
          _SearchSectionHeader(title: title),
          SizedBox(height: _SearchTokens.headerContentGap),
        ],
        for (var i = 0; i < items.length; i++) ...[
          _HotEntityListTile(
            item: items[i],
            isDark: isDark,
            fallbackIcon: fallbackIcon,
            imageStyle: imageStyle,
            onTap: () => onTap(items[i]),
          ),
          if (i != items.length - 1) SizedBox(height: AppSpacing.intraGroupSm),
        ],
      ],
    );
  }
}

class _HotEntityListTile extends StatelessWidget {
  const _HotEntityListTile({
    required this.item,
    required this.isDark,
    required this.fallbackIcon,
    required this.imageStyle,
    required this.onTap,
  });

  final SearchInspirationCardView item;
  final bool isDark;
  final IconData fallbackIcon;
  final _HotEntityImageStyle imageStyle;
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
    final imageSize = imageStyle == _HotEntityImageStyle.avatar
        ? AppSpacing.avatarUserMd
        : AppSpacing.avatarUserLg;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(
              imageStyle == _HotEntityImageStyle.avatar
                  ? imageSize / 2
                  : AppSpacing.smallBorderRadius,
            ),
            child: SizedBox.square(
              dimension: imageSize,
              child: DecoratedBox(
                decoration: BoxDecoration(color: surface),
                child: imageUrl.isEmpty
                    ? Icon(
                        fallbackIcon,
                        size: AppSpacing.iconMedium,
                        color: fgSecondary,
                      )
                    : AppCachedNetworkImage(
                        imageUrl: imageUrl,
                        fit: BoxFit.cover,
                        width: imageSize,
                        height: imageSize,
                        cdnPreset: imageStyle == _HotEntityImageStyle.avatar
                            ? CdnImagePreset.avatar
                            : CdnImagePreset.cover,
                        errorWidget: Icon(
                          fallbackIcon,
                          size: AppSpacing.iconMedium,
                          color: fgSecondary,
                        ),
                      ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: _SearchTokens.bodySize,
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
                    fontSize: _SearchTokens.captionSize,
                    color: fgSecondary,
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

class _KeywordSuggestionRow extends StatelessWidget {
  const _KeywordSuggestionRow({
    required this.entry,
    required this.query,
    required this.color,
    required this.onTap,
  });

  final SearchSuggestionEntry entry;
  final String query;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final network = entry.cast<NetworkSearchSuggestion>();
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Align(
        alignment: Alignment.centerLeft,
        child: _highlightedText(
          network.displayTitle,
          query,
          TextStyle(
            fontSize: _SearchTokens.bodySize,
            fontWeight: _SearchTokens.bodyWeight,
            color: color,
          ),
        ),
      ),
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
  if (text.trim().isEmpty) {
    return Text('', style: style);
  }
  final spans = SearchHighlightSpan.build(text: text, keyword: query);
  if (spans.length == 1 && !spans.first.isMatch) {
    return Text(
      text,
      maxLines: maxLines,
      overflow: TextOverflow.ellipsis,
      style: style,
    );
  }
  return Text.rich(
    TextSpan(
      children: spans
          .map(
            (span) => TextSpan(
              text: span.text,
              style: span.isMatch
                  ? style.copyWith(
                      color: AppColors.primaryColor,
                      fontWeight: AppTypography.medium,
                    )
                  : style,
            ),
          )
          .toList(growable: false),
    ),
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
        child: AppAvatarImage(
          imageUrl: effectiveImageUrl,
          size: AppSpacing.avatarUserMd,
          fit: BoxFit.cover,
          errorWidget: Icon(
            fallbackIcon,
            size: AppSpacing.iconMedium,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundSecondary,
            ),
          ),
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
