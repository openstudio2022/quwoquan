// 对话态设置 UI：贴底半屏、保留上层上下文（与全屏 `settings_form/` 区分）。
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';

/// Post 更多操作弹窗入口（对话态）。
abstract final class MoreActionPopup {
  static Future<void> show({
    required BuildContext context,
    required MediaPostMoreActionConfig config,
    double? panelMaxWidth,
  }) {
    return showAppBottomModal<void>(
      context: context,
      builder: (context) => _MediaPostMoreActionSheet(
        config: config,
        panelMaxWidth: panelMaxWidth,
      ),
    );
  }
}

/// 滚动行操作项
class _ScrollAction {
  final String id;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _ScrollAction({
    required this.id,
    required this.icon,
    required this.label,
    required this.onTap,
  });
}

/// 底部操作项
class _BottomAction {
  final String id;
  final IconData icon;
  final String label;
  final String? description;
  final VoidCallback? onTap;
  final bool isDestructive;

  const _BottomAction({
    required this.id,
    required this.icon,
    required this.label,
    this.description,
    this.onTap,
    this.isDestructive = false,
  });
}

/// 媒体帖子更多操作底部弹窗
class _MediaPostMoreActionSheet extends ConsumerStatefulWidget {
  final MediaPostMoreActionConfig config;
  final double? panelMaxWidth;

  const _MediaPostMoreActionSheet({required this.config, this.panelMaxWidth});

  @override
  ConsumerState<_MediaPostMoreActionSheet> createState() =>
      _MediaPostMoreActionSheetState();
}

class _MediaPostMoreActionSheetState
    extends ConsumerState<_MediaPostMoreActionSheet> {
  static const String _contentFilterActionId = 'contentFilter';
  static const String _readingSettingsActionId = 'readingSettings';
  bool _showContentFilterPanel = false;
  bool _showReadingSettingsPanel = false;
  late Set<String> _selectedFilterIds;
  late String _selectedReadingOptionId;

  @override
  void initState() {
    super.initState();
    _selectedFilterIds = widget.config.selectedFilterIds.isEmpty
        ? <String>{'all'}
        : widget.config.selectedFilterIds.toSet();
    _selectedReadingOptionId =
        widget.config.selectedReadingOptionId ??
        (widget.config.readingOptions.isEmpty
            ? 'system'
            : widget.config.readingOptions.first.id);
  }

  List<_ScrollAction> _buildScrollActions(bool isDark) {
    final actions = <_ScrollAction>[
      if (widget.config.onCopyLink != null)
        _ScrollAction(
          id: 'copyLink',
          icon: CupertinoIcons.link,
          label: FoundationText.copyLink,
          onTap: widget.config.onCopyLink!,
        ),
      if (widget.config.showShareAction && widget.config.onShare != null)
        _ScrollAction(
          id: 'share',
          icon: CupertinoIcons.share,
          label: FoundationText.share,
          onTap: widget.config.onShare!,
        ),
      if (widget.config.showViewOriginalAction &&
          widget.config.onViewOriginal != null)
        _ScrollAction(
          id: 'viewOriginal',
          icon: CupertinoIcons.photo,
          label: ContentText.viewOriginal,
          onTap: widget.config.onViewOriginal!,
        ),
      _ScrollAction(
        id: 'themeMode',
        icon: isDark ? CupertinoIcons.sun_max : CupertinoIcons.moon,
        label: isDark ? ContentText.lightMode : ContentText.darkMode,
        onTap: widget.config.onThemeToggle ?? _toggleTheme,
      ),
    ];
    return actions;
  }

  List<_BottomAction> _buildBottomActions() {
    final actions = <_BottomAction>[
      if (widget.config.filterOptions.isNotEmpty)
        _BottomAction(
          id: _contentFilterActionId,
          icon: CupertinoIcons.line_horizontal_3_decrease,
          label: ContentText.contentFilterTitle,
          description: _contentFilterSummaryFor(
            options: widget.config.filterOptions,
            selectedIds: _selectedFilterIds,
          ),
        ),
      if (widget.config.readingOptions.isNotEmpty)
        _BottomAction(
          id: _readingSettingsActionId,
          icon: CupertinoIcons.book,
          label: ContentText.readingSettingsTitle,
          description: _readingSettingSummaryFor(
            options: widget.config.readingOptions,
            selectedId: _selectedReadingOptionId,
          ),
        ),
      if (widget.config.onNotInterested != null)
        _BottomAction(
          id: 'notInterested',
          icon: CupertinoIcons.eye_slash,
          label: ContentText.notInterested,
          description: ContentText.notInterestedDescription,
          onTap: widget.config.onNotInterested,
        ),
      if (widget.config.onBlockUser != null)
        _BottomAction(
          id: 'blockUser',
          icon: CupertinoIcons.person_badge_minus,
          label: ContentText.blockAuthor,
          description: ContentText.blockAuthorDescription,
          onTap: widget.config.onBlockUser,
        ),
      if (widget.config.onBlockWords != null)
        _BottomAction(
          id: 'blockWords',
          icon: CupertinoIcons.slider_horizontal_3,
          label: ContentText.blockKeywords,
          description: ContentText.blockKeywordsDescription,
          onTap: widget.config.onBlockWords,
        ),
      if (widget.config.onReport != null)
        _BottomAction(
          id: 'report',
          icon: CupertinoIcons.flag,
          label: ContentText.report,
          description: ContentText.reportDescription,
          onTap: widget.config.onReport,
        ),
    ];
    if (widget.config.showDeleteAction && widget.config.onDelete != null) {
      actions.add(
        _BottomAction(
          id: 'delete',
          icon: CupertinoIcons.delete,
          label: ChatText.messageActionDelete,
          onTap: widget.config.onDelete,
          isDestructive: true,
        ),
      );
    }
    return actions;
  }

  static String _readingSettingSummaryFor({
    required List<MoreActionReadingOption> options,
    required String selectedId,
  }) {
    for (final option in options) {
      if (option.id == selectedId) return option.label;
    }
    return options.isEmpty ? '' : options.first.label;
  }

  static String _contentFilterSummaryFor({
    required List<MoreActionFilterOption> options,
    required Set<String> selectedIds,
  }) {
    if (options.isEmpty || selectedIds.isEmpty) {
      return ContentText.allWorks;
    }
    final selected = options
        .where((option) => selectedIds.contains(option.id))
        .toList(growable: false);
    if (selected.isEmpty ||
        selected.any((option) => option.id == 'all') ||
        selected.length == options.length - 1) {
      return ContentText.allWorks;
    }
    return selected.map((option) => option.label).join(' / ');
  }

  void _toggleFilterOption(String id) {
    setState(() {
      if (id == 'all') {
        _selectedFilterIds = <String>{'all'};
        return;
      }
      _selectedFilterIds.remove('all');
      if (_selectedFilterIds.contains(id)) {
        _selectedFilterIds.remove(id);
      } else {
        _selectedFilterIds.add(id);
      }
      if (_selectedFilterIds.isEmpty) {
        _selectedFilterIds = <String>{'all'};
      }
      final nonAllIds = widget.config.filterOptions
          .where((option) => option.id != 'all')
          .map((option) => option.id)
          .toSet();
      if (_selectedFilterIds.containsAll(nonAllIds)) {
        _selectedFilterIds = <String>{'all'};
      }
    });
  }

  void _commitFilterSelection() {
    widget.config.onFilterSelectionChanged?.call(_selectedFilterIds);
    setState(() => _showContentFilterPanel = false);
  }

  void _commitReadingOption(String id) {
    setState(() => _selectedReadingOptionId = id);
    widget.config.onReadingOptionChanged?.call(id);
    Navigator.pop(context);
  }

  void _toggleTheme() {
    Future<void>.delayed(const Duration(milliseconds: 80), () {
      ref.read(themeProvider.notifier).toggleTheme();
    });
  }

  void _handleScrollActionTap(_ScrollAction action) {
    widget.config.onActionInvoked?.call(action.id);
    Navigator.pop(context);
    action.onTap();
  }

  void _handleBottomActionTap(_BottomAction action) {
    widget.config.onActionInvoked?.call(action.id);
    if (action.id == _contentFilterActionId) {
      setState(() {
        _showContentFilterPanel = true;
        _showReadingSettingsPanel = false;
      });
      return;
    }
    if (action.id == _readingSettingsActionId) {
      setState(() {
        _showReadingSettingsPanel = true;
        _showContentFilterPanel = false;
      });
      return;
    }
    Navigator.pop(context);
    action.onTap?.call();
  }

  @override
  Widget build(BuildContext context) {
    final resolvedIsDark = widget.config.forceDarkAppearance
        ? true
        : ref.watch(isDarkProvider);
    final scrollActions = _buildScrollActions(resolvedIsDark);
    final bottomActions = _buildBottomActions();
    final panelBackground =
        SettingsSemanticConstants.conversationSheetPanelBackground(
          resolvedIsDark,
        );
    final iconSurface = AppColorsFunctional.getColor(
      resolvedIsDark,
      ColorType.surfaceMuted,
    );
    final iconBorder = AppColorsFunctional.getColor(
      resolvedIsDark,
      ColorType.separatorSubtle,
    ).withValues(alpha: resolvedIsDark ? 0.72 : 0.9);
    final primaryText = AppColorsFunctional.getColor(
      resolvedIsDark,
      ColorType.foregroundPrimary,
    );
    final secondaryText = AppColorsFunctional.getColor(
      resolvedIsDark,
      ColorType.foregroundSecondary,
    );

    return CupertinoTheme(
      data: CupertinoTheme.of(context).copyWith(
        brightness: resolvedIsDark ? Brightness.dark : Brightness.light,
      ),
      child: AppBottomModalSurface(
        onDismiss: () => Navigator.pop(context),
        backgroundColor: panelBackground,
        panelKey: TestKeys.modalBottomSheetPanel,
        panelMaxWidth: widget.panelMaxWidth,
        contentPadding: EdgeInsets.fromLTRB(
          SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
          0,
          SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
          SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        ),
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ConversationSheetHeader(
                isDark: resolvedIsDark,
                title: ContentText.moreActionsTitle,
              ),
              if (_showContentFilterPanel) ...[
                _InlineContentFilterSection(
                  options: widget.config.filterOptions,
                  selectedIds: _selectedFilterIds,
                  onToggle: _toggleFilterOption,
                  onBack: () => setState(() => _showContentFilterPanel = false),
                  onDone: _commitFilterSelection,
                ),
                SizedBox(
                  height: SettingsSemanticConstants.conversationSheetSectionGap,
                ),
              ] else if (_showReadingSettingsPanel) ...[
                _InlineReadingSettingsSection(
                  options: widget.config.readingOptions,
                  selectedId: _selectedReadingOptionId,
                  onSelect: _commitReadingOption,
                ),
                SizedBox(
                  height: SettingsSemanticConstants.conversationSheetSectionGap,
                ),
              ] else ...[
                if (scrollActions.isNotEmpty) ...[
                  _MoreActionQuickSection(
                    isDark: resolvedIsDark,
                    actions: scrollActions,
                    iconSurface: iconSurface,
                    iconBorder: iconBorder,
                    primaryText: primaryText,
                    secondaryText: secondaryText,
                    onTap: _handleScrollActionTap,
                  ),
                  SizedBox(
                    height:
                        SettingsSemanticConstants.conversationSheetSectionGap,
                  ),
                ],
                if (bottomActions.isNotEmpty) ...[
                  _MoreActionListSection(
                    isDark: resolvedIsDark,
                    actions: bottomActions,
                    onTap: _handleBottomActionTap,
                  ),
                  SizedBox(
                    height:
                        SettingsSemanticConstants.conversationSheetSectionGap,
                  ),
                ],
              ],
              ConversationSheetCancelBar(
                isDark: resolvedIsDark,
                label: (_showContentFilterPanel || _showReadingSettingsPanel)
                    ? ContentText.back
                    : FoundationText.cancel,
                onTap: () {
                  if (_showContentFilterPanel || _showReadingSettingsPanel) {
                    setState(() {
                      _showContentFilterPanel = false;
                      _showReadingSettingsPanel = false;
                    });
                    return;
                  }
                  Navigator.pop(context);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MoreActionQuickSection extends StatelessWidget {
  const _MoreActionQuickSection({
    required this.isDark,
    required this.actions,
    required this.iconSurface,
    required this.iconBorder,
    required this.primaryText,
    required this.secondaryText,
    required this.onTap,
  });

  final bool isDark;
  final List<_ScrollAction> actions;
  final Color iconSurface;
  final Color iconBorder;
  final Color primaryText;
  final Color secondaryText;
  final ValueChanged<_ScrollAction> onTap;

  @override
  Widget build(BuildContext context) {
    return ConversationSheetListCard(
      isDark: isDark,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.containerXs),
        child: SizedBox(
          height: AppSpacing.avatarRailHeight + AppSpacing.containerSm,
          child: SingleChildScrollView(
            key: TestKeys.modalBottomSheetQuickActionsRail,
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            child: Row(
              children: [
                for (var index = 0; index < actions.length; index++) ...[
                  if (index > 0) SizedBox(width: AppSpacing.intraGroupXs),
                  SizedBox(
                    width: AppSpacing.avatarUserLg + AppSpacing.twenty,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => onTap(actions[index]),
                      child: Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: AppSpacing.avatarUserLg,
                              height: AppSpacing.avatarUserLg,
                              decoration: BoxDecoration(
                                color: iconSurface,
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: iconBorder,
                                  width: AppSpacing.hairline,
                                ),
                              ),
                              child: Center(
                                child: Icon(
                                  actions[index].icon,
                                  size: AppSpacing.iconMedium,
                                  color: secondaryText,
                                ),
                              ),
                            ),
                            SizedBox(height: AppSpacing.intraGroupSm),
                            Text(
                              actions[index].label,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                color: primaryText,
                                fontWeight: AppTypography.medium,
                              ),
                              textAlign: TextAlign.center,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _InlineContentFilterSection extends StatelessWidget {
  const _InlineContentFilterSection({
    required this.options,
    required this.selectedIds,
    required this.onToggle,
    required this.onBack,
    required this.onDone,
  });

  final List<MoreActionFilterOption> options;
  final Set<String> selectedIds;
  final ValueChanged<String> onToggle;
  final VoidCallback onBack;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    const isDark = true;
    return Column(
      key: const ValueKey<String>('more-action-content-filter-panel'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const ConversationSheetHeader(
          isDark: isDark,
          title: ContentText.contentFilterTitle,
        ),
        ConversationSheetListCard(
          isDark: isDark,
          child: Column(
            children: options.asMap().entries.map((entry) {
              final index = entry.key;
              final option = entry.value;
              final selected = option.id == 'all'
                  ? selectedIds.isEmpty || selectedIds.contains('all')
                  : selectedIds.contains(option.id);
              return Column(
                children: [
                  ConversationSheetSingleSelectRow(
                    key: ValueKey<String>(
                      'more-action-content-filter-${option.id}',
                    ),
                    isDark: isDark,
                    label: option.label,
                    icon: option.id == 'all'
                        ? CupertinoIcons.line_horizontal_3_decrease
                        : null,
                    isSelected: selected,
                    onTap: () => onToggle(option.id),
                  ),
                  if (index < options.length - 1)
                    ConversationSheetDivider(
                      isDark: isDark,
                      dividerLeftInset:
                          ConversationSheetSingleSelectRow.dividerInsetForIcon(
                            option.id == 'all',
                          ),
                    ),
                ],
              );
            }).toList(),
          ),
        ),
        SizedBox(height: SettingsSemanticConstants.conversationSheetSectionGap),
        ConversationSheetCancelBar(
          isDark: isDark,
          label: CommunityText.done,
          onTap: onDone,
        ),
      ],
    );
  }
}

class _InlineReadingSettingsSection extends StatelessWidget {
  const _InlineReadingSettingsSection({
    required this.options,
    required this.selectedId,
    required this.onSelect,
  });

  final List<MoreActionReadingOption> options;
  final String selectedId;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    const isDark = true;
    return Column(
      key: const ValueKey<String>('more-action-reading-settings-panel'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const ConversationSheetHeader(
          isDark: isDark,
          title: ContentText.readingSettingsTitle,
        ),
        ConversationSheetListCard(
          isDark: isDark,
          child: Column(
            children: options
                .asMap()
                .entries
                .map((entry) {
                  final index = entry.key;
                  final option = entry.value;
                  return Column(
                    children: [
                      ConversationSheetSingleSelectRow(
                        key: ValueKey<String>(
                          'more-action-reading-theme-${option.id}',
                        ),
                        isDark: isDark,
                        label: option.label,
                        icon: option.id == 'system'
                            ? CupertinoIcons.sparkles
                            : null,
                        isSelected: selectedId == option.id,
                        onTap: () => onSelect(option.id),
                      ),
                      if (index < options.length - 1)
                        ConversationSheetDivider(
                          isDark: isDark,
                          dividerLeftInset:
                              ConversationSheetSingleSelectRow.dividerInsetForIcon(
                                option.id == 'system',
                              ),
                        ),
                    ],
                  );
                })
                .toList(growable: false),
          ),
        ),
      ],
    );
  }
}

class _MoreActionListSection extends StatelessWidget {
  const _MoreActionListSection({
    required this.isDark,
    required this.actions,
    required this.onTap,
  });

  final bool isDark;
  final List<_BottomAction> actions;
  final ValueChanged<_BottomAction> onTap;

  @override
  Widget build(BuildContext context) {
    return ConversationSheetListCard(
      isDark: isDark,
      child: Column(
        children: actions.asMap().entries.map((entry) {
          final index = entry.key;
          final action = entry.value;
          return Column(
            children: [
              ConversationSheetActionRow(
                isDark: isDark,
                icon: action.icon,
                label: action.label,
                description: action.description,
                isDestructive: action.isDestructive,
                onTap: () => onTap(action),
              ),
              if (index < actions.length - 1)
                ConversationSheetDivider(
                  isDark: isDark,
                  dividerLeftInset:
                      ConversationSheetActionRow.dividerLeftInsetDefault,
                ),
            ],
          );
        }).toList(),
      ),
    );
  }
}
