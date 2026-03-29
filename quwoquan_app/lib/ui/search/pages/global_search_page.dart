import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/group_avatar_grid.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/search/providers/search_coordinator.dart';

class GlobalSearchPage extends ConsumerStatefulWidget {
  const GlobalSearchPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<GlobalSearchPage> createState() => _GlobalSearchPageState();
}

class _GlobalSearchPageState extends ConsumerState<GlobalSearchPage> {
  static const int _collapsedHistoryCount = 6;

  late final TextEditingController _controller;
  late final FocusNode _focusNode;

  SearchCoordinator get _coordinator =>
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
    final coordinator = ref.watch(
      searchCoordinatorProvider(widget.launchContext),
    );
    final state = coordinator.state;
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
    final fgTertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );
    final mutedSurface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    _syncControllerText(state.query);

    return AppFullscreenModalSurface(
      surfaceKey: TestKeys.fullscreenModalSurface,
      backgroundColor: backgroundColor,
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerXs,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildSearchBar(state, fgSecondary),
          SizedBox(height: AppSpacing.containerSm),
          _buildSearchObjectSelector(
            state: state,
            isDark: isDark,
            fgSecondary: fgSecondary,
            mutedSurface: mutedSurface,
          ),
          SizedBox(height: AppSpacing.containerSm),
          Expanded(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 180),
              child: switch (state.viewMode) {
                SearchViewMode.historyBrowse => _buildHistoryView(
                  key: const ValueKey<String>('search_history_browse'),
                  state: state,
                  fgSecondary: fgSecondary,
                  fgTertiary: fgTertiary,
                  isDark: isDark,
                  manageMode: false,
                ),
                SearchViewMode.historyManage => _buildHistoryView(
                  key: const ValueKey<String>('search_history_manage'),
                  state: state,
                  fgSecondary: fgSecondary,
                  fgTertiary: fgTertiary,
                  isDark: isDark,
                  manageMode: true,
                ),
                SearchViewMode.liveSuggestions => _buildSuggestionView(
                  key: const ValueKey<String>('search_live_suggestions'),
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
    );
  }

  Widget _buildSearchBar(SearchSessionState state, Color fgSecondary) {
    return Row(
      children: [
        CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: Size.zero,
          onPressed: _handleClose,
          child: Icon(
            CupertinoIcons.chevron_back,
            color: fgSecondary,
            size: AppSpacing.iconLarge,
          ),
        ),
        SizedBox(width: AppSpacing.containerSm),
        Expanded(
          child: AppSearchField(
            key: const ValueKey<String>('global_search_field'),
            controller: _controller,
            focusNode: _focusNode,
            autofocus: true,
            placeholder: UITextConstants.globalSearchTitle,
            onChanged: (value) => _coordinator.updateQuery(value),
            onSubmitted: _handleSearchSubmitted,
          ),
        ),
        if (state.isLoading) ...[
          SizedBox(width: AppSpacing.intraGroupSm),
          const CupertinoActivityIndicator(radius: 8),
        ],
      ],
    );
  }

  Widget _buildSearchObjectSelector({
    required SearchSessionState state,
    required bool isDark,
    required Color fgSecondary,
    required Color mutedSurface,
  }) {
    final selection = state.selection.normalized();
    final selectionBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionBackground,
    );
    final selectionForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionForeground,
    );
    final selectionBorder = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionBorder,
    );
    final fgTertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );

    return Column(
      key: TestKeys.globalSearchObjectSelector,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CupertinoButton(
          key: TestKeys.searchContentSelectorButton,
          padding: EdgeInsets.zero,
          minimumSize: Size.zero,
          onPressed: _openContentTypeSelector,
          child: Row(
            children: [
              Text(
                '搜索指定内容',
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: fgTertiary,
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: fgTertiary,
              ),
              const Spacer(),
              Text(
                _buildContentSelectionSummary(selection),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.medium,
                  color: selection.isAllContent
                      ? fgSecondary
                      : AppColors.primaryColor,
                ),
              ),
            ],
          ),
        ),
        SizedBox(height: AppSpacing.containerXs),
        SingleChildScrollView(
          key: TestKeys.globalSearchScopeRail,
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              _InlineSelectionChip(
                chipKey: TestKeys.searchScopeAllChip,
                label: '全部',
                isSelected: selection.activeObjectTarget == null,
                backgroundColor: mutedSurface,
                textColor: fgSecondary,
                selectedBackgroundColor: selectionBackground,
                selectedTextColor: selectionForeground,
                selectedBorderColor: selectionBorder,
                onTap: () => _selectObjectTarget(null),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              _InlineSelectionChip(
                chipKey: TestKeys.searchScopeContactsChip,
                label: SearchObjectTarget.contacts.label,
                isSelected:
                    selection.activeObjectTarget == SearchObjectTarget.contacts,
                backgroundColor: mutedSurface,
                textColor: fgSecondary,
                selectedBackgroundColor: selectionBackground,
                selectedTextColor: selectionForeground,
                selectedBorderColor: selectionBorder,
                onTap: () => _selectObjectTarget(SearchObjectTarget.contacts),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              _InlineSelectionChip(
                chipKey: TestKeys.searchScopeDirectChatChip,
                label: SearchObjectTarget.directChats.label,
                isSelected:
                    selection.activeObjectTarget ==
                    SearchObjectTarget.directChats,
                backgroundColor: mutedSurface,
                textColor: fgSecondary,
                selectedBackgroundColor: selectionBackground,
                selectedTextColor: selectionForeground,
                selectedBorderColor: selectionBorder,
                onTap: () =>
                    _selectObjectTarget(SearchObjectTarget.directChats),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              _InlineSelectionChip(
                chipKey: TestKeys.searchScopeGroupChatChip,
                label: SearchObjectTarget.groupChats.label,
                isSelected:
                    selection.activeObjectTarget ==
                    SearchObjectTarget.groupChats,
                backgroundColor: mutedSurface,
                textColor: fgSecondary,
                selectedBackgroundColor: selectionBackground,
                selectedTextColor: selectionForeground,
                selectedBorderColor: selectionBorder,
                onTap: () => _selectObjectTarget(SearchObjectTarget.groupChats),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              _InlineSelectionChip(
                chipKey: TestKeys.searchScopeCirclesChip,
                label: SearchObjectTarget.circles.label,
                isSelected:
                    selection.activeObjectTarget == SearchObjectTarget.circles,
                backgroundColor: mutedSurface,
                textColor: fgSecondary,
                selectedBackgroundColor: selectionBackground,
                selectedTextColor: selectionForeground,
                selectedBorderColor: selectionBorder,
                onTap: () => _selectObjectTarget(SearchObjectTarget.circles),
              ),
            ],
          ),
        ),
      ],
    );
  }

  String _buildContentSelectionSummary(SearchObjectSelection selection) {
    if (selection.isAllContent) {
      return '全部内容';
    }
    final labels = SearchContentTypeFilter.values
        .where(selection.isContentTypeEnabled)
        .map((item) => item.label)
        .toList(growable: false);
    if (labels.length <= 2) {
      return labels.join(' · ');
    }
    return '${labels[0]} · ${labels[1]} +${labels.length - 2}';
  }

  Future<void> _openContentTypeSelector() async {
    final nextSelection = await showCupertinoModalPopup<SearchObjectSelection>(
      context: context,
      barrierColor: AppColors.black.withValues(alpha: 0),
      builder: (_) => _SearchContentTypeSheet(
        initialSelection: _coordinator.state.selection.normalized(),
      ),
    );
    if (nextSelection != null) {
      _coordinator.updateSelection(nextSelection);
    }
  }

  void _selectObjectTarget(SearchObjectTarget? target) {
    final current = _coordinator.state.selection.normalized();
    _coordinator.updateSelection(
      SearchObjectSelection(
        targets: target == null
            ? const <SearchObjectTarget>{}
            : <SearchObjectTarget>{target},
        contentTypes: current.contentTypes,
      ),
    );
  }

  bool _allowsNetworkResults(SearchObjectSelection selection) {
    return selection.normalized().enabledContentTypes.isNotEmpty;
  }

  Widget _buildHistoryView({
    required Key key,
    required SearchSessionState state,
    required Color fgSecondary,
    required Color fgTertiary,
    required bool isDark,
    required bool manageMode,
  }) {
    if (state.isHydratingHistory && state.recentSearches.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state.recentSearches.isEmpty) {
      return SizedBox(key: key);
    }

    final visibleEntries = manageMode || state.isHistoryExpanded
        ? state.recentSearches
        : state.recentSearches
              .take(_collapsedHistoryCount)
              .toList(growable: false);
    final separatorColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final showExpand =
        !manageMode && state.recentSearches.length > _collapsedHistoryCount;

    return ListView(
      key: key,
      padding: EdgeInsets.only(
        top: AppSpacing.containerXs,
        bottom: AppSpacing.containerMd,
      ),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Text(
              '最近在搜',
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                fontWeight: AppTypography.medium,
                color: fgTertiary,
              ),
            ),
            const Spacer(),
            if (showExpand)
              CupertinoButton(
                key: TestKeys.searchHistoryExpandButton,
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: _coordinator.toggleHistoryExpanded,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      state.isHistoryExpanded ? '收起' : '展开',
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        color: fgSecondary,
                      ),
                    ),
                    SizedBox(width: AppSpacing.intraGroupXs / 2),
                    Icon(
                      state.isHistoryExpanded
                          ? CupertinoIcons.chevron_up
                          : CupertinoIcons.chevron_down,
                      color: fgTertiary,
                      size: AppSpacing.iconSmall,
                    ),
                  ],
                ),
              ),
            if (showExpand) ...[
              SizedBox(width: AppSpacing.containerSm),
              _HeaderActionDivider(color: separatorColor),
            ],
            if (!manageMode) ...[
              SizedBox(width: AppSpacing.containerSm),
              CupertinoButton(
                key: TestKeys.searchHistoryManageButton,
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: _coordinator.startManagingHistory,
                child: Icon(
                  CupertinoIcons.delete,
                  color: fgTertiary,
                  size: AppSpacing.iconMedium,
                ),
              ),
            ] else ...[
              CupertinoButton(
                key: TestKeys.searchHistoryClearButton,
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: () => unawaited(_confirmClearHistory()),
                child: Text(
                  '清空',
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    color: fgSecondary,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              _HeaderActionDivider(color: separatorColor),
              SizedBox(width: AppSpacing.containerSm),
              _ManageDoneButton(onTap: _coordinator.finishManagingHistory),
            ],
          ],
        ),
        SizedBox(height: AppSpacing.containerMd),
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: visibleEntries.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisExtent: manageMode
                ? AppSpacing.buttonHeightMd + AppSpacing.containerSm
                : AppSpacing.buttonHeightMd,
            crossAxisSpacing: AppSpacing.intraGroupSm,
            mainAxisSpacing: AppSpacing.intraGroupSm,
          ),
          itemBuilder: (context, index) {
            final entry = visibleEntries[index];
            return _HistoryChip(
              entry: entry,
              manageMode: manageMode,
              isDark: isDark,
              onTap: manageMode
                  ? null
                  : () => unawaited(_coordinator.useRecentSearch(entry)),
              onRemove: manageMode
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
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      itemCount: state.suggestionSections.length,
      itemBuilder: (context, index) {
        final section = state.suggestionSections[index];
        return Padding(
          padding: EdgeInsets.only(
            bottom: index == state.suggestionSections.length - 1
                ? 0
                : AppSpacing.containerLg,
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
        Text(
          section.title,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.semiBold,
            color: fgPrimary,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        DecoratedBox(
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
                if (i != section.visibleItems.length - 1 ||
                    section.showsMoreEntry)
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
                      case SearchSuggestionSectionKind.mostUsed:
                      case SearchSuggestionSectionKind.circles:
                      case SearchSuggestionSectionKind.network:
                        return;
                    }
                  },
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSuggestionItem({
    required SearchSuggestionEntry item,
    required String query,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    switch (item.kind) {
      case SearchSuggestionEntryKind.mostUsed:
        final mostUsed = item.cast<MostUsedSearchItem>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: mostUsed.avatarUrl,
            avatarCompositeUrls: mostUsed.avatarCompositeUrls,
            isDark: isDark,
            fallbackIcon: switch (mostUsed.targetKind) {
              MostUsedTargetKind.contact => CupertinoIcons.person_fill,
              MostUsedTargetKind.chatRecord =>
                CupertinoIcons.chat_bubble_2_fill,
              MostUsedTargetKind.circle => CupertinoIcons.person_3_fill,
            },
          ),
          title: _highlightedText(
            mostUsed.title,
            query,
            TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.medium,
              color: fgPrimary,
            ),
          ),
          subtitle: _highlightedText(
            mostUsed.subtitle,
            query,
            TextStyle(fontSize: AppTypography.iosFootnote, color: fgSecondary),
            maxLines: 2,
          ),
          trailing: Text(
            switch (mostUsed.targetKind) {
              MostUsedTargetKind.contact => '联系人',
              MostUsedTargetKind.chatRecord =>
                mostUsed.conversationType?.trim().toLowerCase() == 'group'
                    ? '群聊'
                    : '单聊',
              MostUsedTargetKind.circle => '圈子',
            },
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openMostUsedItem(mostUsed),
        );
      case SearchSuggestionEntryKind.contact:
        final contact = item.cast<ContactSearchSuggestion>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: contact.avatarUrl,
            avatarCompositeUrls: const <String>[],
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_fill,
          ),
          title: _highlightedText(
            contact.displayName,
            query,
            TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.medium,
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
            avatarCompositeUrls: const <String>[],
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_3_fill,
          ),
          title: _highlightedText(
            circle.name,
            query,
            TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.medium,
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
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.medium,
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

  void _openMostUsedItem(MostUsedSearchItem item) {
    switch (item.targetKind) {
      case MostUsedTargetKind.contact:
      case MostUsedTargetKind.chatRecord:
        if (item.conversationId == null) {
          return;
        }
        _openConversation(
          item.conversationId!,
          messageAnchorId: item.messageAnchorId,
        );
      case MostUsedTargetKind.circle:
        if (item.circleId == null) {
          return;
        }
        _openCircle(item.circleId!);
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
              sourceQuery: _coordinator.state.query.trim(),
            ),
    );
  }

  void _openCircle(String circleId) {
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(AppRoutePaths.circleDetail(id: circleId));
  }

  void _openNetworkResults(String query, {String? initialTabId}) {
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return;
    }
    final selection = _coordinator.state.selection.normalized();
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
        initialScope: _coordinator.state.scope,
        initialFacet: selection.toFacet(),
        searchObjectSelection: selection,
        restoreState: false,
      ),
    );
  }

  String _defaultNetworkTabIdForSelection(SearchObjectSelection selection) {
    return 'xiaoqu';
  }

  void _handleSearchSubmitted(String value) {
    final trimmedValue = value.trim();
    _coordinator.updateQuery(trimmedValue, immediate: true);
    if (trimmedValue.isEmpty) {
      return;
    }
    if (!_allowsNetworkResults(_coordinator.state.selection)) {
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
          title: const Text('清空最近搜索'),
          content: const Padding(
            padding: EdgeInsets.only(top: AppSpacing.containerXs),
            child: Text('将移除全部最近搜索记录，且无法恢复。'),
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

class _HeaderActionDivider extends StatelessWidget {
  const _HeaderActionDivider({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.one,
      height: AppSpacing.buttonHeightMd - AppSpacing.intraGroupXs,
      child: DecoratedBox(decoration: BoxDecoration(color: color)),
    );
  }
}

class _ManageDoneButton extends StatelessWidget {
  const _ManageDoneButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      key: TestKeys.searchHistoryDoneButton,
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Text(
        '完成',
        style: TextStyle(
          fontSize: AppTypography.iosBody,
          fontWeight: AppTypography.medium,
          color: AppColors.primaryColor,
        ),
      ),
    );
  }
}

class _InlineSelectionChip extends StatelessWidget {
  const _InlineSelectionChip({
    required this.chipKey,
    required this.label,
    required this.isSelected,
    required this.backgroundColor,
    required this.textColor,
    required this.selectedBackgroundColor,
    required this.selectedTextColor,
    required this.selectedBorderColor,
    required this.onTap,
  });

  final Key chipKey;
  final String label;
  final bool isSelected;
  final Color backgroundColor;
  final Color textColor;
  final Color selectedBackgroundColor;
  final Color selectedTextColor;
  final Color selectedBorderColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      key: chipKey,
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: isSelected ? selectedBackgroundColor : backgroundColor,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: isSelected
                ? selectedBorderColor
                : AppColors.black.withValues(alpha: 0),
            width: AppSpacing.hairline,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.medium,
              color: isSelected ? selectedTextColor : textColor,
            ),
          ),
        ),
      ),
    );
  }
}

class _SearchContentTypeSheet extends StatefulWidget {
  const _SearchContentTypeSheet({required this.initialSelection});

  final SearchObjectSelection initialSelection;

  @override
  State<_SearchContentTypeSheet> createState() =>
      _SearchContentTypeSheetState();
}

class _SearchContentTypeSheetState extends State<_SearchContentTypeSheet> {
  late Set<SearchContentTypeFilter> _enabledTypes;

  @override
  void initState() {
    super.initState();
    _enabledTypes = widget.initialSelection.enabledContentTypes.toSet();
  }

  void _toggleType(SearchContentTypeFilter type, bool enabled) {
    setState(() {
      if (enabled) {
        _enabledTypes.add(type);
      } else {
        _enabledTypes.remove(type);
      }
    });
  }

  void _reset() {
    setState(() {
      _enabledTypes = SearchContentTypeFilter.values.toSet();
    });
  }

  void _complete() {
    final normalizedTypes =
        _enabledTypes.isEmpty ||
            _enabledTypes.length == SearchContentTypeFilter.values.length
        ? const <SearchContentTypeFilter>{}
        : _enabledTypes;
    Navigator.of(context).pop(
      SearchObjectSelection(
        targets: widget.initialSelection.normalizedTargets,
        contentTypes: normalizedTypes,
      ),
    );
  }

  Key _toggleKeyForType(SearchContentTypeFilter type) {
    switch (type) {
      case SearchContentTypeFilter.article:
        return TestKeys.searchContentArticleToggle;
      case SearchContentTypeFilter.image:
        return TestKeys.searchContentImageToggle;
      case SearchContentTypeFilter.video:
        return TestKeys.searchContentVideoToggle;
      case SearchContentTypeFilter.moment:
        return TestKeys.searchContentMomentToggle;
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final pageBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final primaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final divider = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final cardBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );

    return AppBottomModalSurface(
      panelKey: TestKeys.searchContentSheet,
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: pageBackground,
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        0,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '搜索指定内容',
                  style: TextStyle(
                    fontSize: AppTypography.iosTitle3,
                    fontWeight: AppTypography.semiBold,
                    color: primaryText,
                  ),
                ),
              ),
              CupertinoButton(
                key: TestKeys.searchContentSheetResetButton,
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: _reset,
                child: Text(
                  '恢复默认',
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    color: secondaryText,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              CupertinoButton(
                key: TestKeys.searchContentSheetDoneButton,
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: _complete,
                child: Text(
                  '完成',
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    fontWeight: AppTypography.medium,
                    color: AppColors.primaryColor,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.containerMd),
          DecoratedBox(
            decoration: BoxDecoration(
              color: cardBackground,
              borderRadius: BorderRadius.circular(
                AppSpacing.contentPreviewCornerRadius,
              ),
            ),
            child: Column(
              children: [
                for (
                  var index = 0;
                  index < SearchContentTypeFilter.values.length;
                  index++
                ) ...[
                  _ContentToggleRow(
                    label: SearchContentTypeFilter.values[index].label,
                    value: _enabledTypes.contains(
                      SearchContentTypeFilter.values[index],
                    ),
                    toggleKey: _toggleKeyForType(
                      SearchContentTypeFilter.values[index],
                    ),
                    onChanged: (value) => _toggleType(
                      SearchContentTypeFilter.values[index],
                      value,
                    ),
                  ),
                  if (index != SearchContentTypeFilter.values.length - 1)
                    Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerSm,
                      ),
                      child: SizedBox(
                        height: AppSpacing.one,
                        child: DecoratedBox(
                          decoration: BoxDecoration(color: divider),
                        ),
                      ),
                    ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ContentToggleRow extends StatelessWidget {
  const _ContentToggleRow({
    required this.label,
    required this.value,
    required this.toggleKey,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final Key toggleKey;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final primaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, AppSpacing.toolbarMinTouchHeight),
      onPressed: () => onChanged(!value),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.containerSm,
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: primaryText,
                ),
              ),
            ),
            IgnorePointer(
              ignoring: true,
              child: CupertinoSwitch(
                key: toggleKey,
                value: value,
                onChanged: (_) {},
                activeTrackColor: AppColors.primaryColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HistoryChip extends StatelessWidget {
  const _HistoryChip({
    required this.entry,
    required this.manageMode,
    required this.isDark,
    this.onTap,
    this.onRemove,
  });

  final RecentSearchEntryView entry;
  final bool manageMode;
  final bool isDark;
  final VoidCallback? onTap;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final fgTertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );
    final background = manageMode
        ? AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted)
        : AppColors.black.withValues(alpha: 0);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(
          horizontal: manageMode ? AppSpacing.containerSm : 0,
          vertical: AppSpacing.intraGroupSm,
        ),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          children: [
            Icon(
              CupertinoIcons.clock,
              size: AppSpacing.iconSmall,
              color: fgTertiary,
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Expanded(
              child: Text(
                entry.query,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: fgSecondary,
                ),
              ),
            ),
            if (manageMode && onRemove != null) ...[
              SizedBox(width: AppSpacing.intraGroupXs),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onRemove,
                child: SizedBox.square(
                  dimension: AppSpacing.buttonHeightMd,
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
          _buildConversationLeading(
            avatarUrl: suggestion.avatarUrl,
            avatarCompositeUrls: suggestion.avatarCompositeUrls,
            isDark: isDark,
            fallbackIcon: suggestion.conversationType == 'group'
                ? CupertinoIcons.person_2_fill
                : CupertinoIcons.chat_bubble_2_fill,
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
                          fontSize: AppTypography.iosBody,
                          fontWeight: AppTypography.medium,
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
  required List<String> avatarCompositeUrls,
  required bool isDark,
  required IconData fallbackIcon,
}) {
  if (avatarCompositeUrls.isNotEmpty) {
    return SizedBox(
      width: AppSpacing.avatarUserMd,
      height: AppSpacing.avatarUserMd,
      child: GroupAvatarGrid(
        size: AppSpacing.avatarUserMd,
        avatarUrls: avatarCompositeUrls,
      ),
    );
  }
  final effectiveImageUrl = (avatarUrl ?? '').trim();
  return ClipRRect(
    borderRadius: BorderRadius.circular(AppSpacing.avatarUserMd / 2),
    child: Container(
      width: AppSpacing.avatarUserMd,
      height: AppSpacing.avatarUserMd,
      color: AppColorsFunctional.getColor(
        isDark,
        ColorType.backgroundSecondary,
      ),
      child: effectiveImageUrl.isEmpty
          ? Icon(
              fallbackIcon,
              size: AppSpacing.iconMedium,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            )
          : Image.network(
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
