import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

class ProfileInteractionTab extends ConsumerWidget {
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
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.watch(profileNotifierProvider(userId));
    final state = notifier.state;
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final primary = AppColors.primaryColor;
    final border = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Column(
      children: [
        SizedBox(
          height: AppSpacing.subTabNavigationHeight,
          child: Row(
            children: [
              SizedBox(width: AppSpacing.containerMd),
              _SubTabChip(
                label: '赞',
                isActive: state.interactionSubTab == InteractionSubTab.likes,
                onTap: () => notifier.setInteractionSubTab(InteractionSubTab.likes),
                fg: fg,
                primary: primary,
                border: border,
              ),
              SizedBox(width: AppSpacing.sm),
              _SubTabChip(
                label: '评论',
                isActive: state.interactionSubTab == InteractionSubTab.comments,
                onTap: () => notifier.setInteractionSubTab(InteractionSubTab.comments),
                fg: fg,
                primary: primary,
                border: border,
              ),
              const Spacer(),
              if (mode == ProfileMode.mine) ...[
                _DirectionChip(
                  label: '收到',
                  isActive: state.interactionDirection == InteractionDirection.received,
                  onTap: () => notifier.setInteractionDirection(InteractionDirection.received),
                  fg: fg,
                  primary: primary,
                  border: border,
                ),
                SizedBox(width: AppSpacing.xs),
                _DirectionChip(
                  label: '发出',
                  isActive: state.interactionDirection == InteractionDirection.sent,
                  onTap: () => notifier.setInteractionDirection(InteractionDirection.sent),
                  fg: fg,
                  primary: primary,
                  border: border,
                ),
                SizedBox(width: AppSpacing.containerMd),
              ],
            ],
          ),
        ),
        Expanded(
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  state.interactionSubTab == InteractionSubTab.likes
                      ? Icons.favorite_outline
                      : Icons.chat_bubble_outline,
                  size: AppSpacing.xl * 2,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  '暂无互动记录',
                  style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _SubTabChip extends StatelessWidget {
  const _SubTabChip({
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
          color: isActive ? primary.withValues(alpha: 0.1) : null,
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: isActive ? null : Border.all(color: border.withValues(alpha: 0.3)),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.md,
            fontWeight: isActive ? AppTypography.semiBold : AppTypography.normal,
            color: isActive ? primary : fg,
          ),
        ),
      ),
    );
  }
}

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
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.sm,
            fontWeight: isActive ? AppTypography.semiBold : AppTypography.normal,
            color: isActive ? primary : fg,
          ),
        ),
      ),
    );
  }
}
