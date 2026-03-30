import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/avatar/group_avatar_grid.dart';
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
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';

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
  final Map<String, Map<String, String>> _selectedMembers = {};
  final Set<String> _existingMemberIds = <String>{};

  List<ChatInboxDto> _groupInboxRows = [];
  List<ChatContactRowDto> _contacts = [];
  List<CircleDto> _circles = [];
  bool _selectedExpanded = false;
  bool _submitting = false;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    try {
      final chatRepo = ref.read(chatRepositoryProvider);
      final userRepo = ref.read(userProfileRepositoryProvider);
      final currentUserId = ref.read(currentUserIdProvider);
      final inbox = await chatRepo.listInbox(limit: 50);
      final convMaps = await chatRepo.listConversations(limit: 50);
      final contacts = await chatRepo.listContacts(limit: 200);
      final circleMaps = await userRepo.listUserCircles(
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
      if (mounted) {
        setState(() {
          final convId = widget.conversationId ?? '';
          _groupInboxRows = inbox
              .where(
                (row) => row.type == 'group' && row.id.isNotEmpty && row.id != convId,
              )
              .toList(growable: false);
          _contacts = contacts;
          final activeCircleIds = convMaps
              .where((conversation) => conversation['type'] == 'circle')
              .map(
                (conversation) =>
                    _readString(conversation, const ['circleId', 'id']),
              )
              .where((circleId) => circleId.isNotEmpty)
              .toSet();
          _circles = circleMaps
              .map(CircleDto.fromMap)
              .where((circle) => activeCircleIds.contains(circle.id))
              .toList(growable: false);
          _existingMemberIds
            ..clear()
            ..addAll(
              existingMembers
                  .map((m) => m.userId)
                  .where((id) => id.isNotEmpty),
            );
        });
      }
    } catch (_) {
      // Fallback: leave empty lists
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    _listScrollController.dispose();
    super.dispose();
  }

  static String _readString(Map<String, dynamic> source, List<String> keys) {
    for (final key in keys) {
      final value = source[key];
      if (value == null) {
        continue;
      }
      final text = value.toString().trim();
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }

  Set<String> get _mutualContactIds {
    return _contacts
        .map((contact) => contact.userId)
        .where((id) => id.isNotEmpty && !_existingMemberIds.contains(id))
        .toSet();
  }

  List<Map<String, String>> _normalizeSelectableMembers(
    List<Map<String, dynamic>> members, {
    bool mutualOnly = false,
  }) {
    final allowedIds = _mutualContactIds;
    final normalized = <Map<String, String>>[];
    final seen = <String>{};
    for (final member in members) {
      final userId = _readString(member, const [
        'userId',
        'profileSubjectId',
        'contactId',
      ]);
      if (userId.isEmpty ||
          _existingMemberIds.contains(userId) ||
          seen.contains(userId)) {
        continue;
      }
      if (mutualOnly && !allowedIds.contains(userId)) {
        continue;
      }
      seen.add(userId);
      normalized.add(<String, String>{
        'userId': userId,
        'name': _readString(member, const [
          'displayName',
          'nickname',
          'name',
          'username',
        ]),
        'username': userId,
        'avatar': _readString(member, const [
          'avatarUrl',
          'avatar',
          'coverUrl',
        ]),
      });
    }
    return normalized;
  }

  void _mergeSelectedMembers(List<Map<String, String>> members) {
    setState(() {
      for (final member in members) {
        final userId = member['userId'] ?? member['username'] ?? '';
        if (userId.isEmpty || _existingMemberIds.contains(userId)) {
          continue;
        }
        _selectedMembers[userId] = <String, String>{
          'userId': userId,
          'name': member['name'] ?? userId,
          'username': member['username'] ?? userId,
          'avatar': member['avatar'] ?? '',
        };
      }
    });
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

  void _toggleSelectedMember(Map<String, String> member) {
    final userId = member['userId'] ?? member['username'] ?? '';
    if (userId.isEmpty) {
      return;
    }
    setState(() {
      if (_selectedMembers.containsKey(userId)) {
        _selectedMembers.remove(userId);
      } else {
        _selectedMembers[userId] = member;
      }
    });
  }

  Future<void> _submitSelection() async {
    if (_submitting || _selectedMembers.isEmpty) {
      return;
    }
    final selectedIds = _selectedMembers.keys.toList(growable: false);
    if (widget.isCreateMode && selectedIds.length >= 500) {
      AppToast.show(context, '群成员数量超过上限');
      return;
    }
    setState(() => _submitting = true);
    try {
      final repo = ref.read(chatRepositoryProvider);
      if (widget.isCreateMode) {
        final created = await repo.createConversation(
          type: 'group',
          title: _selectedMembers.values
              .map((member) => member['name'] ?? '')
              .where((name) => name.isNotEmpty)
              .take(3)
              .join('、'),
          maxGroupSize: 500,
          initialMemberIds: selectedIds,
        );
        final conversationId = _readString(created, const [
          '_id',
          'id',
          'conversationId',
        ]);
        if (!context.mounted) {
          return;
        }
        await ref.read(chatInboxListProvider.notifier).refresh();
        if (!context.mounted) {
          return;
        }
        _handleCreateConversationSuccess(conversationId);
      } else {
        await repo.addMembers(
          conversationId: widget.conversationId!,
          userIds: selectedIds,
        );
        await ref.read(chatInboxListProvider.notifier).refresh();
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
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (context) => _SelectGroupChatSheet(
        groups: _groupInboxRows
            .map(
              (g) => <String, dynamic>{
                'id': g.id,
                'name': g.title,
                'count': '',
                'avatar': g.avatarUrl,
                'memberAvatars': g.avatarCompositeUrls,
              },
            )
            .toList(growable: false),
        onSelectGroup: (group) async {
          Navigator.of(context).pop();
          final members = await ref
              .read(chatRepositoryProvider)
              .listMembers(
                conversationId: (group['id'] ?? '').toString(),
                limit: 500,
              );
          final selectableMembers = _normalizeSelectableMembers(
            members.map((m) => m.toMap()).toList(growable: false),
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
            title:
                '${group['name']}${(group['count'] as String).isEmpty ? '' : ' (${group['count']}${UITextConstants.friendsCount})'}',
            members: selectableMembers,
            onConfirm: _mergeSelectedMembers,
          );
        },
        onClose: () => Navigator.of(context).pop(),
      ),
    );
  }

  void _openSelectCircleSheet() {
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (context) => _SelectCircleSheet(
        circles: _circles
            .map(
              (circle) => <String, dynamic>{
                'id': circle.id,
                'name': circle.name,
                'count': '${circle.memberCount}',
                'avatar': circle.coverUrl ?? '',
              },
            )
            .toList(),
        onSelectCircle: (circle) async {
          Navigator.of(context).pop();
          final members = await ref
              .read(circleRepositoryProvider)
              .listMembers((circle['id'] ?? '').toString(), limit: 500);
          final selectableMembers = _normalizeSelectableMembers(
            members,
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
                '${circle['name']} (${circle['count']}${UITextConstants.friendsCount})',
            members: selectableMembers,
            onConfirm: _mergeSelectedMembers,
          );
        },
        onClose: () => Navigator.of(context).pop(),
      ),
    );
  }

  void _openMemberSelectSheet({
    required String title,
    required List<Map<String, String>> members,
    required void Function(List<Map<String, String>>) onConfirm,
  }) {
    showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (context) => _MemberSelectSheet(
        title: title,
        members: members,
        onConfirm: onConfirm,
        onBack: () => Navigator.of(context).pop(),
      ),
    );
  }

  /// 按首字母分组：A-Z, #，返回有序 keys 与 map
  static ({List<String> keys, Map<String, List<Map<String, dynamic>>> map})
  _groupByLetter(List<Map<String, dynamic>> list) {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final m in list) {
      final name = m['name'] as String? ?? '';
      final letter =
          m['letter'] as String? ??
          (name.isNotEmpty ? name.substring(0, 1).toUpperCase() : '#');
      final key = RegExp(r'[A-Za-z]').hasMatch(letter)
          ? letter.toUpperCase()
          : '#';
      map.putIfAbsent(key, () => []).add(m);
    }
    for (final key in map.keys) {
      map[key]!.sort(
        (a, b) => (a['name'] as String).compareTo(b['name'] as String),
      );
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
    final selectedMembers = _selectedMembers.values.toList(growable: false);
    final visibleSelectedCount = _selectedExpanded
        ? selectedMembers.length
        : (selectedMembers.length > 12 ? 12 : selectedMembers.length);
    final friendsWithLetter = _contacts
        .where((contact) {
          final userId = contact.userId;
          if (userId.isEmpty || _existingMemberIds.contains(userId)) {
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
        .map(
          (c) {
            final displayName = c.displayName;
            return <String, dynamic>{
              'name': displayName,
              'username': c.userId,
              'avatar': c.avatarUrl,
              'letter': displayName.isNotEmpty
                  ? displayName.substring(0, 1).toUpperCase()
                  : '#',
            };
          },
        )
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
              onTap: _openSelectGroupChatSheet,
            ),
            _SelectionListDivider(isDark: isDark),
            _SectionRow(
              label: UITextConstants.selectFriendsFromCircle,
              fgPrimary: fgPrimary,
              isDark: isDark,
              onTap: _openSelectCircleSheet,
            ),
          ],
        ),
      ),
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
                        final username = m['username'] as String? ?? '';
                        final selected = _selectedMembers.containsKey(username);
                        return _RelatedFriendRow(
                          name: m['name'] as String,
                          username: username,
                          avatarUrl: m['avatar'] as String? ?? '',
                          selected: selected,
                          fgPrimary: fgPrimary,
                          onTap: () => _toggleSelectedMember(<String, String>{
                            'userId': username,
                            'name': m['name'] as String? ?? username,
                            'username': username,
                            'avatar': m['avatar'] as String? ?? '',
                          }),
                          onAvatarTap: () => context.push(
                            AppRoutePaths.userProfile(username: username),
                            extra: UserProfileRouteExtra(
                              profileSubjectId: username,
                              avatar: m['avatar'] as String?,
                              displayName: m['name'] as String?,
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
                        final userId = member['userId'] ?? '';
                        return _SelectedMemberAvatar(
                          name: member['name'] ?? userId,
                          avatarUrl: member['avatar'] ?? '',
                          isDark: isDark,
                          onRemove: () =>
                              setState(() => _selectedMembers.remove(userId)),
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
  final VoidCallback onTap;

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
                    color: fgPrimary,
                  ),
                ),
              ),
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
}

class _RelatedFriendRow extends StatelessWidget {
  const _RelatedFriendRow({
    required this.name,
    required this.username,
    required this.avatarUrl,
    required this.selected,
    required this.fgPrimary,
    required this.onTap,
    required this.onAvatarTap,
    required this.isDark,
  });

  final String name;
  final String username;
  final String avatarUrl;
  final bool selected;
  final Color fgPrimary;
  final VoidCallback onTap;
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
              _SelectionIndicator(selected: selected, onTap: onTap),
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
                child: Text(
                  name,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    color: fgPrimary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
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
  const _SelectionIndicator({required this.selected, required this.onTap});

  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      child: Icon(
        selected
            ? CupertinoIcons.check_mark_circled_solid
            : CupertinoIcons.circle,
        color: selected ? AppColors.primaryColor : CupertinoColors.systemGrey2,
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

  final List<Map<String, dynamic>> groups;
  final void Function(Map<String, dynamic> group) onSelectGroup;
  final VoidCallback onClose;

  @override
  State<_SelectGroupChatSheet> createState() => _SelectGroupChatSheetState();
}

class _SelectGroupChatSheetState extends State<_SelectGroupChatSheet> {
  final TextEditingController _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  bool _matches(Map<String, dynamic> group) {
    final query = _query.trim().toLowerCase();
    if (query.isEmpty) {
      return true;
    }
    final name = (group['name'] ?? '').toString().toLowerCase();
    final count = (group['count'] ?? '').toString().toLowerCase();
    return name.contains(query) || count.contains(query);
  }

  Widget _buildLeading(Map<String, dynamic> group, bool isDark) {
    final memberAvatars =
        (group['memberAvatars'] as List<dynamic>? ?? const <dynamic>[])
            .map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false);
    if (memberAvatars.isNotEmpty) {
      return GroupAvatarGrid(
        size: AppSpacing.avatarSize,
        avatarUrls: memberAvatars,
      );
    }

    final avatarUrl = (group['avatar'] ?? '').toString();
    if (avatarUrl.isNotEmpty) {
      return RoundedSquareAvatar(
        size: AppSpacing.avatarSize,
        imageUrl: avatarUrl,
        name: (group['name'] ?? '').toString(),
        backgroundColor: SettingsSemanticConstants.blockBackground(isDark),
      );
    }

    return _SquareSymbolAvatar(
      isDark: isDark,
      icon: Icons.group,
      tintColor: AppColors.primaryColor,
    );
  }

  Widget _buildRow(
    BuildContext context,
    Map<String, dynamic> group,
    bool isDark,
    Color fgPrimary,
    Color fgSecondary,
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
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      (group['name'] ?? '').toString(),
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        color: fgPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    SizedBox(height: AppSpacing.two),
                    Text(
                      '${group['count']}${UITextConstants.friendsCount}',
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

/// 选择圈子页
class _SelectCircleSheet extends StatefulWidget {
  const _SelectCircleSheet({
    required this.circles,
    required this.onSelectCircle,
    required this.onClose,
  });

  final List<Map<String, dynamic>> circles;
  final void Function(Map<String, dynamic> circle) onSelectCircle;
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

  bool _matches(Map<String, dynamic> circle) {
    final query = _query.trim().toLowerCase();
    if (query.isEmpty) {
      return true;
    }
    final name = (circle['name'] ?? '').toString().toLowerCase();
    final count = (circle['count'] ?? '').toString().toLowerCase();
    return name.contains(query) || count.contains(query);
  }

  Widget _buildLeading(Map<String, dynamic> circle, bool isDark) {
    final avatarUrl = (circle['avatar'] ?? '').toString();
    if (avatarUrl.isNotEmpty) {
      return RoundedSquareAvatar(
        size: AppSpacing.avatarSize,
        imageUrl: avatarUrl,
        name: (circle['name'] ?? '').toString(),
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
    Map<String, dynamic> circle,
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
                      (circle['name'] ?? '').toString(),
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        color: fgPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    SizedBox(height: AppSpacing.two),
                    Text(
                      '${circle['count']}${UITextConstants.friendsCount}',
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
class _MemberSelectSheet extends StatefulWidget {
  const _MemberSelectSheet({
    required this.title,
    required this.members,
    required this.onConfirm,
    required this.onBack,
  });

  final String title;
  final List<Map<String, String>> members;
  final void Function(List<Map<String, String>> selected) onConfirm;
  final VoidCallback onBack;

  @override
  State<_MemberSelectSheet> createState() => _MemberSelectSheetState();
}

class _MemberSelectSheetState extends State<_MemberSelectSheet> {
  final Set<String> _selectedIds = <String>{};
  final TextEditingController _searchController = TextEditingController();
  String _query = '';

  String _memberId(Map<String, String> member) {
    final userId = (member['userId'] ?? '').trim();
    if (userId.isNotEmpty) {
      return userId;
    }
    final username = (member['username'] ?? '').trim();
    if (username.isNotEmpty) {
      return username;
    }
    return (member['name'] ?? '').trim();
  }

  bool get _allSelected => _selectedIds.length == widget.members.length;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _toggleMember(Map<String, String> member) {
    final id = _memberId(member);
    if (id.isEmpty) {
      return;
    }
    setState(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
      } else {
        _selectedIds.add(id);
      }
    });
  }

  void _toggleAll() {
    setState(() {
      if (_allSelected) {
        _selectedIds.clear();
      } else {
        _selectedIds
          ..clear()
          ..addAll(widget.members.map(_memberId).where((id) => id.isNotEmpty));
      }
    });
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
    final filtered = widget.members
        .where((member) {
          final query = _query.trim().toLowerCase();
          if (query.isEmpty) {
            return true;
          }
          final name = (member['name'] ?? '').toLowerCase();
          final userId = _memberId(member).toLowerCase();
          return name.contains(query) || userId.contains(query);
        })
        .toList(growable: false);

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
                                  final selected = _selectedIds.contains(
                                    _memberId(member),
                                  );
                                  return CupertinoButton(
                                    padding: EdgeInsets.zero,
                                    onPressed: () => _toggleMember(member),
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
                                              onTap: () =>
                                                  _toggleMember(member),
                                            ),
                                            RoundedSquareAvatar(
                                              size: AppSpacing.avatarSize,
                                              imageUrl: member['avatar'] ?? '',
                                              name: member['name'] ?? '',
                                              backgroundColor:
                                                  SettingsSemanticConstants.blockBackground(
                                                    isDark,
                                                  ),
                                            ),
                                            SizedBox(width: AppSpacing.sm),
                                            Expanded(
                                              child: Text(
                                                member['name'] ?? '',
                                                style: TextStyle(
                                                  fontSize: AppTypography.lg,
                                                  color: fgPrimary,
                                                ),
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
                  onPressed: _toggleAll,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _SelectionIndicator(
                        selected: _allSelected,
                        onTap: _toggleAll,
                      ),
                      Text(
                        UITextConstants.selectAll,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          color: fgPrimary,
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
                  onPressed: _selectedIds.isEmpty
                      ? null
                      : () {
                          final list = widget.members
                              .where(
                                (member) =>
                                    _selectedIds.contains(_memberId(member)),
                              )
                              .toList(growable: false);
                          Navigator.of(context).pop();
                          widget.onConfirm(list);
                        },
                  minimumSize: Size(
                    SettingsSemanticConstants.actionButtonHeightMedium,
                    SettingsSemanticConstants.actionButtonHeightMedium,
                  ),
                  child: Text(
                    '${UITextConstants.selectAction}（${_selectedIds.length}）',
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      fontWeight: FontWeight.w500,
                      color: _selectedIds.isEmpty
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
  });

  final bool isDark;
  final IconData icon;
  final Color tintColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSpacing.avatarSize,
      height: AppSpacing.avatarSize,
      decoration: BoxDecoration(
        color: tintColor.withValues(alpha: isDark ? 0.18 : 0.14),
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
      ),
      alignment: Alignment.center,
      child: Icon(icon, color: tintColor, size: AppSpacing.iconLarge),
    );
  }
}
