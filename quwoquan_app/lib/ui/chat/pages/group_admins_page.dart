import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/search/search_embedded.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
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
  void _initSelectedIds(List<Map<String, dynamic>> members) {
    if (_initialized) return;
    _initialized = true;
    for (final m in members) {
      if (m['role'] == 'admin') {
        _selectedIds.add(m['userId'] as String? ?? '');
      }
    }
  }

  void _toggleMember(String userId) {
    setState(() {
      if (_selectedIds.contains(userId)) {
        _selectedIds.remove(userId);
      } else {
        if (_selectedIds.length >= _maxAdmins) {
          showCupertinoDialog<void>(
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
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);

    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );

    // 排除群主和当前用户自己
    final allMembers = membersState.members
        .where((m) => m['role'] != 'owner' && m['isCurrentUser'] != true)
        .toList();

    // 首次加载完成后初始化选中集合
    if (!membersState.isLoading && allMembers.isNotEmpty) {
      _initSelectedIds(membersState.members);
    }

    final filtered = filterMemberMapsByQuery(allMembers, _searchQuery);

    final selectedMembers = allMembers
        .where((m) => _selectedIds.contains(m['userId'] as String? ?? ''))
        .toList();

    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: UITextConstants.selectGroupMembers,
      onBack: () => context.pop(),
      trailing: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: _selectedIds.isEmpty ? null : _onDone,
        child: Text(
          '${UITextConstants.done}(${_selectedIds.length})',
          style: TextStyle(
            fontWeight: FontWeight.w600,
            color: _selectedIds.isEmpty
                ? CupertinoColors.systemGrey
                : AppColors.primaryColor,
          ),
        ),
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
                                isSelected: _selectedIds.contains(
                                  m['userId'] as String? ?? '',
                                ),
                                onTap: () => _toggleMember(
                                  m['userId'] as String? ?? '',
                                ),
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
