import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/ui/chat/models/start_group_pickable_member.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/start_group_member_wizard_provider.dart';
import 'package:quwoquan_app/ui/chat/services/start_group_chat_wire.dart';
import 'package:quwoquan_app/ui/chat/widgets/chat_conversation_avatar_tokens.dart';

// settings-canonical-exception: 多步发起群聊向导，完整 Inset 化见后续 slice owner:chat CR-20260329-003

/// 发起群聊页（图一：创建新群聊 + 相关同好）
class StartGroupChatPage extends ConsumerStatefulWidget {
  const StartGroupChatPage({
    super.key,
    this.conversationId,
    required this.onBack,
  });

  final String? conversationId;
  final VoidCallback onBack;

  bool get isCreateMode => conversationId == null || conversationId!.isEmpty;

  @override
  ConsumerState<StartGroupChatPage> createState() => _StartGroupChatPageState();
}

class _StartGroupChatPageState extends ConsumerState<StartGroupChatPage> {
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _listScrollController = ScrollController();
  late final String _wizardId;

  List<ChatInboxDto> _groupInboxRows = [];
  List<ChatContactRowDto> _contacts = [];
  List<CircleDto> _circles = [];
  bool _selectedExpanded = false;
  bool _submitting = false;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _wizardId =
        '${widget.conversationId ?? 'create'}_${DateTime.now().microsecondsSinceEpoch}';
    Future<void>.microtask(() {
      if (!mounted) {
        return;
      }
      final wizard = ref.read(
        startGroupMemberWizardProvider(_wizardId).notifier,
      );
      if (widget.isCreateMode) {
        wizard.completeBootstrap(const <String>{});
      } else {
        wizard.setBootstrapLoading();
      }
    });
    _loadData();
  }

  Future<void> _loadData() async {
    try {
      final chatRepo = ref.read(chatRepositoryProvider);
      final userRepo = ref.read(userProfileRepositoryProvider);
      final currentUserId = ref.read(currentUserIdProvider);
      final inbox = await chatRepo.listInbox(limit: 50);
      final contacts = await chatRepo.listContacts(limit: 200);
      final circleSummaries = await userRepo.listUserCircles(
        currentUserId,
        limit: 50,
      );
      final List<ChatConversationMemberDto> existingMembers =
          !widget.isCreateMode && widget.conversationId != null
          ? await chatRepo.listMembers(
              conversationId: widget.conversationId!,
              limit: 500,
            )
          : const <ChatConversationMemberDto>[];
      final lockedMemberIds = existingMembers
          .map((member) => member.userId)
          .where((id) => id.isNotEmpty)
          .toSet();
      if (mounted) {
        ref
            .read(startGroupMemberWizardProvider(_wizardId).notifier)
            .completeBootstrap(lockedMemberIds);
        setState(() {
          final convId = widget.conversationId ?? '';
          _groupInboxRows = inbox
              .where(
                (row) =>
                    row.type == 'group' &&
                    row.id.isNotEmpty &&
                    row.id != convId,
              )
              .toList(growable: false);
          _contacts = contacts;
          final activeCircleIds = inbox
              .where((row) => row.circleId.isNotEmpty)
              .map((row) => row.circleId)
              .toSet();
          _circles = circleSummaries
              .where((circle) => activeCircleIds.contains(circle.id))
              .toList(growable: false);
        });
      }
    } catch (_) {
      if (mounted && !widget.isCreateMode) {
        ref
            .read(startGroupMemberWizardProvider(_wizardId).notifier)
            .completeBootstrap(const <String>{});
      }
      // Fallback: leave empty lists
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    _listScrollController.dispose();
    super.dispose();
  }

  Set<String> get _mutualContactIds {
    return _contacts
        .map((contact) => contact.userId)
        .where((id) => id.isNotEmpty)
        .toSet();
  }

  bool get _selectionBootstrapReady {
    if (widget.isCreateMode) {
      return true;
    }
    return ref
        .read(startGroupMemberWizardProvider(_wizardId))
        .isBootstrapLoaded;
  }

  void _handleCreateConversationSuccess(String conversationId) {
    AppToast.show(context, '群聊已创建');
    if (conversationId.isEmpty) {
      context.go(AppRoutePaths.chat);
    } else {
      context.go(AppRoutePaths.chatDetail(id: conversationId));
    }
  }

  void _handleAddMembersSuccess(int count) {
    AppToast.show(context, '已添加 $count 位同好');
    context.pop();
  }

  void _handleSubmitSelectionError() {
    AppToast.show(
      context,
      widget.isCreateMode ? '发起群聊失败，请稍后重试' : '添加成员失败，请稍后重试',
    );
  }

  void _showEmptySelectableMembersToast(String message) {
    AppToast.show(context, message);
  }

  Future<void> _refreshChatEntryLists() async {
    await ref.read(chatInboxListProvider.notifier).refresh();
    ref.invalidate(
      chatContactsRowsForSubTabProvider(UITextConstants.contactsTabFunGroup),
    );
  }

  void _toggleSelectedMember(StartGroupPickableMember member) {
    if (!_selectionBootstrapReady) {
      return;
    }
    ref
        .read(startGroupMemberWizardProvider(_wizardId).notifier)
        .toggleMember(member);
  }

  Future<void> _submitSelection() async {
    final wizardState = ref.read(startGroupMemberWizardProvider(_wizardId));
    if (_submitting || wizardState.selectedMembers.isEmpty) {
      return;
    }
    final selectedIds = wizardState.selectedMembers.keys.toList(
      growable: false,
    );
    if (widget.isCreateMode && selectedIds.length >= 500) {
      AppToast.show(context, '群成员数量超过上限');
      return;
    }
    setState(() => _submitting = true);
    try {
      final repo = ref.read(chatRepositoryProvider);
      if (widget.isCreateMode) {
        final ChatConversationCreatedDto created = await repo
            .createConversation(
              type: 'group',
              title: wizardState.selectedMembers.values
                  .map((member) => member.displayName)
                  .where((name) => name.isNotEmpty)
                  .take(3)
                  .join('、'),
              maxGroupSize: 500,
              initialMemberIds: selectedIds,
            );
        final conversationId = created.conversationId;
        if (!context.mounted) {
          return;
        }
        await _refreshChatEntryLists();
        if (!context.mounted) {
          return;
        }
        _handleCreateConversationSuccess(conversationId);
      } else {
        await repo.addMembers(
          conversationId: widget.conversationId!,
          userIds: selectedIds,
        );
        await _refreshChatEntryLists();
        if (!context.mounted) {
          return;
        }
        _handleAddMembersSuccess(selectedIds.length);
      }
    } catch (_) {
      if (!context.mounted) {
        return;
      }
      _handleSubmitSelectionError();
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  void _openSelectGroupChatSheet() {
    if (!_selectionBootstrapReady) {
      _showEmptySelectableMembersToast('正在同步群成员状态，请稍后再试');
      return;
    }
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (context) => _SelectGroupChatSheet(
        groups: _groupInboxRows,
        onSelectGroup: (group) async {
          Navigator.of(context).pop();
          final members = await ref
              .read(chatRepositoryProvider)
              .listMembers(conversationId: group.id, limit: 500);
          final selectableMembers = selectableFromChatMembers(
            members,
            mutualContactIds: _mutualContactIds,
            mutualOnly: true,
          );
          if (!context.mounted) {
            return;
          }
          if (selectableMembers.isEmpty) {
            _showEmptySelectableMembersToast('该群暂无可添加的互关同好');
            return;
          }
          _openMemberSelectSheet(
            title: group.title,
            members: selectableMembers,
          );
        },
        onClose: () => Navigator.of(context).pop(),
      ),
    );
  }

  void _openSelectCircleSheet() {
    if (!_selectionBootstrapReady) {
      _showEmptySelectableMembersToast('正在同步群成员状态，请稍后再试');
      return;
    }
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (context) => _SelectCircleSheet(
        circles: _circles,
        onSelectCircle: (circle) async {
          Navigator.of(context).pop();
          final members = await ref
              .read(circleRepositoryProvider)
              .listMembers(circle.id, limit: 500);
          final selectableMembers = selectableFromCircleRosterItems(
            members,
            mutualContactIds: _mutualContactIds,
            mutualOnly: true,
          );
          if (!context.mounted) {
            return;
          }
          if (selectableMembers.isEmpty) {
            _showEmptySelectableMembersToast('该圈暂无可添加的互关同好');
            return;
          }
          _openMemberSelectSheet(
            title:
                '${circle.name} (${circle.memberCount}${UITextConstants.friendsCount})',
            members: selectableMembers,
          );
        },
        onClose: () => Navigator.of(context).pop(),
      ),
    );
  }

  void _openMemberSelectSheet({
    required String title,
    required List<StartGroupPickableMember> members,
  }) {
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (context) => _MemberSelectSheet(
        title: title,
        members: members,
        wizardId: _wizardId,
        onBack: () => Navigator.of(context).pop(),
      ),
    );
  }

  /// 按首字母分组：A-Z, #，返回有序 keys 与 map
  static ({List<String> keys, Map<String, List<StartGroupFriendLetterRow>> map})
  _groupByLetter(List<StartGroupFriendLetterRow> list) {
    final map = <String, List<StartGroupFriendLetterRow>>{};
    for (final m in list) {
      final name = m.displayName;
      final letter = m.letter.isNotEmpty
          ? m.letter
          : (name.isNotEmpty ? name.substring(0, 1).toUpperCase() : '#');
      final key = RegExp(r'[A-Za-z]').hasMatch(letter)
          ? letter.toUpperCase()
          : '#';
      map.putIfAbsent(key, () => []).add(m);
    }
    for (final key in map.keys) {
      map[key]!.sort((a, b) => a.displayName.compareTo(b.displayName));
    }
    final keys = map.keys.toList()..sort();
    if (keys.contains('#')) {
      keys.remove('#');
      keys.add('#');
    }
    return (keys: keys, map: map);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final wizardState = ref.watch(startGroupMemberWizardProvider(_wizardId));
    final selectionReady = widget.isCreateMode || wizardState.isBootstrapLoaded;
    final bgColor = SettingsSemanticConstants.pageBackground(isDark);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final dividerColor = SettingsSemanticConstants.dividerColor(isDark);
    final selectedMembers = wizardState.selectedMembers.values.toList(
      growable: false,
    );
    final visibleSelectedCount = _selectedExpanded
        ? selectedMembers.length
        : (selectedMembers.length > 12 ? 12 : selectedMembers.length);
    final friendsWithLetter = _contacts
        .where((contact) {
          final userId = contact.userId;
          if (userId.isEmpty) {
            return false;
          }
          final displayName = contact.displayName;
          final normalizedQuery = _query.trim().toLowerCase();
          if (normalizedQuery.isEmpty) {
            return true;
          }
          return displayName.toLowerCase().contains(normalizedQuery) ||
              userId.toLowerCase().contains(normalizedQuery);
        })
        .map((c) {
          final displayName = c.displayName;
          return StartGroupFriendLetterRow(
            displayName: displayName,
            userId: c.userId,
            avatarUrl: c.avatarUrl,
            letter: displayName.isNotEmpty
                ? displayName.substring(0, 1).toUpperCase()
                : '#',
          );
        })
        .toList();
    final grouped = _groupByLetter(friendsWithLetter);
    final indexLetters = ['↑', '☆', ...grouped.keys];

    final letterKeys = <String, GlobalKey>{};
    for (final k in grouped.keys) {
      letterKeys[k] = GlobalKey();
    }

    final topChildren = <Widget>[
      _SelectionCard(
        isDark: isDark,
        child: Column(
          children: [
            _SectionRow(
              label: UITextConstants.selectFriendsFromGroupChat,
              fgPrimary: fgPrimary,
              isDark: isDark,
              onTap: selectionReady ? _openSelectGroupChatSheet : null,
            ),
            _SelectionListDivider(isDark: isDark),
            _SectionRow(
              label: UITextConstants.selectFriendsFromCircle,
              fgPrimary: fgPrimary,
              isDark: isDark,
              onTap: selectionReady ? _openSelectCircleSheet : null,
            ),
          ],
        ),
      ),
      if (!selectionReady) ...[
        SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            const CupertinoActivityIndicator(),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                '正在同步群成员状态…',
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
            ),
          ],
        ),
      ],
      SizedBox(height: AppSpacing.md),
      _SelectionSectionLabel(
        title: UITextConstants.relatedSameInterest,
        color: fgSecondary,
      ),
      SizedBox(height: AppSpacing.xs),
    ];

    final relatedChildren = <Widget>[];
    for (final letter in grouped.keys) {
      final membersForLetter = grouped.map[letter]!;
      relatedChildren.add(
        Column(
          key: letterKeys[letter],
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _SelectionSectionLabel(title: letter, color: fgSecondary),
            SizedBox(height: AppSpacing.xs),
            _SelectionCard(
              isDark: isDark,
              child: Column(
                children: [
                  for (
                    var index = 0;
                    index < membersForLetter.length;
                    index++
                  ) ...[
                    Builder(
                      builder: (context) {
                        final m = membersForLetter[index];
                        final username = m.userId;
                        final selected = wizardState.isSelected(username);
                        final locked = wizardState.isLocked(username);
                        final pickable = StartGroupPickableMember(
                          userId: username,
                          displayName: m.displayName.isNotEmpty
                              ? m.displayName
                              : username,
                          avatarUrl: m.avatarUrl,
                        );
                        return _RelatedFriendRow(
                          name: m.displayName,
                          username: username,
                          avatarUrl: m.avatarUrl,
                          selected: selected,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          locked: locked,
                          onTap: selectionReady && !locked
                              ? () => _toggleSelectedMember(pickable)
                              : null,
                          onAvatarTap: () => context.push(
                            AppRoutePaths.userProfile(username: username),
                            extra: UserProfileRouteExtra(
                              subAccountId: username,
                              avatar: m.avatarUrl.isNotEmpty
                                  ? m.avatarUrl
                                  : null,
                              displayName: m.displayName.isNotEmpty
                                  ? m.displayName
                                  : null,
                            ),
                          ),
                          isDark: isDark,
                        );
                      },
                    ),
                    if (index < membersForLetter.length - 1)
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
            SizedBox(height: AppSpacing.sm),
          ],
        ),
      );
    }

    return AppScaffold(
      backgroundColor: bgColor,
      navigationBar: AppNavigationBar(
        backgroundColor: SettingsSemanticConstants.selectionToolbarBackground(
          isDark,
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
        middle: Text(
          widget.isCreateMode
              ? UITextConstants.startGroupChat
              : UITextConstants.addMember,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        border: Border(
          bottom: BorderSide(color: dividerColor, width: AppSpacing.hairline),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal:
                  AppSpacing.semantic[DesignSemanticConstants
                      .container]?[DesignSemanticConstants.md] ??
                  AppSpacing.containerMd,
              vertical: AppSpacing.sm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: UITextConstants.search,
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          if (selectedMembers.isNotEmpty)
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                0,
                AppSpacing.containerMd,
                AppSpacing.sm,
              ),
              child: _SelectionCard(
                isDark: isDark,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          '已选 ${selectedMembers.length} 人',
                          style: TextStyle(
                            fontSize: AppTypography.md,
                            fontWeight: FontWeight.w600,
                            color: fgPrimary,
                          ),
                        ),
                        const Spacer(),
                        if (selectedMembers.length > 12)
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            minimumSize: Size.zero,
                            onPressed: () => setState(
                              () => _selectedExpanded = !_selectedExpanded,
                            ),
                            child: Text(
                              _selectedExpanded
                                  ? UITextConstants.collapse
                                  : UITextConstants.moreMembers,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                color: AppColors.primaryColor,
                              ),
                            ),
                          ),
                      ],
                    ),
                    SizedBox(height: AppSpacing.sm),
                    Wrap(
                      spacing: AppSpacing.sm,
                      runSpacing: AppSpacing.sm,
                      children: List.generate(visibleSelectedCount, (index) {
                        final member = selectedMembers[index];
                        final userId = member.userId;
                        return _SelectedMemberAvatar(
                          name: member.displayName.isNotEmpty
                              ? member.displayName
                              : userId,
                          avatarUrl: member.avatarUrl,
                          isDark: isDark,
                          onRemove: () => ref
                              .read(
                                startGroupMemberWizardProvider(
                                  _wizardId,
                                ).notifier,
                              )
                              .deselectMemberIds(<String>[userId]),
                        );
                      }),
                    ),
                  ],
                ),
              ),
            ),
          Expanded(
            child: Stack(
              children: [
                ListView(
                  controller: _listScrollController,
                  padding: EdgeInsets.only(
                    left:
                        AppSpacing.semantic[DesignSemanticConstants
                            .container]?[DesignSemanticConstants.md] ??
                        AppSpacing.containerMd,
                    right:
                        (AppSpacing.semantic[DesignSemanticConstants
                                .container]?[DesignSemanticConstants.md] ??
                            AppSpacing.containerMd) +
                        28,
                    bottom: AppSpacing.lg,
                  ),
                  children: [...topChildren, ...relatedChildren],
                ),
                Positioned(
                  right: AppSpacing.sm,
                  top: 0,
                  bottom: 0,
                  child: _LetterIndex(
                    letters: indexLetters,
                    onTap: (i) {
                      if (i <= 1) {
                        _listScrollController.animateTo(
                          0,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOut,
                        );
                        return;
                      }
                      final letter = indexLetters[i];
                      final key = letterKeys[letter];
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
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.sm,
                AppSpacing.containerMd,
                AppSpacing.sm,
              ),
              child: CupertinoButton(
                padding: EdgeInsets.symmetric(
                  vertical:
                      SettingsSemanticConstants.actionButtonPaddingVertical,
                ),
                color: SettingsSemanticConstants.actionButtonPrimaryBackground,
                disabledColor:
                    SettingsSemanticConstants.actionButtonDisabledBackground(
                      isDark,
                    ),
                borderRadius: BorderRadius.circular(
                  SettingsSemanticConstants.actionButtonBorderRadius,
                ),
                onPressed: selectedMembers.isEmpty || _submitting
                    ? null
                    : _submitSelection,
                child: _submitting
                    ? const CupertinoActivityIndicator()
                    : Text(
                        widget.isCreateMode
                            ? '发起群聊（${selectedMembers.length}）'
                            : '${UITextConstants.addMember}（${selectedMembers.length}）',
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w600,
                          color: selectedMembers.isEmpty
                              ? SettingsSemanticConstants.actionButtonDisabledForeground(
                                  isDark,
                                )
                              : SettingsSemanticConstants
                                    .actionButtonPrimaryForeground,
                        ),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SelectedMemberAvatar extends StatelessWidget {
  const _SelectedMemberAvatar({
    required this.name,
    required this.avatarUrl,
    required this.onRemove,
    required this.isDark,
  });

  final String name;
  final String avatarUrl;
  final VoidCallback onRemove;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeMd,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              RoundedSquareAvatar(
                size: AppSpacing.largeButtonSize,
                imageUrl: avatarUrl,
                name: name,
                backgroundColor: SettingsSemanticConstants.blockBackground(
                  isDark,
                ),
              ),
              SizedBox(height: AppSpacing.xs),
              Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: AppTypography.sm),
              ),
            ],
          ),
          Positioned(
            right: -2,
            top: -2,
            child: GestureDetector(
              onTap: onRemove,
              child: Container(
                width: AppSpacing.eighteen,
                height: AppSpacing.eighteen,
                decoration: BoxDecoration(
                  color:
                      SettingsSemanticConstants.selectionAvatarAccessoryBackground(
                        isDark,
                      ),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color:
                        SettingsSemanticConstants.selectionAvatarAccessoryBorder(
                          isDark,
                        ),
                  ),
                ),
                child: Icon(
                  CupertinoIcons.clear,
                  size: AppSpacing.ten + AppSpacing.one,
                  color:
                      SettingsSemanticConstants.selectionAvatarAccessoryForeground(
                        isDark,
                      ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SelectionSectionLabel extends StatelessWidget {
  const _SelectionSectionLabel({required this.title, required this.color});

  final String title;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.xs,
        AppSpacing.xs,
        AppSpacing.xs,
        AppSpacing.xs,
      ),
      child: Text(
        title,
        style: TextStyle(
          fontSize: AppTypography.sm,
          fontWeight: AppTypography.semiBold,
          color: color,
        ),
      ),
    );
  }
}

class _SelectionCard extends StatelessWidget {
  const _SelectionCard({required this.isDark, required this.child});

  final bool isDark;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: SettingsSemanticConstants.blockBackground(isDark),
        borderRadius: BorderRadius.circular(
          SettingsSemanticConstants.selectionCardBorderRadius,
        ),
        border: Border.all(
          color: SettingsSemanticConstants.blockBorderColor(isDark),
        ),
      ),
      child: child,
    );
  }
}

class _SelectionListDivider extends StatelessWidget {
  const _SelectionListDivider({required this.isDark, this.leadingInset = 0});

  final bool isDark;
  final double leadingInset;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: SettingsSemanticConstants.dividerThickness,
      margin: EdgeInsets.only(
        left: SettingsSemanticConstants.blockHorizontalPadding + leadingInset,
        right: SettingsSemanticConstants.blockHorizontalPadding,
      ),
      color: SettingsSemanticConstants.dividerColor(isDark),
    );
  }
}

class _SectionRow extends StatelessWidget {
  const _SectionRow({
    required this.label,
    required this.fgPrimary,
    required this.isDark,
    required this.onTap,
  });

  final String label;
  final Color fgPrimary;
  final bool isDark;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: SettingsSemanticConstants.selectionRowMinHeight,
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: SettingsSemanticConstants.blockHorizontalPadding,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    color: onTap == null
                        ? SettingsSemanticConstants.secondaryColor(isDark)
                        : fgPrimary,
                  ),
                ),
              ),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconMedium,
                color: onTap == null
                    ? SettingsSemanticConstants.secondaryColor(isDark)
                    : SettingsSemanticConstants.selectionChevronColor(isDark),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RelatedFriendRow extends StatelessWidget {
  const _RelatedFriendRow({
    required this.name,
    required this.username,
    required this.avatarUrl,
    required this.selected,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.locked,
    required this.onTap,
    required this.onAvatarTap,
    required this.isDark,
  });

  final String name;
  final String username;
  final String avatarUrl;
  final bool selected;
  final Color fgPrimary;
  final Color fgSecondary;
  final bool locked;
  final VoidCallback? onTap;
  final VoidCallback onAvatarTap;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: SettingsSemanticConstants.selectionRowMinHeight,
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: SettingsSemanticConstants.blockHorizontalPadding,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              _SelectionIndicator(
                selected: selected,
                onTap: onTap,
                enabled: !locked && onTap != null,
              ),
              GestureDetector(
                onTap: onAvatarTap,
                child: RoundedSquareAvatar(
                  size: AppSpacing.avatarSize,
                  imageUrl: avatarUrl,
                  name: name,
                  backgroundColor: SettingsSemanticConstants.blockBackground(
                    isDark,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        color: locked ? fgSecondary : fgPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (locked)
                      Text(
                        '已在群中',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
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
  }
}

class _LetterIndex extends StatelessWidget {
  const _LetterIndex({required this.letters, required this.onTap});

  final List<String> letters;
  final void Function(int index) onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgSecondary = isDark
        ? AppColors.white.withValues(alpha: 0.45)
        : AppColors.black.withValues(alpha: 0.45);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(letters.length, (i) {
        return GestureDetector(
          onTap: () => onTap(i),
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
            child: Text(
              letters[i],
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: fgSecondary,
                fontWeight: FontWeight.normal,
              ),
            ),
          ),
        );
      }),
    );
  }
}

class _SelectionIndicator extends StatelessWidget {
  const _SelectionIndicator({
    required this.selected,
    required this.onTap,
    this.enabled = true,
  });

  final bool selected;
  final VoidCallback? onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: enabled ? onTap : null,
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      child: Icon(
        selected
            ? CupertinoIcons.check_mark_circled_solid
            : CupertinoIcons.circle,
        color: selected
            ? AppColors.primaryColor.withValues(alpha: enabled ? 1 : 0.6)
            : CupertinoColors.systemGrey2,
        size: AppSpacing.iconMedium,
      ),
    );
  }
}

/// 选择群聊页
class _SelectGroupChatSheet extends StatefulWidget {
  const _SelectGroupChatSheet({
    required this.groups,
    required this.onSelectGroup,
    required this.onClose,
  });

  final List<ChatInboxDto> groups;
  final void Function(ChatInboxDto group) onSelectGroup;
  final VoidCallback onClose;

  @override
  State<_SelectGroupChatSheet> createState() => _SelectGroupChatSheetState();
}

class _SelectGroupChatSheetState extends State<_SelectGroupChatSheet> {
  static const double _groupConversationAvatarSize =
      ChatConversationAvatarTokens.listSize;

  final TextEditingController _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  bool _matches(ChatInboxDto group) {
    final query = _query.trim().toLowerCase();
    if (query.isEmpty) {
      return true;
    }
    final name = group.title.toLowerCase();
    return name.contains(query);
  }

  Widget _buildLeading(ChatInboxDto group, bool isDark) {
    final url = group.avatarUrl.trim();
    if (url.isNotEmpty) {
      return RoundedSquareAvatar(
        size: _groupConversationAvatarSize,
        imageUrl: url,
        name: group.title,
        backgroundColor: SettingsSemanticConstants.blockBackground(isDark),
      );
    }

    return _SquareSymbolAvatar(
      isDark: isDark,
      icon: Icons.group,
      tintColor: AppColors.primaryColor,
      size: _groupConversationAvatarSize,
    );
  }

  Widget _buildRow(
    BuildContext context,
    ChatInboxDto group,
    bool isDark,
    Color fgPrimary,
  ) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => widget.onSelectGroup(group),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: SettingsSemanticConstants.selectionRowMinHeight,
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: SettingsSemanticConstants.blockHorizontalPadding,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              _buildLeading(group, isDark),
              SizedBox(width: ChatConversationAvatarTokens.leadingGap),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      group.title,
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        color: fgPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconMedium,
                color: SettingsSemanticConstants.selectionChevronColor(isDark),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final toolbarBg = SettingsSemanticConstants.selectionToolbarBackground(
      isDark,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final filtered = widget.groups.where(_matches).toList(growable: false);

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        backgroundColor: toolbarBg,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onClose,
        ),
        middle: Text(
          UITextConstants.selectGroupChat,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        border: Border(
          bottom: BorderSide(
            color: SettingsSemanticConstants.dividerColor(isDark),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.sm,
              AppSpacing.containerMd,
              AppSpacing.sm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: UITextConstants.searchGroupChatHint,
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          Expanded(
            child: filtered.isEmpty
                ? Center(
                    child: Text(
                      '暂无匹配群聊',
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        color: fgSecondary,
                      ),
                    ),
                  )
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
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
                              _buildRow(
                                context,
                                filtered[index],
                                isDark,
                                fgPrimary,
                              ),
                              if (index < filtered.length - 1)
                                _SelectionListDivider(
                                  isDark: isDark,
                                  leadingInset:
                                      ChatConversationAvatarTokens.dividerInset(
                                        _groupConversationAvatarSize,
                                      ),
                                ),
                            ],
                          ],
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

/// 选择圈子页
class _SelectCircleSheet extends StatefulWidget {
  const _SelectCircleSheet({
    required this.circles,
    required this.onSelectCircle,
    required this.onClose,
  });

  final List<CircleDto> circles;
  final void Function(CircleDto circle) onSelectCircle;
  final VoidCallback onClose;

  @override
  State<_SelectCircleSheet> createState() => _SelectCircleSheetState();
}

class _SelectCircleSheetState extends State<_SelectCircleSheet> {
  final TextEditingController _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  bool _matches(CircleDto circle) {
    final query = _query.trim().toLowerCase();
    if (query.isEmpty) {
      return true;
    }
    final name = circle.name.toLowerCase();
    final count = '${circle.memberCount}'.toLowerCase();
    return name.contains(query) || count.contains(query);
  }

  Widget _buildLeading(CircleDto circle, bool isDark) {
    final avatarUrl = circle.coverUrl ?? '';
    if (avatarUrl.isNotEmpty) {
      return RoundedSquareAvatar(
        size: AppSpacing.avatarSize,
        imageUrl: avatarUrl,
        name: circle.name,
        backgroundColor: SettingsSemanticConstants.blockBackground(isDark),
      );
    }

    return _SquareSymbolAvatar(
      isDark: isDark,
      icon: Icons.people_outline,
      tintColor: AppColors.secondaryColor,
    );
  }

  Widget _buildRow(
    CircleDto circle,
    bool isDark,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => widget.onSelectCircle(circle),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: SettingsSemanticConstants.selectionRowMinHeight,
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: SettingsSemanticConstants.blockHorizontalPadding,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              _buildLeading(circle, isDark),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      circle.name,
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        color: fgPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    SizedBox(height: AppSpacing.two),
                    Text(
                      '${circle.memberCount}${UITextConstants.friendsCount}',
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconMedium,
                color: SettingsSemanticConstants.selectionChevronColor(isDark),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final toolbarBg = SettingsSemanticConstants.selectionToolbarBackground(
      isDark,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final filtered = widget.circles.where(_matches).toList(growable: false);

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        backgroundColor: toolbarBg,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onClose,
        ),
        middle: Text(
          UITextConstants.selectCircle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        border: Border(
          bottom: BorderSide(
            color: SettingsSemanticConstants.dividerColor(isDark),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.sm,
              AppSpacing.containerMd,
              AppSpacing.sm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: UITextConstants.searchCircleHint,
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          Expanded(
            child: filtered.isEmpty
                ? Center(
                    child: Text(
                      '暂无匹配圈子',
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        color: fgSecondary,
                      ),
                    ),
                  )
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
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
                              _buildRow(
                                filtered[index],
                                isDark,
                                fgPrimary,
                                fgSecondary,
                              ),
                              if (index < filtered.length - 1)
                                _SelectionListDivider(
                                  isDark: isDark,
                                  leadingInset:
                                      AppSpacing.avatarSize + AppSpacing.sm,
                                ),
                            ],
                          ],
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
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final toolbarBg = SettingsSemanticConstants.selectionToolbarBackground(
      isDark,
    );
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

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        backgroundColor: toolbarBg,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
        middle: Text(
          widget.title,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        border: Border(
          bottom: BorderSide(
            color: SettingsSemanticConstants.dividerColor(isDark),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.sm,
              AppSpacing.containerMd,
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
                      '暂无匹配成员',
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        color: fgSecondary,
                      ),
                    ),
                  )
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerMd,
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
                                              backgroundColor:
                                                  SettingsSemanticConstants.blockBackground(
                                                    isDark,
                                                  ),
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
                                                      '已在群中',
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
              AppSpacing.containerMd,
              AppSpacing.sm,
              AppSpacing.containerMd,
              AppSpacing.sm + MediaQuery.paddingOf(context).bottom,
            ),
            decoration: BoxDecoration(
              color: toolbarBg,
              border: Border(
                top: BorderSide(
                  color: SettingsSemanticConstants.dividerColor(isDark),
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

class _SquareSymbolAvatar extends StatelessWidget {
  const _SquareSymbolAvatar({
    required this.isDark,
    required this.icon,
    required this.tintColor,
    this.size = AppSpacing.avatarSize,
  });

  final bool isDark;
  final IconData icon;
  final Color tintColor;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: tintColor.withValues(alpha: isDark ? 0.18 : 0.14),
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
      ),
      alignment: Alignment.center,
      child: Icon(
        icon,
        color: tintColor,
        size: size * ChatConversationAvatarTokens.placeholderIconScale,
      ),
    );
  }
}
