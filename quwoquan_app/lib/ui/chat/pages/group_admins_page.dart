import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/search/search_embedded.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

/// 群管理员设置页 — 多选最多 3 人
class GroupAdminsPage extends ConsumerStatefulWidget {
  const GroupAdminsPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<GroupAdminsPage> createState() => _GroupAdminsPageState();
}

class _GroupAdminsPageState extends ConsumerState<GroupAdminsPage> {
  static const int _maxAdmins = 3;

  // 本地选中集合，从 Provider state 初始化后独立管理
  final Set<String> _selectedIds = {};
  bool _initialized = false;
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  /// 从 Provider state 初始化选中集合（只初始化一次）
  void _initSelectedIds(List<ChatConversationMemberDto> members) {
    if (_initialized) return;
    _initialized = true;
    for (final m in members) {
      if (m.role == 'admin') {
        _selectedIds.add(m.userId);
      }
    }
  }

  void _toggleMember(String userId) {
    setState(() {
      if (_selectedIds.contains(userId)) {
        _selectedIds.remove(userId);
      } else {
        if (_selectedIds.length >= _maxAdmins) {
          showAppCupertinoDialog<void>(
            context: context,
            builder: (_) => CupertinoAlertDialog(
              content: Text(UITextConstants.maxAdminsReached),
              actions: [
                CupertinoDialogAction(
                  child: Text(UITextConstants.confirm),
                  onPressed: () => Navigator.pop(context),
                ),
              ],
            ),
          );
          return;
        }
        _selectedIds.add(userId);
      }
    });
  }

  Future<void> _onDone() async {
    try {
      await ref
          .read(conversationMembersProvider(widget.conversationId).notifier)
          .updateGroupAdmins(_selectedIds.toList());
      if (mounted) context.pop();
    } catch (error) {
      if (!mounted) {
        return;
      }
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      final semantic = UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: '管理员更新未完成',
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.retry,
          label: UITextConstants.tryAgain,
        ),
        secondaryAction: resolved.secondaryAction,
        dismissible: resolved.dismissible,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        recoveryAction: resolved.recoveryAction,
        presentation: resolved.presentation,
        tone: resolved.tone,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _onDone();
          }
        },
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);

    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );

    // 排除群主和当前用户自己
    final allMembers = membersState.members
        .where((m) => m.role != 'owner' && !m.isCurrentUser)
        .toList();

    // 首次加载完成后初始化选中集合
    if (!membersState.isLoading && allMembers.isNotEmpty) {
      _initSelectedIds(membersState.members);
    }

    final filtered = filterMemberDtosByQuery(allMembers, _searchQuery);

    final selectedMembers = allMembers
        .where((m) => _selectedIds.contains(m.userId))
        .map((e) => e.toMap())
        .toList();

    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: UITextConstants.selectGroupMembers,
      onBack: () => context.pop(),
      trailing: AppNavigationBarTextAction(
        label: '${UITextConstants.done}(${_selectedIds.length})',
        enabled: _selectedIds.isNotEmpty,
        onPressed: _selectedIds.isEmpty ? null : _onDone,
      ),
      body: Column(
        children: [
          EmbeddedMemberSearchBarWithChips(
            isDark: isDark,
            controller: _searchController,
            placeholder: UITextConstants.search,
            onChanged: (v) => setState(() => _searchQuery = v),
            selectedMembers: selectedMembers,
            onSelectedMemberTap: _toggleMember,
          ),
          Expanded(
            child: membersState.isLoading
                ? const Center(child: CupertinoActivityIndicator())
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
                    ),
                    children: [
                      if (filtered.isNotEmpty)
                        InsetGroupedMemberListCard(
                          isDark: isDark,
                          dividerKind: MemberListDividerInsetKind.multiSelect,
                          tileWidgets: [
                            for (final m in filtered)
                              MemberListMultiSelectTile(
                                isDark: isDark,
                                member: m,
                                isSelected: _selectedIds.contains(m.userId),
                                onTap: () => _toggleMember(m.userId),
                              ),
                          ],
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
