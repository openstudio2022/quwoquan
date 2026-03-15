import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
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
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final bgColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

    final membersState =
        ref.watch(conversationMembersProvider(widget.conversationId));

    // 排除群主和当前用户自己
    final allMembers = membersState.members
        .where((m) => m['role'] != 'owner' && m['isCurrentUser'] != true)
        .toList();

    // 首次加载完成后初始化选中集合
    if (!membersState.isLoading && allMembers.isNotEmpty) {
      _initSelectedIds(membersState.members);
    }

    final filtered = _searchQuery.isEmpty
        ? allMembers
        : allMembers.where((m) {
            final name = (m['displayName'] ?? m['name'] ?? '') as String;
            return name.toLowerCase().contains(_searchQuery.toLowerCase());
          }).toList();

    final selectedMembers = allMembers.where(
      (m) => _selectedIds.contains(m['userId'] as String? ?? ''),
    );

    return AppScaffold(
      backgroundColor: bgColor,
      navigationBar: AppNavigationBar(
        backgroundColor: bgColor,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.selectGroupMembers,
          style: TextStyle(
            color: fgPrimary,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w600,
          ),
        ),
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
      ),
      body: Column(
        children: [
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xs,
              ),
              decoration: BoxDecoration(
                color: isDark
                    ? Colors.white.withValues(alpha: 0.08)
                    : Colors.grey.shade100,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              ),
              child: Row(
                children: [
                  ...selectedMembers.map((m) {
                    final avatar = m['avatarUrl'] as String? ??
                        m['avatar'] as String? ??
                        '';
                    return Padding(
                      padding: EdgeInsets.only(right: AppSpacing.xs),
                      child: RoundedSquareAvatar(
                        size: AppSpacing.largeButtonSize * 0.8,
                        imageUrl: avatar,
                        name: m['displayName'] as String? ?? '',
                      ),
                    );
                  }),
                  Expanded(
                    child: CupertinoSearchTextField(
                      controller: _searchController,
                      placeholder: UITextConstants.search,
                      onChanged: (v) => setState(() => _searchQuery = v),
                      style: TextStyle(color: fgPrimary),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Expanded(
            child: membersState.isLoading
                ? const Center(child: CupertinoActivityIndicator())
                : ListView.builder(
                    itemCount: filtered.length,
                    itemBuilder: (context, i) {
                      final m = filtered[i];
                      final userId = m['userId'] as String? ?? '';
                      final name =
                          m['displayName'] as String? ?? m['name'] as String? ?? '';
                      final avatar =
                          m['avatarUrl'] as String? ?? m['avatar'] as String? ?? '';
                      final nickname = m['nickname'] as String? ?? '';
                      final isSelected = _selectedIds.contains(userId);

                      return GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () => _toggleMember(userId),
                        child: Padding(
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpacing.md,
                            vertical: AppSpacing.sm,
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: AppSpacing.iconMedium,
                                height: AppSpacing.iconMedium,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: isSelected
                                      ? AppColors.primaryColor
                                      : Colors.transparent,
                                  border: Border.all(
                                    color: isSelected
                                        ? AppColors.primaryColor
                                        : fgSecondary,
                                    width: AppSpacing.oneHalf,
                                  ),
                                ),
                                child: isSelected
                                    ? Icon(
                                        Icons.check,
                                        size: AppSpacing.iconSmall,
                                        color: Colors.white,
                                      )
                                    : null,
                              ),
                              SizedBox(width: AppSpacing.interGroupSm),
                              RoundedSquareAvatar(
                                size: AppSpacing.largeButtonSize,
                                imageUrl: avatar,
                                name: name,
                              ),
                              SizedBox(width: AppSpacing.interGroupSm),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Text(
                                          name,
                                          style: TextStyle(
                                            fontSize: AppTypography.lg,
                                            color: fgPrimary,
                                          ),
                                        ),
                                        if (m['role'] == 'admin') ...[
                                          SizedBox(width: AppSpacing.xs),
                                          Container(
                                            padding: EdgeInsets.symmetric(
                                              horizontal: AppSpacing.xs,
                                              vertical: AppSpacing.one,
                                            ),
                                            decoration: BoxDecoration(
                                              color: AppColors.primaryColor
                                                  .withValues(alpha: 0.12),
                                              borderRadius: BorderRadius.circular(
                                                AppSpacing.borderRadius,
                                              ),
                                            ),
                                            child: Text(
                                              UITextConstants.admin,
                                              style: TextStyle(
                                                fontSize: AppTypography.xs,
                                                color: AppColors.primaryColor,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ],
                                    ),
                                    if (nickname.isNotEmpty)
                                      Text(
                                        nickname,
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
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
