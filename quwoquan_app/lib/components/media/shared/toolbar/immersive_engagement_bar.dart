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
  final bool showFollowButton;

  final VoidCallback onUserTap;
  final VoidCallback onCircleTap;
  final VoidCallback onFollowTap;
  final VoidCallback onLikeTap;
  final VoidCallback? onCommentTap;
  final VoidCallback? onShareTap;
  final VoidCallback? onRevealSystemNav;

  static const double _kFollowBtnWidth = AppSpacing.followButtonWidthCompact;

  static double _actionGap(BuildContext ctx) => AppSpacing.responsiveValue(
        ctx,
        compact: AppSpacing.intraGroupXl,
        regular: AppSpacing.interGroupLg,
        expanded: AppSpacing.interGroupXl,
      );

  static double _interGroupGap(BuildContext ctx) => AppSpacing.responsiveValue(
        ctx,
        compact: AppSpacing.interGroupXl,
        regular: AppSpacing.interGroupXl,
        expanded: AppSpacing.interGroupXl,
      );

  static double _nameVisibleWidth(BuildContext context, int charCount, TextStyle style) {
    const sample = '一二三四五六七八九十';
    final text = sample.length >= charCount ? sample.substring(0, charCount) : sample;
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout();
    return painter.width;
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    final actionGap = _actionGap(context);
    final interGroupGap = _interGroupGap(context);
    const compressText = true;
    final textDisplayName = displayName.isEmpty ? UITextConstants.unknownUser : displayName;

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
              AppSpacing.intraGroupSm,
              AppSpacing.containerMd,
              AppSpacing.containerMd + bottomInset,
            ),
            color: AppColors.worksBackground.withValues(alpha: 0.88),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                GestureDetector(
                  onTap: onUserTap,
                  behavior: HitTestBehavior.opaque,
                  child: CircleAvatar(
                    radius: AppSpacing.avatarUserMd * 0.5,
                    backgroundImage: avatarUrl.isNotEmpty ? NetworkImage(avatarUrl) : null,
                    onBackgroundImageError: (_, stackTrace) {},
                    backgroundColor: AppColors.worksCaption,
                  ),
                ),
                const SizedBox(width: AppSpacing.intraGroupSm),
                Flexible(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Flexible(
                        child: _nameColumn(
                          context: context,
                          displayName: textDisplayName,
                          compressText: compressText,
                          clip: true,
                          fixedMaxChars: 4,
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.only(left: AppSpacing.intraGroupSm),
                        child: SizedBox(
                          width: _kFollowBtnWidth,
                          height: AppSpacing.buttonHeightXs,
                          child: IgnorePointer(
                            ignoring: !showFollowButton,
                            child: Opacity(
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
                                        ? AppColors.followingButtonOnDark
                                        : AppColors.worksAccent,
                                    borderRadius:
                                        BorderRadius.circular(AppSpacing.circularBorderRadius),
                                  ),
                                  child: Text(
                                    isFollowing ? UITextConstants.following : UITextConstants.follow,
                                    maxLines: 1,
                                    overflow: TextOverflow.fade,
                                    softWrap: false,
                                    style: TextStyle(
                                      color: isFollowing
                                          ? AppColors.worksBodyText.withValues(alpha: 0.72)
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
                    ],
                  ),
                ),
                SizedBox(width: interGroupGap),
                Spacer(),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _action(
                      icon: Icon(
                        isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
                        color: isLiked ? AppColors.worksLike : AppColors.worksTitle,
                        size: AppSpacing.iconMedium,
                      ),
                      label: formatCompactActionCount(likeCount),
                      onTap: onLikeTap,
                    ),
                    SizedBox(width: actionGap),
                    _action(
                      icon: Icon(
                        CupertinoIcons.arrowshape_turn_up_right,
                        color: AppColors.worksTitle,
                        size: AppSpacing.iconMedium,
                      ),
                      label: formatCompactActionCount(shareCount),
                      onTap: onShareTap,
                    ),
                    SizedBox(width: actionGap),
                    _action(
                      icon: Icon(
                        CupertinoIcons.chat_bubble,
                        color: AppColors.worksTitle,
                        size: AppSpacing.iconMedium,
                      ),
                      label: formatCompactActionCount(commentCount),
                      onTap: onCommentTap,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _nameColumn({
    required BuildContext context,
    required String displayName,
    required bool compressText,
    required bool clip,
    required int fixedMaxChars,
  }) {
    final displayStyle = TextStyle(
      color: AppColors.worksTitle,
      fontSize: compressText ? AppTypography.sm : AppTypography.base,
      fontWeight: AppTypography.bold,
    );
    final maxNameWidth = _nameVisibleWidth(context, fixedMaxChars, displayStyle);
    final overflow = clip ? TextOverflow.clip : TextOverflow.ellipsis;
    return ConstrainedBox(
      constraints: BoxConstraints(maxWidth: maxNameWidth),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedDefaultTextStyle(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            style: displayStyle,
            child: Text(displayName, maxLines: 1, overflow: overflow),
          ),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          AnimatedDefaultTextStyle(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            style: TextStyle(
              color: AppColors.worksBodyText.withValues(alpha: 0.72),
              fontSize: compressText ? AppTypography.xxs : AppTypography.xs,
              fontWeight: AppTypography.medium,
            ),
            child: GestureDetector(
              onTap: onCircleTap,
              behavior: HitTestBehavior.opaque,
              child: Text(circleName, maxLines: 1, overflow: overflow),
            ),
          ),
        ],
      ),
    );
  }

  Widget _action({
    required Widget icon,
    required String label,
    VoidCallback? onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        constraints: const BoxConstraints(minWidth: AppSpacing.minInteractiveSize),
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
    );
  }
}
