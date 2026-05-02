import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';

/// 侵入式浏览器底部工具栏。
///
/// 布局：`[Avatar][intraSm][作者名区][关注槽位]` + `clusterGap` + `弹性区` + `[赞转评]`。
///
/// **rail**：作者组左锚、动作组右锚；`mediaStage` 与图片/视频全宽对齐；
/// `textStage`/`feedRail` 可走 `feedMaxContentWidth`。
///
/// **作者名**：最多 12 个 Unicode 字符展示；槽位按断点固定为 4/5/6 个中文字符宽度。
/// 单行优先（`sm`），超出则两行紧凑（`xs` + 紧凑行高），必要时末尾省略。
///
/// **关注**：固定接在作者名槽位之后；显隐用透明度与滑入动画，不移动右侧动作组。
class ImmersiveEngagementBar extends StatelessWidget {
  const ImmersiveEngagementBar({
    super.key,
    required this.avatarUrl,
    required this.displayName,
    required this.circleName,
    required this.likeCount,
    required this.shareCount,
    required this.commentCount,
    required this.isLiked,
    required this.isFollowing,
    required this.onUserTap,
    required this.onCircleTap,
    required this.onFollowTap,
    required this.onLikeTap,
    this.onCommentTap,
    this.onShareTap,
    this.onRevealSystemNav,
    this.isSelfPost = false,
    this.showFollowButton = true,
    this.layoutSpec = ImmersiveViewerStageLayoutSpec.feedRail,
  });

  final String avatarUrl;
  final String displayName;
  final String circleName;
  final int likeCount;
  final int shareCount;
  final int commentCount;
  final bool isLiked;
  final bool isFollowing;
  final bool isSelfPost;
  final bool showFollowButton;
  final ImmersiveViewerStageLayoutSpec layoutSpec;

  final VoidCallback onUserTap;
  final VoidCallback onCircleTap;
  final VoidCallback onFollowTap;
  final VoidCallback onLikeTap;
  final VoidCallback? onCommentTap;
  final VoidCallback? onShareTap;
  final VoidCallback? onRevealSystemNav;

  static const double _kFollowBtnWidth = AppSpacing.followButtonWidthCompact;

  /// 工具栏预留高度（含内边距），供宿主布局使用。
  static const double preferredReservedHeight = 108;
  static const Duration _kTransitionDuration = Duration(milliseconds: 260);

  static double _actionCellWidth(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: AppSpacing.iconButtonMinSizeSm,
        regular: AppSpacing.buttonHeightLg,
        expanded: AppSpacing.buttonHeightLg,
      );

  static double _avatarRadius(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: AppSpacing.avatarUserSm / 2,
    regular: AppSpacing.avatarUserMd / 2,
    expanded: AppSpacing.avatarUserMd / 2,
  );

  /// 组间距：档位常量。不参与任何 LayoutBuilder 的弹性计算。
  static double _clusterGapForTier(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: AppSpacing.interGroupSm,
        regular: AppSpacing.interGroupMd,
        expanded: AppSpacing.interGroupMd,
      );

  /// 动作组内间距：档位常量。
  static double _actionInnerGapForTier(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: AppSpacing.intraGroupSm,
        regular: AppSpacing.intraGroupMd,
        expanded: AppSpacing.intraGroupMd,
      );

  /// 组间距降级下限：当自然宽度超过 track 宽度时，允许把组间距压到这个值。
  static double _clusterGapFloorForTier(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: AppSpacing.interGroupSm,
        regular: AppSpacing.interGroupSm,
        expanded: AppSpacing.interGroupSm,
      );

  static double _actionClusterWidth({
    required double actionCellWidth,
    required double actionGroupGap,
  }) {
    return (actionCellWidth * 3) + (actionGroupGap * 2);
  }

  static const int _kAuthorDisplayMaxChars = 12;

  static int _authorNameSlotCharsForViewport(double viewportWidth) {
    if (viewportWidth < AppSpacing.compactBreakpoint) return 4;
    if (viewportWidth < AppSpacing.expandedBreakpoint) return 5;
    return 6;
  }

  static double _nameSlotWidthForChars({
    required int charCount,
    required TextStyle style,
  }) {
    const sample = '一二三四五六七八九十';
    final text = sample.substring(0, charCount);
    final tp = TextPainter(
      text: TextSpan(text: text, style: style),
      maxLines: 1,
      textDirection: TextDirection.ltr,
    )..layout();
    return tp.width;
  }

  /// 作者展示文案：空 -> unknownUser；非空最多 12 个 Unicode 字符。
  static String _normalizeAuthorDisplay(String raw) {
    final t = raw.trim();
    if (t.isEmpty) return UITextConstants.unknownUser;
    final runes = t.runes.toList();
    if (runes.length <= _kAuthorDisplayMaxChars) {
      return String.fromCharCodes(runes);
    }
    return String.fromCharCodes(runes.take(_kAuthorDisplayMaxChars));
  }

  static bool _textFitsSingleLine({
    required String text,
    required double maxWidth,
    required TextStyle style,
  }) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: style),
      maxLines: 1,
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: maxWidth);
    return !tp.didExceedMaxLines;
  }

  Widget _buildAuthorCluster({
    required String displayText,
    required bool showFollowLane,
    required bool isFollowing,
    required ImageProvider? avatarImage,
    required double avatarRadius,
    required double nameSlotWidth,
    required double followLaneWidth,
    required bool useTwoLines,
    required bool shaderTrailingFade,
    required TextStyle singleLineStyle,
    required TextStyle twoLineStyle,
    required TextStyle secondaryStyle,
    required VoidCallback onUserTap,
    required VoidCallback onFollowTap,
  }) {
    final overflow = useTwoLines ? TextOverflow.ellipsis : TextOverflow.fade;
    final nameStyle = useTwoLines
        ? twoLineStyle.copyWith(height: AppSpacing.textLineHeightDense)
        : singleLineStyle;

    Widget nameWidget = Text(
      displayText,
      maxLines: useTwoLines ? 2 : 1,
      overflow: overflow,
      softWrap: true,
      style: nameStyle,
    );

    if (shaderTrailingFade && !useTwoLines) {
      nameWidget = ShaderMask(
        shaderCallback: (bounds) {
          const fadeWidth = 14.0;
          final start = bounds.width <= fadeWidth
              ? 0.0
              : ((bounds.width - fadeWidth) / bounds.width).clamp(0.0, 1.0);
          return LinearGradient(
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
            stops: [start, 1.0],
            colors: const [AppColors.white, AppColors.transparent],
          ).createShader(bounds);
        },
        blendMode: BlendMode.dstIn,
        child: nameWidget,
      );
    }

    final nameColumn = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          key: const ValueKey('immersive-author-name-slot'),
          width: nameSlotWidth,
          child: nameWidget,
        ),
        if (circleName.isNotEmpty) ...[
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          GestureDetector(
            onTap: onCircleTap,
            behavior: HitTestBehavior.opaque,
            child: SizedBox(
              width: nameSlotWidth,
              child: Text(
                circleName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: secondaryStyle,
              ),
            ),
          ),
        ],
      ],
    );

    return Row(
      key: const ValueKey('immersive-author-group'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        GestureDetector(
          onTap: onUserTap,
          behavior: HitTestBehavior.opaque,
          child: CircleAvatar(
            radius: avatarRadius,
            backgroundImage: avatarImage,
            onBackgroundImageError: avatarImage == null
                ? null
                : (_, stackTrace) {},
            backgroundColor: AppColors.worksCaption,
            child: avatarImage == null
                ? Icon(Icons.person, color: AppColors.white, size: avatarRadius)
                : null,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(width: nameSlotWidth, child: nameColumn),
            SizedBox(
              key: const ValueKey('immersive-follow-lane'),
              width: followLaneWidth,
              child: Align(
                alignment: Alignment.centerRight,
                child: Padding(
                  padding: const EdgeInsets.only(left: AppSpacing.intraGroupXs),
                  child: SizedBox(
                    width: _kFollowBtnWidth,
                    height: AppSpacing.buttonHeightXs,
                    child: IgnorePointer(
                      ignoring: !showFollowLane,
                      child: AnimatedSlide(
                        duration: _kTransitionDuration,
                        curve: Curves.easeOutCubic,
                        offset: showFollowLane
                            ? Offset.zero
                            : const Offset(0.45, 0),
                        child: AnimatedOpacity(
                          duration: _kTransitionDuration,
                          curve: Curves.easeOutCubic,
                          opacity: showFollowLane ? 1 : 0,
                          child: GestureDetector(
                            onTap: onFollowTap,
                            behavior: HitTestBehavior.opaque,
                            child: Container(
                              key: const ValueKey('immersive-follow-button'),
                              width: _kFollowBtnWidth,
                              height: AppSpacing.buttonHeightXs,
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: isFollowing
                                    ? AppColors.followingButtonOnDark
                                    : AppColors.worksAccent,
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.circularBorderRadius,
                                ),
                              ),
                              child: Text(
                                isFollowing
                                    ? UITextConstants.following
                                    : UITextConstants.follow,
                                maxLines: 1,
                                overflow: TextOverflow.fade,
                                softWrap: false,
                                style: TextStyle(
                                  color: isFollowing
                                      ? AppColors.worksBodyText.withValues(
                                          alpha: 0.72,
                                        )
                                      : AppColors.white,
                                  fontSize: AppTypography.xs,
                                  fontWeight: AppTypography.semiBold,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildActionCluster({
    required bool isLiked,
    required int likeCount,
    required int shareCount,
    required int commentCount,
    required double actionCellWidth,
    required double actionGroupGap,
    required VoidCallback onLikeTap,
    required VoidCallback? onShareTap,
    required VoidCallback? onCommentTap,
  }) {
    return Row(
      key: const ValueKey('immersive-actions-group'),
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: actionCellWidth,
          child: _action(
            icon: Icon(
              isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
              color: isLiked ? AppColors.worksLike : AppColors.worksTitle,
              size: AppSpacing.iconMedium,
            ),
            label: formatCompactActionCount(likeCount),
            onTap: onLikeTap,
            alignment: Alignment.centerLeft,
          ),
        ),
        SizedBox(width: actionGroupGap),
        SizedBox(
          width: actionCellWidth,
          child: _action(
            icon: Icon(
              CupertinoIcons.arrowshape_turn_up_right,
              color: AppColors.worksTitle,
              size: AppSpacing.iconMedium,
            ),
            label: formatCompactActionCount(shareCount),
            onTap: onShareTap,
            alignment: Alignment.center,
          ),
        ),
        SizedBox(width: actionGroupGap),
        SizedBox(
          width: actionCellWidth,
          child: _action(
            icon: Icon(
              CupertinoIcons.chat_bubble,
              color: AppColors.worksTitle,
              size: AppSpacing.iconMedium,
            ),
            label: formatCompactActionCount(commentCount),
            onTap: onCommentTap,
            alignment: Alignment.centerRight,
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    final singleLineStyle = TextStyle(
      color: AppColors.worksTitle,
      fontSize: AppTypography.sm,
      fontWeight: AppTypography.medium,
    );
    final twoLineStyle = TextStyle(
      color: AppColors.worksTitle,
      fontSize: AppTypography.xs,
      fontWeight: AppTypography.medium,
    );
    final secondaryStyle = TextStyle(
      color: AppColors.worksBodyText.withValues(alpha: 0.72),
      fontSize: AppTypography.xxs,
      fontWeight: AppTypography.medium,
    );
    final actionCellWidth = _actionCellWidth(context);
    final avatarRadius = _avatarRadius(context);
    final avatarImage = avatarUrl.isNotEmpty ? NetworkImage(avatarUrl) : null;
    final showFollowLane = showFollowButton;
    final normalizedAuthor = _normalizeAuthorDisplay(displayName);
    final topPadding = isSelfPost ? AppSpacing.xs : AppSpacing.intraGroupSm;
    final bottomPadding = isSelfPost
        ? bottomInset + AppSpacing.xs
        : AppSpacing.containerMd + bottomInset;

    return GestureDetector(
      onVerticalDragUpdate: (details) {
        if (details.delta.dy < -4) onRevealSystemNav?.call();
      },
      child: ClipRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
          child: Container(
            padding: EdgeInsets.only(top: topPadding, bottom: bottomPadding),
            color: AppColors.worksBackground.withValues(alpha: 0.88),
            child: LayoutBuilder(
              builder: (context, constraints) {
                // Track 宽度 = rail。作者左锚 rail 左缘、动作右锚 rail 右缘。
                final rail = ImmersiveViewerLayout.railWidthForViewport(
                  context,
                  constraints.maxWidth,
                  layoutSpec: layoutSpec,
                );
                final trackWidth = rail;

                // 作者名槽位按断点固定，短名也保留槽位，关注按钮不跟随文本长度移动。
                final followLaneWidth =
                    AppSpacing.intraGroupXs + _kFollowBtnWidth;
                final avatarWidth = avatarRadius * 2;
                final fixedAuthorBeforeName =
                    avatarWidth + AppSpacing.intraGroupSm;

                final clusterGapNatural = _clusterGapForTier(context);
                final actionInnerGap = _actionInnerGapForTier(context);
                final actionClusterWidth = _actionClusterWidth(
                  actionCellWidth: actionCellWidth,
                  actionGroupGap: actionInnerGap,
                );

                final visibleFollowLaneWidth = showFollowLane
                    ? followLaneWidth
                    : 0.0;
                final slotChars = _authorNameSlotCharsForViewport(
                  MediaQuery.sizeOf(context).width,
                );
                final naturalNameSlot = _nameSlotWidthForChars(
                  charCount: slotChars,
                  style: singleLineStyle,
                );
                final maxNameSlot = math.max(
                  0.0,
                  trackWidth -
                      clusterGapNatural -
                      actionClusterWidth -
                      fixedAuthorBeforeName -
                      visibleFollowLaneWidth,
                );

                double effectiveGap = clusterGapNatural;
                double effectiveName = math.min(naturalNameSlot, maxNameSlot);
                final naturalTotalWidth =
                    fixedAuthorBeforeName +
                    effectiveName +
                    visibleFollowLaneWidth +
                    clusterGapNatural +
                    actionClusterWidth;

                // 空间不足：先压组间距，再收窄作者名区。
                if (naturalTotalWidth > trackWidth) {
                  var overflow = naturalTotalWidth - trackWidth;
                  final gapFloor = _clusterGapFloorForTier(context);
                  final gapShrinkable = math.max(
                    0.0,
                    clusterGapNatural - gapFloor,
                  );
                  final useGap = math.min(overflow, gapShrinkable);
                  effectiveGap = clusterGapNatural - useGap;
                  overflow -= useGap;
                  if (overflow > 0) {
                    effectiveName = math.max(0.0, effectiveName - overflow);
                  }
                }

                final fitsSingle =
                    effectiveName > 0 &&
                    ImmersiveEngagementBar._textFitsSingleLine(
                      text: normalizedAuthor,
                      maxWidth: effectiveName,
                      style: singleLineStyle,
                    );
                final useTwoLines = !fitsSingle;
                final shaderFade = showFollowButton && !useTwoLines;

                final content = isSelfPost
                    ? SizedBox(
                        width: double.infinity,
                        height: AppSpacing.iconButtonMinSizeSm,
                        child: _buildSelfActionRow(),
                      )
                    : Row(
                        children: [
                          SizedBox(
                            width:
                                fixedAuthorBeforeName +
                                effectiveName +
                                visibleFollowLaneWidth,
                            child: _buildAuthorCluster(
                              displayText: normalizedAuthor,
                              showFollowLane: showFollowLane,
                              isFollowing: isFollowing,
                              avatarImage: avatarImage,
                              avatarRadius: avatarRadius,
                              nameSlotWidth: effectiveName,
                              followLaneWidth: visibleFollowLaneWidth,
                              useTwoLines: useTwoLines,
                              shaderTrailingFade: shaderFade,
                              singleLineStyle: singleLineStyle,
                              twoLineStyle: twoLineStyle,
                              secondaryStyle: secondaryStyle,
                              onUserTap: onUserTap,
                              onFollowTap: onFollowTap,
                            ),
                          ),
                          SizedBox(width: effectiveGap),
                          const Expanded(child: SizedBox.shrink()),
                          SizedBox(
                            width: actionClusterWidth,
                            child: _buildActionCluster(
                              isLiked: isLiked,
                              likeCount: likeCount,
                              shareCount: shareCount,
                              commentCount: commentCount,
                              actionCellWidth: actionCellWidth,
                              actionGroupGap: actionInnerGap,
                              onLikeTap: onLikeTap,
                              onShareTap: onShareTap,
                              onCommentTap: onCommentTap,
                            ),
                          ),
                        ],
                      );

                final horizontalInset = ImmersiveViewerLayout.horizontalPadding(
                  context,
                  layoutSpec: layoutSpec,
                );
                return Padding(
                  padding: EdgeInsets.symmetric(horizontal: horizontalInset),
                  child: Align(
                    alignment: Alignment.center,
                    child: SizedBox(
                      key: const ValueKey('immersive-engagement-rail'),
                      width: trackWidth,
                      child: content,
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSelfActionRow() {
    return Row(
      key: const ValueKey('immersive-self-actions-group'),
      children: [
        Expanded(
          child: _compactAction(
            icon: Icon(
              isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
              color: isLiked ? AppColors.worksLike : AppColors.worksTitle,
              size: AppSpacing.iconMedium,
            ),
            label: formatCompactActionCount(likeCount),
            onTap: onLikeTap,
          ),
        ),
        Expanded(
          child: _compactAction(
            icon: Icon(
              CupertinoIcons.arrowshape_turn_up_right,
              color: AppColors.worksTitle,
              size: AppSpacing.iconMedium,
            ),
            label: formatCompactActionCount(shareCount),
            onTap: onShareTap,
          ),
        ),
        Expanded(
          child: _compactAction(
            icon: Icon(
              CupertinoIcons.chat_bubble,
              color: AppColors.worksTitle,
              size: AppSpacing.iconMedium,
            ),
            label: formatCompactActionCount(commentCount),
            onTap: onCommentTap,
          ),
        ),
      ],
    );
  }

  Widget _compactAction({
    required Widget icon,
    required String label,
    VoidCallback? onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: double.infinity,
        height: AppSpacing.iconButtonMinSizeSm,
        child: Center(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              icon,
              SizedBox(width: AppSpacing.intraGroupXs),
              Text(
                label,
                style: TextStyle(
                  color: AppColors.worksBodyText,
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                  height: AppSpacing.one,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _action({
    required Widget icon,
    required String label,
    required Alignment alignment,
    VoidCallback? onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: double.infinity,
        child: Align(
          alignment: alignment,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              icon,
              SizedBox(height: AppSpacing.intraGroupXs / 2),
              Text(
                label,
                style: TextStyle(
                  color: AppColors.worksBodyText,
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
