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
  final ScrollController _scrollController = ScrollController();
  final Set<String> _seenCursors = <String>{};
  List<StartGroupPickableMember> _members = const <StartGroupPickableMember>[];
  String? _nextCursor;
  String _query = '';
  bool _loading = true;
  bool _loadingMore = false;
  UiErrorSemantic? _errorSemantic;
  UiErrorSemantic? _appendErrorSemantic;
  int _requestVersion = 0;

  bool get _hasMore => (_nextCursor ?? '').trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_maybeLoadMore);
    // post-frame 触发首帧加载，避免在 build/initState 期间 setState。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(_reloadMembers());
      }
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    setState(() => _query = value);
    unawaited(_reloadMembers());
  }

  void _maybeLoadMore() {
    if (!_scrollController.hasClients ||
        _scrollController.position.extentAfter > AppSpacing.xl) {
      return;
    }
    unawaited(_loadMoreMembers());
  }

  Future<void> _reloadMembers() async {
    final requestVersion = ++_requestVersion;
    final query = _query.trim();
    _seenCursors.clear();
    setState(() {
      _members = const <StartGroupPickableMember>[];
      _nextCursor = null;
      _loading = true;
      _loadingMore = false;
      _errorSemantic = null;
      _appendErrorSemantic = null;
    });
    try {
      final wizard = ref.read(startGroupMemberWizardProvider(widget.wizardId));
      final page = await loadGroupContactMemberPage(
        ref.read(chatGroupSelectionRepositoryProvider),
        group: widget.group,
        lockedMemberIds: wizard.lockedMemberIds,
        query: query.isEmpty ? null : query,
      );
      if (!mounted || requestVersion != _requestVersion) {
        return;
      }
      setState(() {
        _members = page.members;
        _nextCursor = _acceptNextCursor(page.nextCursor);
        _loading = false;
      });
    } catch (error) {
      if (!mounted || requestVersion != _requestVersion) {
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

  Future<void> _loadMoreMembers() async {
    final cursor = _nextCursor;
    if (_loading || _loadingMore || cursor == null || cursor.trim().isEmpty) {
      return;
    }
    final requestVersion = _requestVersion;
    final query = _query.trim();
    setState(() {
      _loadingMore = true;
      _appendErrorSemantic = null;
    });
    try {
      final wizard = ref.read(startGroupMemberWizardProvider(widget.wizardId));
      final page = await loadGroupContactMemberPage(
        ref.read(chatGroupSelectionRepositoryProvider),
        group: widget.group,
        lockedMemberIds: wizard.lockedMemberIds,
        query: query.isEmpty ? null : query,
        cursor: cursor,
      );
      if (!mounted || requestVersion != _requestVersion) {
        return;
      }
      setState(() {
        _members = mergeStartGroupContactMemberPages(_members, page.members);
        _nextCursor = _acceptNextCursor(page.nextCursor);
        _loadingMore = false;
      });
    } catch (error) {
      if (!mounted || requestVersion != _requestVersion) {
        return;
      }
      setState(() {
        _loadingMore = false;
        _appendErrorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.listAppend,
          scope: UiErrorScope.section,
        );
      });
    }
  }

  String? _acceptNextCursor(String? candidate) {
    final normalized = candidate?.trim() ?? '';
    return normalized.isEmpty || !_seenCursors.add(normalized)
        ? null
        : normalized;
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
              placeholder: DiscoveryText.search,
              onChanged: _onSearchChanged,
            ),
          ),
          Expanded(
            child: _buildBody(
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
              rowBackground: rowBackground,
              rowDividerColor: rowDividerColor,
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
    required StartGroupMemberWizardState wizardState,
  }) {
    if (_loading) {
      return AppRequestFeedback.section();
    }
    if (_errorSemantic != null) {
      return AppPageErrorState(
        semantic: _errorSemantic!,
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _reloadMembers();
            return _errorSemantic == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    if (_members.isEmpty) {
      return Center(
        child: Text(
          ChatText.startGroupChatNoMatchedMembers,
          style: TextStyle(fontSize: AppTypography.base, color: fgSecondary),
        ),
      );
    }
    return ListView(
      controller: _scrollController,
      padding: EdgeInsets.only(bottom: AppSpacing.lg),
      children: [
        for (var index = 0; index < _members.length; index++) ...[
          Builder(
            builder: (context) {
              final member = _members[index];
              final personaId = _memberId(member);
              final userHandle = member.userHandle.trim();
              final selected = wizardState.isSelected(personaId);
              final locked = wizardState.isLocked(personaId);
              return _RelatedFriendRow(
                name: member.displayName,
                memberKey: personaId,
                avatarUrl: member.avatarUrl,
                selected: selected,
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
                locked: locked,
                rowBackground: rowBackground,
                dividerColor: rowDividerColor,
                onTap: locked ? null : () => _toggleMember(member),
                onAvatarTap: userHandle.isEmpty
                    ? null
                    : () => context.push(
                        AppRoutePaths.userProfile(userHandle: userHandle),
                        extra: UserProfileRouteExtra(
                          personaId: personaId,
                          avatarUrl: member.avatarUrl.isNotEmpty
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
        if (_loadingMore)
          Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: AppRequestFeedback.section(),
          )
        else if (_appendErrorSemantic != null)
          AppListAppendErrorFooter(
            semantic: _appendErrorSemantic!,
            onAction: (_) async => _loadMoreMembers(),
          )
        else if (_hasMore)
          Center(
            child: CupertinoButton(
              key: const ValueKey<String>(
                'start-group-member-picker-load-more',
              ),
              onPressed: () => unawaited(_loadMoreMembers()),
              child: const Text(ContentText.loadMore),
            ),
          ),
      ],
    );
  }
}
