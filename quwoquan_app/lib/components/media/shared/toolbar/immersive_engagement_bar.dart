import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';

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
        expanded: AppSpacing.buttonHeightLg + AppSpacing.intraGroupXs,
      );

  static double _toolbarHorizontalPadding(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: AppSpacing.containerSm,
        regular: AppSpacing.containerMd,
        expanded: AppSpacing.containerMd,
      );

  static double _avatarRadius(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: AppSpacing.avatarUserSm / 2,
    regular: AppSpacing.avatarUserMd / 2,
    expanded: AppSpacing.avatarUserMd / 2,
  );

  static double _toolbarRailMaxWidth(double availableWidth) {
    if (availableWidth <= 0) return 0;
    return availableWidth;
  }

  static double _outerClusterGapForWidth(double availableWidth) {
    final rawGap = availableWidth * 0.03;
    return rawGap.clamp(AppSpacing.intraGroupMd, AppSpacing.interGroupMd)
        .toDouble();
  }

  static double _authorClusterWidth({
    required double avatarRadius,
    required double currentNameSlotWidth,
    required bool showFollowLane,
  }) {
    final avatarWidth = avatarRadius * 2;
    final followWidth = showFollowLane
        ? AppSpacing.intraGroupXs + _kFollowBtnWidth
        : 0;
    return avatarWidth +
        AppSpacing.intraGroupSm +
        currentNameSlotWidth +
        followWidth;
  }

  static double _actionClusterWidth({
    required double actionCellWidth,
    required double actionGroupGap,
  }) {
    return (actionCellWidth * 3) + (actionGroupGap * 2);
  }

  static int _restNameMaxChars(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: 5,
    regular: 6,
    expanded: 7,
  ).round();

  static int _revealNameMaxChars(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: 4,
        regular: 5,
        expanded: 6,
      ).round();

  static double _actionGroupGapForWidth(double railWidth) {
    final rawGap = railWidth * 0.014;
    return rawGap.clamp(AppSpacing.intraGroupSm, AppSpacing.intraGroupXl)
        .toDouble();
  }

  static double _nameVisibleWidth(
    int charCount,
    TextStyle style, {
    bool includeEllipsis = false,
  }) {
    const sample = '一二三四五六七八九十';
    final text = sample.length >= charCount
        ? sample.substring(0, charCount)
        : sample;
    final painter = TextPainter(
      text: TextSpan(
        text: '$text${includeEllipsis ? '...' : ''}',
        style: style,
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    return painter.width;
  }

  Widget _buildAuthorCluster({
    required String displayName,
    required bool isRevealState,
    required bool showFollowLane,
    required bool isFollowing,
    required ImageProvider? avatarImage,
    required double avatarRadius,
    required double currentNameSlotWidth,
    required double restNameWidth,
    required double restSecondaryWidth,
    required double revealNameWidth,
    required double revealSecondaryWidth,
    required TextStyle restDisplayStyle,
    required TextStyle compressedDisplayStyle,
    required TextStyle secondaryStyle,
    required VoidCallback onUserTap,
    required VoidCallback onFollowTap,
  }) {
    final textDisplayName = displayName.isEmpty
        ? UITextConstants.unknownUser
        : displayName;

    return Row(
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
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedContainer(
              duration: _kTransitionDuration,
              curve: Curves.easeOutCubic,
              width: currentNameSlotWidth,
              child: isRevealState
                  ? ShaderMask(
                      shaderCallback: (bounds) {
                        const fadeWidth = 14.0;
                        final start = bounds.width <= fadeWidth
                            ? 0.0
                            : ((bounds.width - fadeWidth) / bounds.width)
                                .clamp(0.0, 1.0);
                        return LinearGradient(
                          begin: Alignment.centerLeft,
                          end: Alignment.centerRight,
                          stops: [start, 1.0],
                          colors: const [
                            AppColors.white,
                            AppColors.transparent,
                          ],
                        ).createShader(bounds);
                      },
                      blendMode: BlendMode.dstIn,
                      child: _nameColumn(
                        displayName: textDisplayName,
                        displayStyle: compressedDisplayStyle,
                        secondaryStyle: secondaryStyle,
                        primaryMaxWidth: revealNameWidth,
                        secondaryMaxWidth: revealSecondaryWidth,
                        clip: true,
                      ),
                    )
                  : _nameColumn(
                      displayName: textDisplayName,
                      displayStyle: restDisplayStyle,
                      secondaryStyle: secondaryStyle,
                      primaryMaxWidth: restNameWidth,
                      secondaryMaxWidth: restSecondaryWidth,
                      clip: false,
                    ),
            ),
            ClipRect(
              child: AnimatedContainer(
                duration: _kTransitionDuration,
                curve: Curves.easeOutCubic,
                width: showFollowLane
                    ? AppSpacing.intraGroupXs + _kFollowBtnWidth
                    : 0,
                child: Align(
                  alignment: Alignment.centerRight,
                  child: Padding(
                    padding: const EdgeInsets.only(
                      left: AppSpacing.intraGroupXs,
                    ),
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
                              : const Offset(0.24, 0),
                          child: AnimatedOpacity(
                            duration: _kTransitionDuration,
                            curve: Curves.easeOutCubic,
                            opacity: showFollowLane ? 1 : 0,
                            child: GestureDetector(
                              onTap: onFollowTap,
                              behavior: HitTestBehavior.opaque,
                              child: Container(
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
    final isRevealState = showFollowButton;
    final restDisplayStyle = TextStyle(
      color: AppColors.worksTitle,
      fontSize: AppTypography.sm,
      fontWeight: AppTypography.medium,
    );
    final compressedDisplayStyle = TextStyle(
      color: AppColors.worksTitle,
      fontSize: AppTypography.xxs,
      fontWeight: AppTypography.medium,
    );
    final secondaryStyle = TextStyle(
      color: AppColors.worksBodyText.withValues(alpha: 0.72),
      fontSize: AppTypography.xxs,
      fontWeight: AppTypography.medium,
    );
    final restNameWidth = _nameVisibleWidth(
      _restNameMaxChars(context),
      restDisplayStyle,
      includeEllipsis: true,
    );
    final restSecondaryWidth = _nameVisibleWidth(
      _restNameMaxChars(context),
      secondaryStyle,
      includeEllipsis: true,
    );
    final revealNameWidth = _nameVisibleWidth(
      _revealNameMaxChars(context),
      compressedDisplayStyle,
    );
    final revealSecondaryWidth = _nameVisibleWidth(
      _revealNameMaxChars(context),
      secondaryStyle,
    );
    final restNameSlotWidth = restNameWidth > restSecondaryWidth
        ? restNameWidth
        : restSecondaryWidth;
    final revealNameSlotWidth = revealNameWidth > revealSecondaryWidth
        ? revealNameWidth
        : revealSecondaryWidth;
    final actionCellWidth = _actionCellWidth(context);
    final horizontalPadding = _toolbarHorizontalPadding(context);
    final avatarRadius = _avatarRadius(context);
    final avatarImage = avatarUrl.isNotEmpty ? NetworkImage(avatarUrl) : null;
    final showFollowLane = showFollowButton;
    final currentNameSlotWidth = showFollowLane
        ? revealNameSlotWidth
        : restNameSlotWidth;
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
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              topPadding,
              horizontalPadding,
              bottomPadding,
            ),
            color: AppColors.worksBackground.withValues(alpha: 0.88),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final outerGap = _outerClusterGapForWidth(
                  constraints.maxWidth,
                );
                final actionGroupGap = _actionGroupGapForWidth(
                  constraints.maxWidth,
                );
                final authorClusterWidth = _authorClusterWidth(
                  avatarRadius: avatarRadius,
                  currentNameSlotWidth: currentNameSlotWidth,
                  showFollowLane: showFollowLane,
                );
                final actionClusterWidth = _actionClusterWidth(
                  actionCellWidth: actionCellWidth,
                  actionGroupGap: actionGroupGap,
                );
                final railWidth = _toolbarRailMaxWidth(
                  constraints.maxWidth,
                )
                    .clamp(
                      0.0,
                      authorClusterWidth +
                          outerGap +
                          actionClusterWidth,
                    )
                    .toDouble();

                final content = isSelfPost
                    ? SizedBox(
                        height: AppSpacing.iconButtonMinSizeSm,
                        child: _buildSelfActionRow(),
                      )
                    : SizedBox(
                        width: railWidth,
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            Align(
                              alignment: Alignment.centerLeft,
                              child: _buildAuthorCluster(
                                displayName: displayName,
                                isRevealState: isRevealState,
                                showFollowLane: showFollowLane,
                                isFollowing: isFollowing,
                                avatarImage: avatarImage,
                                avatarRadius: avatarRadius,
                                currentNameSlotWidth: currentNameSlotWidth,
                                restNameWidth: restNameWidth,
                                restSecondaryWidth: restSecondaryWidth,
                                revealNameWidth: revealNameWidth,
                                revealSecondaryWidth: revealSecondaryWidth,
                                restDisplayStyle: restDisplayStyle,
                                compressedDisplayStyle:
                                    compressedDisplayStyle,
                                secondaryStyle: secondaryStyle,
                                onUserTap: onUserTap,
                                onFollowTap: onFollowTap,
                              ),
                            ),
                            Align(
                              alignment: Alignment.centerRight,
                              child: _buildActionCluster(
                                isLiked: isLiked,
                                likeCount: likeCount,
                                shareCount: shareCount,
                                commentCount: commentCount,
                                actionCellWidth: actionCellWidth,
                                actionGroupGap: actionGroupGap,
                                onLikeTap: onLikeTap,
                                onShareTap: onShareTap,
                                onCommentTap: onCommentTap,
                              ),
                            ),
                          ],
                        ),
                      );
                return Center(
                  child: ConstrainedBox(
                    constraints: BoxConstraints(maxWidth: railWidth),
                    child: content,
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _nameColumn({
    required String displayName,
    required TextStyle displayStyle,
    required TextStyle secondaryStyle,
    required double primaryMaxWidth,
    required double secondaryMaxWidth,
    required bool clip,
  }) {
    final overflow = clip ? TextOverflow.clip : TextOverflow.ellipsis;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedDefaultTextStyle(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          style: displayStyle,
          child: SizedBox(
            width: primaryMaxWidth,
            child: Text(displayName, maxLines: 1, overflow: overflow),
          ),
        ),
        if (circleName.isNotEmpty) ...[
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          AnimatedDefaultTextStyle(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            style: secondaryStyle,
            child: GestureDetector(
              onTap: onCircleTap,
              behavior: HitTestBehavior.opaque,
              child: SizedBox(
                width: secondaryMaxWidth,
                child: Text(circleName, maxLines: 1, overflow: overflow),
              ),
            ),
          ),
        ],
      ],
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
