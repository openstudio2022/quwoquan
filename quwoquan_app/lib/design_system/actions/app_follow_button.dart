import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// 关注 pill 的视觉变体。
enum AppFollowButtonStyle {
  /// 亮面（feed 卡片作者栏等）：未关注 accent 浅底、已关注灰底次级字。
  tinted,

  /// 深色媒体面（沉浸式 toolbar 等叠在内容上的场景）：白字实底。
  onMedia,
}

/// 关注/已关注 pill 的唯一共享组件。
///
/// 关注状态的唯一真相源是 `userRelationshipStateProvider`，写意图统一走
/// `syncProfileFollowIntent` / `setFollowingWithSync`；本组件只收视觉形态，
/// 状态与登录门（`runWhenLoggedIn(AuthGateReason.follow, ...)`）由调用方持有。
///
/// 边界：profile_stats 的关系管理行按钮（followBack/mutual/pending + action
/// sheet 分发）是 capability 驱动的另一组件语义，不属于本 pill；不要为其
/// 增加参数造成伪统一。
class AppFollowButton extends StatelessWidget {
  const AppFollowButton({
    super.key,
    required this.isFollowing,
    required this.onPressed,
    this.style = AppFollowButtonStyle.tinted,
    this.label,
    this.height,
    this.pillKey,
  });

  final bool isFollowing;

  /// 为空时按钮呈禁用态（与 CupertinoButton 语义一致）。
  final VoidCallback? onPressed;
  final AppFollowButtonStyle style;

  /// 覆盖默认「关注/已关注」文案（如「回关」）。
  final String? label;

  /// 覆盖默认高度（如沉浸式 toolbar 与头像对齐时）。
  final double? height;

  /// 透传给 pill 容器的语义 key（测试探针）。
  final Key? pillKey;

  @override
  Widget build(BuildContext context) {
    final text =
        label ?? (isFollowing ? FoundationText.following : FoundationText.follow);
    final (Color background, Color foreground) = switch (style) {
      AppFollowButtonStyle.tinted => isFollowing
          ? (
              AppColors.iosSecondaryFill(context),
              AppColors.iosSecondaryLabel(context),
            )
          : (
              AppColors.iosAccent(context).withValues(alpha: 0.12),
              AppColors.iosAccent(context),
            ),
      AppFollowButtonStyle.onMedia => isFollowing
          ? (AppColors.followingButtonOnDark, AppColors.white)
          : (AppColors.primaryColor, AppColors.white),
    };
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onPressed,
      child: Container(
        key: pillKey,
        width: AppSpacing.followButtonWidthCompact,
        height: height ?? AppSpacing.buttonHeightXs,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          text,
          maxLines: 1,
          overflow: TextOverflow.fade,
          softWrap: false,
          style: TextStyle(
            fontSize: style == AppFollowButtonStyle.onMedia
                ? AppTypography.sm
                : AppTypography.xs,
            fontWeight: AppTypography.semiBold,
            color: foreground,
          ),
        ),
      ),
    );
  }
}
