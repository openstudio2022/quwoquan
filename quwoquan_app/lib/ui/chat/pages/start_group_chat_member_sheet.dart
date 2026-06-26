part of 'start_group_chat_page.dart';

/// 群成员/圈成员多选 sheet（图三）
class _MemberSelectSheet extends ConsumerStatefulWidget {
  const _MemberSelectSheet({
    required this.title,
    required this.members,
    required this.wizardId,
    required this.onBack,
  });

  final String title;
  final List<StartGroupPickableMember> members;
  final String wizardId;
  final VoidCallback onBack;

  @override
  ConsumerState<_MemberSelectSheet> createState() => _MemberSelectSheetState();
}

class _MemberSelectSheetState extends ConsumerState<_MemberSelectSheet> {
  final TextEditingController _searchController = TextEditingController();
  String _query = '';

  String _memberId(StartGroupPickableMember member) {
    final userId = member.userId.trim();
    if (userId.isNotEmpty) {
      return userId;
    }
    return member.displayName.trim();
  }

  bool _allSelected(StartGroupMemberWizardState state) {
    final selectableIds = widget.members
        .map(_memberId)
        .where((id) => id.isNotEmpty && !state.isLocked(id))
        .toList(growable: false);
    if (selectableIds.isEmpty) {
      return false;
    }
    return selectableIds.every((id) => state.selectedMembers.containsKey(id));
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _toggleMember(StartGroupPickableMember member) {
    ref
        .read(startGroupMemberWizardProvider(widget.wizardId).notifier)
        .toggleMember(member);
  }

  void _toggleAll(StartGroupMemberWizardState state) {
    final selectableMembers = widget.members
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
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final toolbarBg =
        SettingsSemanticConstants.memberPickerNavigationBarBackground(isDark);
    final listHorizontalPadding =
        SettingsSemanticConstants.insetFormListHorizontalPadding;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final filtered = widget.members
        .where((member) {
          final query = _query.trim().toLowerCase();
          if (query.isEmpty) {
            return true;
          }
          final name = member.displayName.toLowerCase();
          final userId = _memberId(member).toLowerCase();
          return name.contains(query) || userId.contains(query);
        })
        .toList(growable: false);
    final allSelected = _allSelected(wizardState);
    final hasSelectableMembers = widget.members.any((member) {
      final id = _memberId(member);
      return id.isNotEmpty && !wizardState.isLocked(id);
    });
    final selectedCount = wizardState.selectedMembers.length;

    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: widget.title,
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
            child: filtered.isEmpty
                ? Center(
                    child: Text(
                      UITextConstants.startGroupChatNoMatchedMembers,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        color: fgSecondary,
                      ),
                    ),
                  )
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      listHorizontalPadding,
                      0,
                      listHorizontalPadding,
                      listHorizontalPadding,
                    ),
                    children: [
                      _SelectionCard(
                        isDark: isDark,
                        child: Column(
                          children: [
                            for (
                              var index = 0;
                              index < filtered.length;
                              index++
                            ) ...[
                              Builder(
                                builder: (context) {
                                  final member = filtered[index];
                                  final memberId = _memberId(member);
                                  final selected = wizardState.isSelected(
                                    memberId,
                                  );
                                  final locked = wizardState.isLocked(memberId);
                                  return CupertinoButton(
                                    padding: EdgeInsets.zero,
                                    onPressed: locked
                                        ? null
                                        : () => _toggleMember(member),
                                    child: ConstrainedBox(
                                      constraints: BoxConstraints(
                                        minHeight: SettingsSemanticConstants
                                            .selectionRowMinHeight,
                                      ),
                                      child: Padding(
                                        padding: EdgeInsets.symmetric(
                                          horizontal: SettingsSemanticConstants
                                              .blockHorizontalPadding,
                                          vertical: AppSpacing.sm,
                                        ),
                                        child: Row(
                                          children: [
                                            _SelectionIndicator(
                                              selected: selected,
                                              onTap: locked
                                                  ? null
                                                  : () => _toggleMember(member),
                                              enabled: !locked,
                                            ),
                                            RoundedSquareAvatar(
                                              size: AppSpacing.avatarSize,
                                              imageUrl: member.avatarUrl,
                                              name: member.displayName,
                                              fallbackIcon:
                                                  CupertinoIcons.person_fill,
                                            ),
                                            SizedBox(width: AppSpacing.sm),
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    member.displayName,
                                                    style: TextStyle(
                                                      fontSize:
                                                          AppTypography.lg,
                                                      color: locked
                                                          ? fgSecondary
                                                          : fgPrimary,
                                                    ),
                                                  ),
                                                  if (locked)
                                                    Text(
                                                      UITextConstants
                                                          .startGroupChatAlreadyInGroup,
                                                      style: TextStyle(
                                                        fontSize:
                                                            AppTypography.sm,
                                                        color: fgSecondary,
                                                      ),
                                                    ),
                                                ],
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  );
                                },
                              ),
                              if (index < filtered.length - 1)
                                _SelectionListDivider(
                                  isDark: isDark,
                                  leadingInset:
                                      AppSpacing.minInteractiveSize +
                                      AppSpacing.avatarSize +
                                      AppSpacing.sm,
                                ),
                            ],
                          ],
                        ),
                      ),
                    ],
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
                        UITextConstants.selectAll,
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
                      : () => Navigator.of(context).pop(),
                  minimumSize: Size(
                    SettingsSemanticConstants.actionButtonHeightMedium,
                    SettingsSemanticConstants.actionButtonHeightMedium,
                  ),
                  child: Text(
                    '${UITextConstants.selectAction}（$selectedCount）',
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
}
