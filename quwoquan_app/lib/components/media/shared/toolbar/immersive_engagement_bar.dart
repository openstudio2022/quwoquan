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
  static const Duration _kTransitionDuration = Duration(milliseconds: 260);
  static double _actionCellWidth(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: 44.0,
        regular: 52.0,
        expanded: 60.0,
      );

  static double _crossGroupGap(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: AppSpacing.intraGroupSm,
    regular: AppSpacing.intraGroupMd,
    expanded: AppSpacing.intraGroupLg,
  );

  static int _restNameMaxChars(BuildContext ctx) => AppSpacing.responsiveValue(
    ctx,
    compact: 5,
    regular: 6,
    expanded: 7,
  ).round();

  static int _revealNameMaxChars(BuildContext ctx) =>
      AppSpacing.responsiveValue(
        ctx,
        compact: 3,
        regular: 3,
        expanded: 3,
      ).round();

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

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    final textDisplayName = displayName.isEmpty
        ? UITextConstants.unknownUser
        : displayName;
    final isRevealState = showFollowButton;
    final restDisplayStyle = TextStyle(
      color: AppColors.worksTitle,
      fontSize: AppTypography.sm,
      fontWeight: AppTypography.bold,
    );
    final compressedDisplayStyle = TextStyle(
      color: AppColors.worksTitle,
      fontSize: AppTypography.xxs,
      fontWeight: AppTypography.bold,
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
    final crossGroupGap = _crossGroupGap(context);
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
              AppSpacing.containerMd,
              topPadding,
              AppSpacing.containerMd,
              bottomPadding,
            ),
            color: AppColors.worksBackground.withValues(alpha: 0.88),
            child: isSelfPost
                ? SizedBox(
                    height: AppSpacing.iconButtonMinSizeSm,
                    child: _buildSelfActionRow(),
                  )
                : Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      GestureDetector(
                        onTap: onUserTap,
                        behavior: HitTestBehavior.opaque,
                        child: CircleAvatar(
                          radius: AppSpacing.avatarUserMd * 0.5,
                          backgroundImage: avatarImage,
                          onBackgroundImageError: avatarImage == null
                              ? null
                              : (_, stackTrace) {},
                          backgroundColor: AppColors.worksCaption,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.intraGroupSm),
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
                                          : ((bounds.width - fadeWidth) /
                                                    bounds.width)
                                                .clamp(0.0, 1.0);
                                      return LinearGradient(
                                        begin: Alignment.centerLeft,
                                        end: Alignment.centerRight,
                                        stops: [start, 1.0],
                                        colors: const [
                                          Colors.white,
                                          Colors.transparent,
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
                                  ? AppSpacing.intraGroupSm + _kFollowBtnWidth
                                  : 0,
                              child: Align(
                                alignment: Alignment.centerRight,
                                child: Padding(
                                  padding: const EdgeInsets.only(
                                    left: AppSpacing.intraGroupSm,
                                  ),
                                  child: SizedBox(
                                    width: _kFollowBtnWidth,
                                    height: AppSpacing.buttonHeightXs,
                                    child: IgnorePointer(
                                      ignoring: !showFollowButton,
                                      child: AnimatedSlide(
                                        duration: _kTransitionDuration,
                                        curve: Curves.easeOutCubic,
                                        offset: showFollowButton
                                            ? Offset.zero
                                            : const Offset(0.24, 0),
                                        child: AnimatedOpacity(
                                          duration: _kTransitionDuration,
                                          curve: Curves.easeOutCubic,
                                          opacity: showFollowButton ? 1 : 0,
                                          child: GestureDetector(
                                            onTap: onFollowTap,
                                            behavior: HitTestBehavior.opaque,
                                            child: Container(
                                              width: _kFollowBtnWidth,
                                              height: AppSpacing.buttonHeightXs,
                                              alignment: Alignment.center,
                                              decoration: BoxDecoration(
                                                color: isFollowing
                                                    ? AppColors
                                                          .followingButtonOnDark
                                                    : AppColors.worksAccent,
                                                borderRadius:
                                                    BorderRadius.circular(
                                                      AppSpacing
                                                          .circularBorderRadius,
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
                                                      ? AppColors.worksBodyText
                                                            .withValues(
                                                              alpha: 0.72,
                                                            )
                                                      : AppColors.white,
                                                  fontSize: AppTypography.xs,
                                                  fontWeight:
                                                      AppTypography.semiBold,
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
                      SizedBox(width: crossGroupGap),
                      Expanded(
                        child: LayoutBuilder(
                          builder: (context, constraints) {
                            final actionGroupWidth = (actionCellWidth * 3)
                                .clamp(0.0, constraints.maxWidth);
                            final resolvedCellWidth = actionGroupWidth / 3;

                            return Align(
                              alignment: Alignment.centerRight,
                              child: SizedBox(
                                key: const ValueKey('immersive-actions-group'),
                                width: actionGroupWidth,
                                child: Row(
                                  children: [
                                    SizedBox(
                                      width: resolvedCellWidth,
                                      child: _action(
                                        icon: Icon(
                                          isLiked
                                              ? CupertinoIcons.heart_fill
                                              : CupertinoIcons.heart,
                                          color: isLiked
                                              ? AppColors.worksLike
                                              : AppColors.worksTitle,
                                          size: AppSpacing.iconMedium,
                                        ),
                                        label: formatCompactActionCount(
                                          likeCount,
                                        ),
                                        onTap: onLikeTap,
                                        alignment: Alignment.centerLeft,
                                      ),
                                    ),
                                    SizedBox(
                                      width: resolvedCellWidth,
                                      child: _action(
                                        icon: Icon(
                                          CupertinoIcons
                                              .arrowshape_turn_up_right,
                                          color: AppColors.worksTitle,
                                          size: AppSpacing.iconMedium,
                                        ),
                                        label: formatCompactActionCount(
                                          shareCount,
                                        ),
                                        onTap: onShareTap,
                                        alignment: Alignment.center,
                                      ),
                                    ),
                                    SizedBox(
                                      width: resolvedCellWidth,
                                      child: _action(
                                        icon: Icon(
                                          CupertinoIcons.chat_bubble,
                                          color: AppColors.worksTitle,
                                          size: AppSpacing.iconMedium,
                                        ),
                                        label: formatCompactActionCount(
                                          commentCount,
                                        ),
                                        onTap: onCommentTap,
                                        alignment: Alignment.centerRight,
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
