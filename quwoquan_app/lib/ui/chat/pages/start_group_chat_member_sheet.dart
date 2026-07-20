part of 'start_group_chat_page.dart';

/// 图五：从某个群聊中选择与当前用户 mutual 的联系人（群成员 ∩ 联系人）。
///
/// 选中项通过同一 [wizardId] 实时并入发起群聊向导；点击「选择(N)」pop 回主页，
/// 主页选中横向条自动滚到尾部并展示。行样式与联系人列表 / 主候选列表同源
/// （复用 [_RelatedFriendRow]，去卡片、全宽、头像 52、`iosBody`）。
class _MemberSelectSheet extends ConsumerStatefulWidget {
  const _MemberSelectSheet({
    super.key,
    required this.group,
    required this.wizardId,
    required this.isDark,
    required this.onBack,
  });

  final GroupWithFriendCount group;
  final String wizardId;
  final bool isDark;
  final VoidCallback onBack;

  @override
  ConsumerState<_MemberSelectSheet> createState() => _MemberSelectSheetState();
}

class _MemberSelectSheetState extends ConsumerState<_MemberSelectSheet> {
  final TextEditingController _searchController = TextEditingController();
  List<StartGroupPickableMember> _members = const <StartGroupPickableMember>[];
  bool _loading = true;
  String _query = '';
  UiErrorSemantic? _errorSemantic;

  @override
  void initState() {
    super.initState();
    // post-frame 触发首帧加载，避免在 build/initState 期间 setState。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _loadMembers();
      }
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadMembers() async {
    if (!mounted) {
      return;
    }
    setState(() {
      _loading = true;
      _errorSemantic = null;
    });
    try {
      final wizard = ref.read(startGroupMemberWizardProvider(widget.wizardId));
      final members = await loadGroupContactMembers(
        ref.read(chatGroupSelectionRepositoryProvider),
        widget.group,
        wizard.lockedMemberIds,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _members = members;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
      });
    }
  }

  String _memberId(StartGroupPickableMember member) {
    final userId = member.userId.trim();
    if (userId.isNotEmpty) {
      return userId;
    }
    return member.displayName.trim();
  }

  bool _allSelected(StartGroupMemberWizardState state) {
    final selectableIds = _members
        .map(_memberId)
        .where((id) => id.isNotEmpty && !state.isLocked(id))
        .toList(growable: false);
    if (selectableIds.isEmpty) {
      return false;
    }
    return selectableIds.every((id) => state.selectedMembers.containsKey(id));
  }

  void _toggleMember(StartGroupPickableMember member) {
    ref
        .read(startGroupMemberWizardProvider(widget.wizardId).notifier)
        .toggleMember(member);
  }

  void _toggleAll(StartGroupMemberWizardState state) {
    final selectableMembers = _members
        .where((member) {
          final id = _memberId(member);
          return id.isNotEmpty && !state.isLocked(id);
        })
        .toList(growable: false);
    if (selectableMembers.isEmpty) {
      return;
    }
    final notifier = ref.read(
      startGroupMemberWizardProvider(widget.wizardId).notifier,
    );
    final allSelected = selectableMembers.every(
      (member) => state.selectedMembers.containsKey(_memberId(member)),
    );
    if (allSelected) {
      notifier.deselectMemberIds(selectableMembers.map(_memberId));
      return;
    }
    notifier.selectMembers(selectableMembers);
  }

  @override
  Widget build(BuildContext context) {
    final wizardState = ref.watch(
      startGroupMemberWizardProvider(widget.wizardId),
    );
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
    final toolbarBg =
        SettingsSemanticConstants.memberPickerNavigationBarBackground(isDark);
    final listHorizontalPadding =
        SettingsSemanticConstants.insetFormListHorizontalPadding;
    final normalizedQuery = _query.trim().toLowerCase();
    final filtered = _members
        .where((member) {
          if (normalizedQuery.isEmpty) {
            return true;
          }
          return pinyinMatches(member.displayName, normalizedQuery) ||
              _memberId(member).toLowerCase().contains(normalizedQuery);
        })
        .toList(growable: false);
    final allSelected = _allSelected(wizardState);
    final hasSelectableMembers = _members.any((member) {
      final id = _memberId(member);
      return id.isNotEmpty && !wizardState.isLocked(id);
    });
    final selectedCount = wizardState.selectedMembers.length;
    final title = ChatText.startGroupChatGroupMemberTitle(
      widget.group.title,
      widget.group.friendCount,
    );

    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: title,
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
              placeholder: UITextConstants.search,
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          Expanded(
            child: _buildBody(
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
              rowBackground: rowBackground,
              rowDividerColor: rowDividerColor,
              filtered: filtered,
              wizardState: wizardState,
            ),
          ),
          Container(
            padding: EdgeInsets.fromLTRB(
              listHorizontalPadding,
              AppSpacing.sm,
              listHorizontalPadding,
              AppSpacing.sm + MediaQuery.paddingOf(context).bottom,
            ),
            decoration: BoxDecoration(
              color: toolbarBg,
              border: Border(
                top: BorderSide(
                  color:
                      SettingsSemanticConstants.insetFormNavigationBarBorderColor(
                        isDark,
                      ),
                  width: AppSpacing.hairline,
                ),
              ),
            ),
            child: Row(
              children: [
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: hasSelectableMembers
                      ? () => _toggleAll(wizardState)
                      : null,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _SelectionIndicator(
                        selected: allSelected,
                        onTap: hasSelectableMembers
                            ? () => _toggleAll(wizardState)
                            : null,
                        enabled: hasSelectableMembers,
                      ),
                      Text(
                        ChatText.selectAll,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          color: hasSelectableMembers ? fgPrimary : fgSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                CupertinoButton(
                  padding: EdgeInsets.symmetric(
                    horizontal:
                        SettingsSemanticConstants.actionButtonPaddingHorizontal,
                    vertical:
                        SettingsSemanticConstants.actionButtonPaddingVertical,
                  ),
                  color:
                      SettingsSemanticConstants.actionButtonPrimaryBackground,
                  disabledColor:
                      SettingsSemanticConstants.actionButtonDisabledBackground(
                        isDark,
                      ),
                  borderRadius: BorderRadius.circular(
                    SettingsSemanticConstants.actionButtonBorderRadius,
                  ),
                  onPressed: selectedCount == 0
                      ? null
                      : () => Navigator.of(context).pop(true),
                  minimumSize: Size(
                    SettingsSemanticConstants.actionButtonHeightMedium,
                    SettingsSemanticConstants.actionButtonHeightMedium,
                  ),
                  child: Text(
                    '${ChatText.selectAction}（$selectedCount）',
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      fontWeight: FontWeight.w500,
                      color: selectedCount == 0
                          ? SettingsSemanticConstants.actionButtonDisabledForeground(
                              isDark,
                            )
                          : SettingsSemanticConstants
                                .actionButtonPrimaryForeground,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody({
    required Color fgPrimary,
    required Color fgSecondary,
    required Color rowBackground,
    required Color rowDividerColor,
    required List<StartGroupPickableMember> filtered,
    required StartGroupMemberWizardState wizardState,
  }) {
    if (_loading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_errorSemantic != null) {
      return AppPageErrorState(
        semantic: _errorSemantic!,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadMembers();
          }
        },
      );
    }
    if (filtered.isEmpty) {
      return Center(
        child: Text(
          ChatText.startGroupChatNoMatchedMembers,
          style: TextStyle(fontSize: AppTypography.base, color: fgSecondary),
        ),
      );
    }
    return ListView(
      padding: EdgeInsets.only(bottom: AppSpacing.lg),
      children: [
        for (var index = 0; index < filtered.length; index++) ...[
          Builder(
            builder: (context) {
              final member = filtered[index];
              final memberId = _memberId(member);
              final selected = wizardState.isSelected(memberId);
              final locked = wizardState.isLocked(memberId);
              return _RelatedFriendRow(
                name: member.displayName,
                username: memberId,
                avatarUrl: member.avatarUrl,
                selected: selected,
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
                locked: locked,
                rowBackground: rowBackground,
                dividerColor: rowDividerColor,
                onTap: locked ? null : () => _toggleMember(member),
                onAvatarTap: () => context.push(
                  AppRoutePaths.userProfile(username: memberId),
                  extra: UserProfileRouteExtra(
                    subAccountId: memberId,
                    avatar: member.avatarUrl.isNotEmpty
                        ? member.avatarUrl
                        : null,
                    displayName: member.displayName.isNotEmpty
                        ? member.displayName
                        : null,
                  ),
                ),
              );
            },
          ),
        ],
      ],
    );
  }
}
