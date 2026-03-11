import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

class ProfileInteractionTab extends ConsumerStatefulWidget {
  const ProfileInteractionTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;

  @override
  ConsumerState<ProfileInteractionTab> createState() =>
      _ProfileInteractionTabState();
}

class _ProfileInteractionTabState extends ConsumerState<ProfileInteractionTab> {
  List<Map<String, dynamic>>? _items;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final notifier = ref.read(profileNotifierProvider(widget.userId));
    final direction = notifier.state.interactionDirection;
    final subTab = notifier.state.interactionSubTab;
    final repo = ref.read(userProfileRepositoryProvider);
    setState(() => _loading = true);
    try {
      final list = direction == InteractionDirection.received
          ? await repo.listUserInteractionReceived(widget.userId)
          : await repo.listUserInteractionSent(widget.userId);

      final filtered = list.where((item) {
        final contentType = item['contentType'] as String? ?? '';
        if (subTab == InteractionSubTab.comments) {
          return contentType == 'comment';
        } else {
          return contentType == 'favorite';
        }
      }).toList();

      if (mounted) {
        setState(() {
          _items = filtered;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _items = [];
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final notifier = ref.watch(profileNotifierProvider(widget.userId));
    final state = notifier.state;
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final primary = AppColors.primaryColor;
    final border = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.borderPrimary,
    );

    return Column(
      children: [
        Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              // 二级 Tab: 评论 | 收藏
              _SubTabChip(
                label: '评论',
                isActive:
                    state.interactionSubTab == InteractionSubTab.comments,
                onTap: () {
                  notifier.setInteractionSubTab(InteractionSubTab.comments);
                  _load();
                },
                fg: fg,
                primary: primary,
              ),
              SizedBox(width: AppSpacing.xs),
              _SubTabChip(
                label: '收藏',
                isActive:
                    state.interactionSubTab == InteractionSubTab.favorites,
                onTap: () {
                  notifier.setInteractionSubTab(InteractionSubTab.favorites);
                  _load();
                },
                fg: fg,
                primary: primary,
              ),

              const Spacer(),

              // 方向切换: 接收 | 发送 (仅自己的主页显示)
              if (widget.mode == ProfileMode.mine) ...[
                _DirectionChip(
                  label: '接收',
                  isActive: state.interactionDirection ==
                      InteractionDirection.received,
                  onTap: () {
                    notifier.setInteractionDirection(
                      InteractionDirection.received,
                    );
                    _load();
                  },
                  fg: fg,
                  primary: primary,
                  border: border,
                ),
                SizedBox(width: AppSpacing.xs),
                _DirectionChip(
                  label: '发送',
                  isActive:
                      state.interactionDirection == InteractionDirection.sent,
                  onTap: () {
                    notifier.setInteractionDirection(
                      InteractionDirection.sent,
                    );
                    _load();
                  },
                  fg: fg,
                  primary: primary,
                  border: border,
                ),
              ],
            ],
          ),
        ),
        Expanded(
          child: _loading
              ? Center(child: CircularProgressIndicator(color: primary))
              : _items == null || _items!.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            state.interactionSubTab ==
                                    InteractionSubTab.comments
                                ? Icons.chat_bubble_outline
                                : Icons.star_outline,
                            size: AppSpacing.xl * 2,
                            color: fgSecondary,
                          ),
                          SizedBox(height: AppSpacing.md),
                          Text(
                            state.interactionSubTab ==
                                    InteractionSubTab.comments
                                ? '暂无评论记录'
                                : '暂无收藏记录',
                            style: TextStyle(
                              fontSize: AppTypography.md,
                              color: fgSecondary,
                            ),
                          ),
                        ],
                      ),
                    )
                  : ListView.separated(
                      padding: EdgeInsets.all(AppSpacing.containerMd),
                      itemCount: _items!.length,
                      separatorBuilder: (_, __) =>
                          SizedBox(height: AppSpacing.sm),
                      itemBuilder: (context, i) {
                        final item = _items![i];
                        final userId = item['userId'] as String? ?? '';
                        final nickname = item['nickname'] as String? ?? '';
                        final avatarUrl = item['avatarUrl'] as String? ?? '';
                        final targetTitle =
                            item['targetTitle'] as String? ?? '';
                        return InkWell(
                          onTap: () {
                            if (userId.isNotEmpty) {
                              context.push(
                                AppRoutePaths.userProfile(username: userId),
                                extra: UserProfileRouteExtra(
                                  avatar:
                                      avatarUrl.isNotEmpty ? avatarUrl : null,
                                  displayName:
                                      nickname.isNotEmpty ? nickname : null,
                                ),
                              );
                            }
                          },
                          child: Row(
                            children: [
                              CircleAvatar(
                                radius: 24,
                                backgroundImage: avatarUrl.isNotEmpty
                                    ? NetworkImage(avatarUrl)
                                    : null,
                                onBackgroundImageError: (_, __) {},
                                child: avatarUrl.isEmpty
                                    ? Icon(Icons.person, color: fgSecondary)
                                    : null,
                              ),
                              SizedBox(width: AppSpacing.containerSm),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      nickname,
                                      style: TextStyle(
                                        fontSize: AppTypography.md,
                                        fontWeight: AppTypography.semiBold,
                                        color: fg,
                                      ),
                                    ),
                                    if (targetTitle.isNotEmpty)
                                      Text(
                                        targetTitle,
                                        style: TextStyle(
                                          fontSize: AppTypography.sm,
                                          color: fgSecondary,
                                        ),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
        ),
      ],
    );
  }
}

/// 二级 Tab chip（评论/收藏），使用 Tab 样式：选中时有底部指示线效果。
class _SubTabChip extends StatelessWidget {
  const _SubTabChip({
    required this.label,
    required this.isActive,
    required this.onTap,
    required this.fg,
    required this.primary,
  });

  final String label;
  final bool isActive;
  final VoidCallback onTap;
  final Color fg;
  final Color primary;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          border: isActive
              ? Border(
                  bottom: BorderSide(color: primary, width: 2),
                )
              : null,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.base,
            fontWeight:
                isActive ? AppTypography.semiBold : AppTypography.normal,
            color: isActive ? fg : fg.withValues(alpha: 0.6),
          ),
        ),
      ),
    );
  }
}

/// 方向切换 chip（接收/发送），保持现有圆角胶囊样式。
class _DirectionChip extends StatelessWidget {
  const _DirectionChip({
    required this.label,
    required this.isActive,
    required this.onTap,
    required this.fg,
    required this.primary,
    required this.border,
  });

  final String label;
  final bool isActive;
  final VoidCallback onTap;
  final Color fg;
  final Color primary;
  final Color border;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          color: isActive ? primary.withValues(alpha: 0.08) : null,
          borderRadius:
              BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.sm,
            fontWeight:
                isActive ? AppTypography.semiBold : AppTypography.normal,
            color: isActive ? primary : fg,
          ),
        ),
      ),
    );
  }
}
