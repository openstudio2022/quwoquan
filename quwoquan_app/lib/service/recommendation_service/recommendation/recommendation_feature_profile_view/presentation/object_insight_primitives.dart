import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/interactive_intersection_text.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_icon_resolver.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 「我的交集」预览模块共享展示积木（我的主页 / 他人主页 / 实体主页 / 圈子主页同壳同 token）。
///
/// 归属 components/object_page，跨 UI 模块复用；从 ui/user 下沉以修复 components→ui 反向依赖。
/// 类名保留 `ProfileInsight*` 历史命名以零改动收敛；语义上为通用对象交集预览积木。

String profileIntersectionSourceRef(IntersectionReason reason) {
  final resolved = resolvedIntersectionReasonKind(reason).trim();
  if (resolved.isNotEmpty) {
    return resolved;
  }
  return reason.source.trim();
}

class ProfileInsightSectionCard extends StatelessWidget {
  const ProfileInsightSectionCard({
    super.key,
    required this.title,
    required this.child,
    this.actionLabel,
    this.onAction,
    this.topPadding = false,
  });

  final String title;
  final String? actionLabel;
  final Widget child;
  final VoidCallback? onAction;
  final bool topPadding;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final separator = AppColors.iosSeparator(context);
    final border = separator.withValues(alpha: isDark ? 0.14 : 0.07);
    final shadow = AppColors.black.withValues(alpha: isDark ? 0.10 : 0.018);
    return Padding(
      padding: EdgeInsets.only(top: topPadding ? AppSpacing.interGroupSm : 0),
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: AppColors.iosProfileSurface(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(color: border, width: AppSpacing.hairline),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: shadow,
              blurRadius: AppSpacing.fourteen,
              offset: const Offset(0, 5),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerSm,
                AppSpacing.containerXs,
                AppSpacing.intraGroupXs,
                AppSpacing.intraGroupXs,
              ),
              child: Row(
                children: <Widget>[
                  Container(
                    width: AppSpacing.xs / 2,
                    height: AppSpacing.iconSmall,
                    decoration: BoxDecoration(
                      color:
                          (isDark
                                  ? AppColors.profileSloganAccentDark
                                  : AppColors.profileSloganAccentLight)
                              .withValues(alpha: isDark ? 0.80 : 0.56),
                      borderRadius: BorderRadius.circular(AppSpacing.xs / 2),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Expanded(
                    child: Text(
                      title,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.regular,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const ProfileInsightDivider(),
            child,
            if ((actionLabel ?? '').trim().isNotEmpty &&
                onAction != null) ...<Widget>[
              const ProfileInsightDivider(),
              ProfileInsightFooterAction(
                label: actionLabel!.trim(),
                onTap: onAction,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class ProfileInsightFooterAction extends StatelessWidget {
  const ProfileInsightFooterAction({
    super.key,
    required this.label,
    this.onTap,
  });

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final surface = isDark
        ? AppColors.iosSecondaryFill(context)
        : AppColors.iosSystemBackground(context);
    final ink = AppColors.iosLabel(context);
    final ornament = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.26 : 0.18);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.buttonHeightMd,
      ),
      onPressed: onTap,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Expanded(child: _ProfileInsightFooterLine(color: ornament)),
          SizedBox(width: AppSpacing.intraGroupSm),
          DecoratedBox(
            decoration: BoxDecoration(
              color: surface.withValues(alpha: isDark ? 0.32 : 0.68),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              border: Border.all(color: ornament, width: AppSpacing.hairline),
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.regular,
                      color: ink,
                    ),
                  ),
                ],
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: _ProfileInsightFooterLine(color: ornament, reverse: true),
          ),
        ],
      ),
    );
  }
}

class _ProfileInsightFooterLine extends StatelessWidget {
  const _ProfileInsightFooterLine({required this.color, this.reverse = false});

  final Color color;
  final bool reverse;

  @override
  Widget build(BuildContext context) {
    final dot = Container(
      width: AppSpacing.xs,
      height: AppSpacing.xs,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
    final line = Expanded(
      child: Container(height: AppSpacing.hairline, color: color),
    );
    return Row(
      children: reverse
          ? <Widget>[dot, SizedBox(width: AppSpacing.intraGroupXs), line]
          : <Widget>[line, SizedBox(width: AppSpacing.intraGroupXs), dot],
    );
  }
}

class ProfileIntersectionPreviewRow extends StatelessWidget {
  const ProfileIntersectionPreviewRow({
    super.key,
    required this.reason,
    required this.onTap,
    required this.onSpanTap,
  });

  final IntersectionReason reason;
  final VoidCallback onTap;
  final void Function(IntersectionTextSpan span) onSpanTap;

  @override
  Widget build(BuildContext context) {
    final displayReason = displayReadyIntersectionReason(reason);
    if (displayReason == null) {
      return const SizedBox.shrink();
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.containerSm,
        ),
        child: Row(
          children: <Widget>[
            IntersectionTypeIcon(
              iconKey: displayReason.iconKey,
              sourceRef: profileIntersectionSourceRef(displayReason),
              dimension: displayReason.dimension,
              tone: displayReason.tone,
              assetUrl: displayReason.typeVisual?.imageUrl ?? '',
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: InteractiveIntersectionText(
                spans: displayReason.primarySpans,
                fallbackText: displayReason.primaryText,
                onSpanTap: onSpanTap,
                onFallbackTap: onTap,
                accentFontWeight: AppTypography.regular,
                baseStyle: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  height: AppSpacing.textLineHeightFootnote,
                  fontWeight: AppTypography.regular,
                  color: AppColors.iosLabel(context),
                  letterSpacing: -0.08,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ProfileIntersectionEmptyState extends StatelessWidget {
  const ProfileIntersectionEmptyState({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerMd,
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: AppTypography.iosSubheadline,
          height: AppSpacing.textLineHeightFootnote,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class ProfileIntersectionSkeletonList extends StatelessWidget {
  const ProfileIntersectionSkeletonList({super.key});

  @override
  Widget build(BuildContext context) {
    // 行形状：头像位 + 单行短句条；脉动与占位视觉由统一 primitives 承载。
    final row = Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerSm,
      ),
      child: const Row(
        children: <Widget>[
          AppSkeletonCircle(size: AppSpacing.avatarUserSm),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(child: AppSkeletonLine(height: AppSpacing.sm)),
        ],
      ),
    );
    return AppSkeletonShimmer(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (var i = 0; i < 3; i += 1) ...[
            if (i > 0) const ProfileInsightDivider(),
            row,
          ],
        ],
      ),
    );
  }
}

class ProfileInsightDivider extends StatelessWidget {
  const ProfileInsightDivider({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(left: AppSpacing.containerSm * 2),
      child: Container(
        height: AppSpacing.hairline,
        color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
      ),
    );
  }
}
