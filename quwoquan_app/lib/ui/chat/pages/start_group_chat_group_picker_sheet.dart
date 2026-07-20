part of 'start_group_chat_page.dart';

/// 图四：从群聊 / 圈子中选择联系人（按名称首字母分区）。
///
/// 数据由服务端 `source=group|circle` 在分页前区分来源，并统一计算会话成员与
/// mutual 联系人的交集。点击来源后进入图五 [_MemberSelectSheet] 选具体成员，
/// 选中项通过同一 wizardId 并入向导。
class _GroupPickerSheet extends ConsumerStatefulWidget {
  const _GroupPickerSheet({
    super.key,
    required this.wizardId,
    required this.isDark,
    required this.source,
    required this.onBack,
  });

  final String wizardId;
  final bool isDark;
  final StartGroupSource source;
  final VoidCallback onBack;

  @override
  ConsumerState<_GroupPickerSheet> createState() => _GroupPickerSheetState();
}

class _GroupPickerSheetState extends ConsumerState<_GroupPickerSheet> {
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final Map<String, GlobalKey> _sectionKeys = <String, GlobalKey>{};
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  ({List<String> keys, Map<String, List<GroupWithFriendCount>> map})
  _groupByLetter(List<GroupWithFriendCount> groups) {
    final map = <String, List<GroupWithFriendCount>>{};
    for (final g in groups) {
      final key = chatContactInitial(g.title);
      map.putIfAbsent(key, () => []).add(g);
    }
    for (final key in map.keys) {
      map[key]!.sort((a, b) => a.title.compareTo(b.title));
    }
    final keys = map.keys.toList()..sort();
    if (keys.contains('#')) {
      keys.remove('#');
      keys.add('#');
    }
    return (keys: keys, map: map);
  }

  Future<void> _openGroup(GroupWithFriendCount group) async {
    final navigator = Navigator.of(context);
    // 图五「选择(N)」pop(true) → 这里再 pop 图四，直接回到发起群聊主页；
    // 图五左返回 pop(null) → 仅关闭图五，停留在图四以便重新选群。
    final completed = await navigator.push<bool>(
      CupertinoPageRoute<bool>(
        builder: (sheetContext) => _MemberSelectSheet(
          key: const ValueKey<String>('start-group-member-select-sheet'),
          group: group,
          wizardId: widget.wizardId,
          isDark: widget.isDark,
          onBack: () => Navigator.of(sheetContext).pop(),
        ),
      ),
    );
    if (completed == true && mounted) {
      navigator.pop(true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isCircleSource = widget.source == StartGroupSource.circle;
    final isDark = widget.isDark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final rowBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final rowDividerColor =
        SettingsSemanticConstants.conversationSheetDividerColor(
          isDark,
        ).withValues(alpha: 0.9);
    final sectionBandColor =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);
    final listHorizontalPadding =
        SettingsSemanticConstants.insetFormListHorizontalPadding;

    final sourceProvider = isCircleSource
        ? startGroupFromCircleProvider
        : startGroupFromGroupProvider;
    final asyncGroups = ref.watch(sourceProvider);
    final normalizedQuery = _query.trim().toLowerCase();

    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: isCircleSource
          ? ChatText.startGroupChatCirclePickerTitle
          : ChatText.startGroupChatGroupPickerTitle,
      onBack: widget.onBack,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              listHorizontalPadding,
              AppSpacing.sm,
              listHorizontalPadding,
              AppSpacing.sm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: isCircleSource
                  ? ChatText.startGroupChatPickFromCircleSearch
                  : ChatText.startGroupChatPickFromGroupSearch,
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          Expanded(
            child: asyncGroups.when(
              loading: () => const Center(child: CupertinoActivityIndicator()),
              error: (error, _) => AppPageErrorState(
                semantic: runtimeErrorSemantic(
                  context,
                  error: error,
                  category: UiErrorCategory.pageLoad,
                  scope: UiErrorScope.page,
                ),
                onAction: (action) async {
                  if (action.type == UiErrorActionType.retry ||
                      action.type == UiErrorActionType.resubmit) {
                    ref.invalidate(sourceProvider);
                  }
                },
              ),
              data: (allGroups) {
                final filtered = normalizedQuery.isEmpty
                    ? allGroups
                    : allGroups
                          .where((g) => pinyinMatches(g.title, normalizedQuery))
                          .toList(growable: false);
                if (filtered.isEmpty) {
                  return Center(
                    child: Text(
                      isCircleSource
                          ? ChatText.startGroupChatCirclePickerEmpty
                          : ChatText.startGroupChatGroupPickerEmpty,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        color: fgSecondary,
                      ),
                    ),
                  );
                }
                final grouped = _groupByLetter(filtered);
                final indexLetters = <String>['↑', ...grouped.keys];
                _sectionKeys
                  ..clear()
                  ..addAll({for (final k in grouped.keys) k: GlobalKey()});
                final listChildren = <Widget>[
                  for (final letter in grouped.keys) ...[
                    _ContactListSectionBand(
                      key: _sectionKeys[letter],
                      title: letter,
                      color: fgSecondary,
                      bandColor: sectionBandColor,
                    ),
                    for (final group in grouped.map[letter]!)
                      _GroupPickerRow(
                        group: group,
                        rowBackground: rowBackground,
                        dividerColor: rowDividerColor,
                        fgPrimary: fgPrimary,
                        fgSecondary: fgSecondary,
                        onTap: () => _openGroup(group),
                      ),
                  ],
                  SizedBox(height: AppSpacing.xl),
                ];
                return Stack(
                  children: [
                    ListView(
                      controller: _scrollController,
                      padding: EdgeInsets.only(bottom: AppSpacing.lg),
                      children: listChildren,
                    ),
                    if (normalizedQuery.isEmpty)
                      Positioned(
                        right: 4,
                        top: 0,
                        bottom: 0,
                        child: _LetterIndex(
                          letters: indexLetters,
                          onTap: (i) {
                            if (i == 0) {
                              _scrollController.animateTo(
                                0,
                                duration: const Duration(milliseconds: 300),
                                curve: Curves.easeOut,
                              );
                              return;
                            }
                            final letter = indexLetters[i];
                            final key = _sectionKeys[letter];
                            if (key?.currentContext != null) {
                              Scrollable.ensureVisible(
                                key!.currentContext!,
                                duration: const Duration(milliseconds: 300),
                                curve: Curves.easeOut,
                                alignment: 0,
                              );
                            }
                          },
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// 图四群聊列表行：群头像 + 群名 + (N个朋友) + 右 chevron。
class _GroupPickerRow extends StatelessWidget {
  const _GroupPickerRow({
    required this.group,
    required this.rowBackground,
    required this.dividerColor,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.onTap,
  });

  final GroupWithFriendCount group;
  final Color rowBackground;
  final Color dividerColor;
  final Color fgPrimary;
  final Color fgSecondary;
  final VoidCallback onTap;

  static const double _avatarSize = ChatConversationAvatarTokens.listSize;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        key: ValueKey<String>('start-group-picker-row-${group.conversationId}'),
        color: rowBackground,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  RoundedSquareAvatar(
                    size: _avatarSize,
                    imageUrl: group.avatarUrl,
                    name: group.title,
                    fallbackIcon: CupertinoIcons.group,
                  ),
                  SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                  Expanded(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Flexible(
                          child: Text(
                            group.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosBody,
                              fontWeight: AppTypography.regular,
                              color: fgPrimary,
                              height: AppTypography.lineHeightTight,
                            ),
                          ),
                        ),
                        SizedBox(width: AppSpacing.xs),
                        Text(
                          '（${ChatText.startGroupChatFriendsCount(group.friendCount)}）',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    CupertinoIcons.chevron_forward,
                    size: AppSpacing.iconSmall,
                    color: fgPrimary.withValues(alpha: 0.4),
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: ChatConversationAvatarTokens.dividerInset(_avatarSize),
              ),
              child: Divider(
                key: ValueKey<String>(
                  'start-group-picker-divider-${group.conversationId}',
                ),
                height: AppSpacing.one,
                thickness: AppSpacing.hairline,
                color: dividerColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
