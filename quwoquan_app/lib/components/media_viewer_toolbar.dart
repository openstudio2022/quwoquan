import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/assistant_avatar.dart';

class MediaViewerTopBar extends StatelessWidget {
  final VoidCallback onBack;
  final String positionText;
  final String authorName;
  final String? authorAvatarUrl;
  final bool isFollowing;
  final VoidCallback? onFollow;
  final VoidCallback? onAuthorTap;
  final VoidCallback onMore;
  final bool showPosition;

  const MediaViewerTopBar({
    super.key,
    required this.onBack,
    required this.positionText,
    required this.authorName,
    required this.onMore,
    this.authorAvatarUrl,
    this.isFollowing = false,
    this.onFollow,
    this.onAuthorTap,
    this.showPosition = true,
  });

  @override
  Widget build(BuildContext context) {
    final horizontalPadding = context.safeGetContainerSpacing(SpacingSize.md);
    final verticalPadding = context.safeGetIntraGroupSpacing(SpacingSize.sm);
    final statusBarTop = MediaQuery.of(context).padding.top;

    return LayoutBuilder(
      builder: (context, constraints) {
        final contentWidth = math.max(0.0, constraints.maxWidth - horizontalPadding * 2);
        // 左/右固定宽度，中间 Expanded，保证作者名+关注按钮有足够空间（8 字+渐变+按钮）
        final leftWidth = AppSpacing.buttonSize +
            (showPosition
                ? context.safeGetIntraGroupSpacing(SpacingSize.sm) +
                    AppSpacing.mediaViewerPositionIndicatorWidth
                : 0.0);
        final rightWidth = AppSpacing.buttonSize;
        final centerWidth = math.max(0.0, contentWidth - leftWidth - rightWidth);
        return Container(
          padding: EdgeInsets.only(
            left: horizontalPadding,
            right: horizontalPadding,
            top: statusBarTop + verticalPadding,
            bottom: verticalPadding,
          ),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                AppColors.overlayStrong,
                Colors.transparent,
              ],
            ),
          ),
          child: Row(
            children: [
              SizedBox(
                width: leftWidth,
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: ClipRect(
                    child: _buildLeftGroup(context),
                  ),
                ),
              ),
              Expanded(
                child: Center(
                  child: ClipRect(
                    child: _buildAuthorInfo(context),
                  ),
                ),
              ),
              SizedBox(
                width: rightWidth,
                child: Align(
                  alignment: Alignment.centerRight,
                  child: ClipRect(
                    child: _buildMoreButton(context),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildLeftGroup(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildBackButton(context),
        if (showPosition) ...[
          SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
          _buildPositionIndicator(context),
        ],
      ],
    );
  }

  Widget _buildBackButton(BuildContext context) {
    return InkWell(
      onTap: onBack,
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: Container(
        width: AppSpacing.buttonSize,
        height: AppSpacing.buttonSize,
        alignment: Alignment.center,
        child: Icon(
          Icons.arrow_back_ios_new,
          color: AppColors.dark.foregroundSecondary,
          size: AppSpacing.iconMedium,
        ),
      ),
    );
  }

  Widget _buildPositionIndicator(BuildContext context) {
    return Text(
      positionText,
      style: TextStyle(
        color: AppColors.dark.foregroundSecondary,
        fontSize: AppTypography.sm.sp,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  /// 头像、名字、关注按钮为一组，整体居中对齐；名字与按钮紧贴，超过 5 字用渐变遮挡
  Widget _buildAuthorInfo(BuildContext context) {
    return InkWell(
      onTap: onAuthorTap,
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _buildAvatar(),
          SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
          _buildNameAndFollow(context),
        ],
      ),
    );
  }

  /// 指定个数中文字符在名字样式下的精确宽度（与名字同字体同字号）
  static double _nameVisibleWidth(BuildContext context, int charCount) {
    final style = TextStyle(
      color: AppColors.white,
      fontSize: AppTypography.sm.sp,
      fontWeight: FontWeight.w600,
    );
    const sample = '一二三四五六七八九十';
    final text = sample.length >= charCount ? sample.substring(0, charCount) : sample;
    final tp = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout();
    return tp.width;
  }

  /// 名字与关注按钮紧贴；超过 5 字部分用渐变遮挡，再被按钮盖住
  Widget _buildNameAndFollow(BuildContext context) {
    const double gradientWidth = 20.0;
    final buttonWidth = AppSpacing.followButtonWidthCompact;
    // 只显示 5 个字，超过则渐变+按钮遮挡
    final nameVisibleWidth = _nameVisibleWidth(context, 5);
    final totalWidth = nameVisibleWidth + gradientWidth + buttonWidth;
    final height = AppSpacing.smallButtonSize;
    final nameStyle = TextStyle(
      color: AppColors.white,
      fontSize: AppTypography.sm.sp,
      fontWeight: FontWeight.w600,
    );

    if (onFollow == null) {
      return ConstrainedBox(
        constraints: BoxConstraints(maxWidth: nameVisibleWidth),
        child: Text(
          authorName,
          style: nameStyle,
          maxLines: 1,
          overflow: TextOverflow.clip,
        ),
      );
    }

    return SizedBox(
      height: height,
      width: totalWidth,
      child: Stack(
        alignment: Alignment.centerLeft,
        children: [
          // 名字全文，左对齐，可延伸到渐变和按钮下
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              authorName,
              style: nameStyle,
              maxLines: 1,
              overflow: TextOverflow.clip,
            ),
          ),
          // 第 5 字右侧到按钮左缘：透明→不透明黑，名字渐变消失后紧贴按钮
          Positioned(
            left: nameVisibleWidth,
            width: gradientWidth,
            top: 0,
            bottom: 0,
            child: IgnorePointer(
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                    colors: [
                      Colors.transparent,
                      AppColors.black,
                    ],
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            right: 0,
            child: _buildFollowButton(context, height: height),
          ),
        ],
      ),
    );
  }

  Widget _buildAvatar() {
    final avatarSize = AppSpacing.avatarUserSm;
    if (authorAvatarUrl != null && authorAvatarUrl!.isNotEmpty) {
      return CircleAvatar(
        radius: avatarSize / 2,
        backgroundImage: NetworkImage(authorAvatarUrl!),
      );
    }
    return CircleAvatar(
      radius: avatarSize / 2,
      backgroundColor: AppColors.overlayMedium,
      child: Icon(
        Icons.person,
        color: AppColors.white,
        size: AppSpacing.iconMedium,
      ),
    );
  }

  Widget _buildFollowButton(
    BuildContext context, {
    required double height,
  }) {
    final buttonText = isFollowing ? UITextConstants.following : UITextConstants.follow;
    return InkWell(
      onTap: onFollow,
      borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      child: Container(
        width: AppSpacing.followButtonWidthCompact,
        height: height,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: isFollowing ? AppColors.followingButtonOnDark : AppColors.primaryColor,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Text(
          buttonText,
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.sm.sp,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  Widget _buildMoreButton(BuildContext context) {
    return InkWell(
      onTap: onMore,
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: Container(
        width: AppSpacing.buttonSize,
        height: AppSpacing.buttonSize,
        alignment: Alignment.center,
        child: Icon(
          Icons.more_horiz,
          color: AppColors.dark.foregroundSecondary,
          size: AppSpacing.iconMedium,
        ),
      ),
    );
  }
}

class MediaViewerBottomBar extends StatelessWidget {
  final int shareCount;
  final int commentCount;
  final int likeCount;
  final int saveCount;
  final bool isLiked;
  final bool isSaved;
  final VoidCallback onShare;
  final VoidCallback onComment;
  final VoidCallback onLike;
  final VoidCallback onSave;
  final VoidCallback? onAssistant;

  const MediaViewerBottomBar({
    super.key,
    required this.shareCount,
    required this.commentCount,
    required this.likeCount,
    required this.saveCount,
    required this.isLiked,
    required this.isSaved,
    required this.onShare,
    required this.onComment,
    required this.onLike,
    required this.onSave,
    this.onAssistant,
  });

  @override
  Widget build(BuildContext context) {
    final horizontalPadding = context.safeGetContainerSpacing(SpacingSize.md);
    final bottomPadding = context.safeGetIntraGroupSpacing(SpacingSize.sm);
    final safeBottom = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.only(
        left: horizontalPadding,
        right: horizontalPadding,
        top: context.safeGetIntraGroupSpacing(SpacingSize.sm),
        bottom: safeBottom + bottomPadding,
      ),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [
            AppColors.overlayStrong,
            Colors.transparent,
          ],
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: _buildActionSlot(
              context,
              icon: Icons.share_outlined,
              count: shareCount,
              onTap: onShare,
            ),
          ),
          Expanded(
            child: _buildActionSlot(
              context,
              icon: Icons.chat_bubble_outline,
              count: commentCount,
              onTap: onComment,
            ),
          ),
          Expanded(
            child: Center(
              child: _buildAssistantButton(context),
            ),
          ),
          Expanded(
            child: _buildActionSlot(
              context,
              icon: isLiked ? Icons.favorite : Icons.favorite_border,
              count: likeCount,
              onTap: onLike,
              isActive: isLiked,
              activeColor: AppColors.error,
            ),
          ),
          Expanded(
            child: _buildActionSlot(
              context,
              icon: isSaved ? Icons.star : Icons.star_border,
              count: saveCount,
              onTap: onSave,
              isActive: isSaved,
              activeColor: AppColors.warning,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionSlot(
    BuildContext context, {
    required IconData icon,
    required int count,
    required VoidCallback onTap,
    bool isActive = false,
    Color? activeColor,
  }) {
    return Center(
      child: MediaViewerActionButton(
        icon: icon,
        count: count,
        onTap: onTap,
        isActive: isActive,
        activeColor: activeColor,
      ),
    );
  }

  Widget _buildAssistantButton(BuildContext context) {
    if (onAssistant == null) {
      return const SizedBox.shrink();
    }
    return InkWell(
      onTap: onAssistant,
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: AssistantAvatar(radius: AppSpacing.iconMedium),
    );
  }
}

class MediaViewerActionButton extends StatelessWidget {
  final IconData icon;
  final int count;
  final VoidCallback onTap;
  final bool isActive;
  final Color? activeColor;

  const MediaViewerActionButton({
    super.key,
    required this.icon,
    required this.count,
    required this.onTap,
    this.isActive = false,
    this.activeColor,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      child: Padding(
        padding: EdgeInsets.symmetric(
          vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              color: isActive ? (activeColor ?? AppColors.white) : AppColors.white,
              size: AppSpacing.iconMedium,
            ),
            SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
            Text(
              count.toString(),
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.xs.sp,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
