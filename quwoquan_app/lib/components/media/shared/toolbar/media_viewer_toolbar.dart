import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';

/// 'full'：作品模式，含作者/关注/位置；'backOnly'：微趣模式，仅返回+更多
typedef ToolbarMode = String;

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

  /// 'full'（默认）| 'backOnly'：backOnly 时仅显示返回、更多
  final String toolbarMode;

  /// 与底部互动栏、内容区共用 rail；图片/视频沉浸页使用 [ImmersiveViewerStageLayoutSpec.mediaStage]。
  final ImmersiveViewerStageLayoutSpec layoutSpec;

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
    this.toolbarMode = 'full',
    this.layoutSpec = ImmersiveViewerStageLayoutSpec.feedRail,
  });

  bool get _isBackOnly => toolbarMode == 'backOnly';

  @override
  Widget build(BuildContext context) {
    final verticalPadding = context.safeGetIntraGroupSpacing(SpacingSize.sm);
    final statusBarTop = MediaQuery.of(context).padding.top;
    final showPositionInBar = showPosition && !_isBackOnly;
    final showAuthorInBar = !_isBackOnly;

    return Container(
      padding: EdgeInsets.only(
        top: statusBarTop + verticalPadding,
        bottom: verticalPadding,
      ),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [AppColors.overlayStrong, AppColors.transparent],
        ),
      ),
      child: ImmersiveViewerLayout.alignToRail(
        context: context,
        layoutSpec: layoutSpec,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _buildLeftGroup(context, showPositionInBar),
                _buildMoreButton(context),
              ],
            ),
            if (showAuthorInBar) _buildAuthorInfo(context),
          ],
        ),
      ),
    );
  }

  Widget _buildLeftGroup(BuildContext context, bool showPos) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildBackButton(context),
        if (showPos) ...[
          const SizedBox(width: AppSpacing.intraGroupSm),
          _buildPositionIndicator(context),
        ],
      ],
    );
  }

  Widget _buildBackButton(BuildContext context) {
    return ImmersiveToolbarIconButton(
      icon: CupertinoIcons.back,
      onPressed: onBack,
    );
  }

  Widget _buildPositionIndicator(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Text(
        positionText,
        style: TextStyle(
          color: AppColors.white,
          fontSize: AppTypography.sm,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }

  /// 头像、名字、关注按钮为一组，整体居中对齐；名字与按钮紧贴，超过 5 字用渐变遮挡
  Widget _buildAuthorInfo(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onAuthorTap,
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
      fontSize: AppTypography.sm,
      fontWeight: AppTypography.semiBold,
    );
    const sample = '一二三四五六七八九十';
    final text = sample.length >= charCount
        ? sample.substring(0, charCount)
        : sample;
    final tp = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout();
    return tp.width;
  }

  /// 名字与关注按钮紧贴；超过 5 字部分用渐变遮挡，再被按钮盖住
  Widget _buildNameAndFollow(BuildContext context) {
    const double gradientWidth = 20.0;
    final buttonMaxWidth = AppSpacing.followButtonWidthCompact;
    final height = AppSpacing.buttonHeightForSizeCompact(
      DesignSemanticConstants.sm,
    );
    // 只显示 5 个字，超过则渐变+按钮遮挡
    final nameVisibleWidth = _nameVisibleWidth(context, 5);
    final totalWidth = nameVisibleWidth + gradientWidth + buttonMaxWidth;
    final nameStyle = TextStyle(
      color: AppColors.white,
      fontSize: AppTypography.sm,
      fontWeight: AppTypography.medium,
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
                    colors: [AppColors.transparent, AppColors.black],
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

  Widget _buildFollowButton(BuildContext context, {required double height}) {
    final buttonText = isFollowing
        ? UITextConstants.following
        : UITextConstants.follow;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onFollow,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: AppSpacing.followButtonWidthCompact,
        ),
        padding: AppSpacing.buttonPaddingCompact(
          context,
          DesignSemanticConstants.sm,
        ),
        height: height,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: isFollowing
              ? AppColors.followingButtonOnDark
              : AppColors.primaryColor,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Text(
          buttonText,
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.semiBold,
          ),
        ),
      ),
    );
  }

  Widget _buildMoreButton(BuildContext context) {
    return ImmersiveToolbarIconButton(
      icon: CupertinoIcons.ellipsis,
      onPressed: onMore,
    );
  }
}

class ImmersiveToolbarIconButton extends StatelessWidget {
  const ImmersiveToolbarIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.foregroundColor = AppColors.white,
    this.backgroundColor,
    this.borderColor,
    this.size = AppSpacing.minInteractiveSize,
    this.iconSize = AppSpacing.iconMedium,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final Color foregroundColor;
  final Color? backgroundColor;
  final Color? borderColor;
  final double size;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    final fill = backgroundColor ?? AppColors.black.withValues(alpha: 0.24);
    final outline = borderColor ?? AppColors.white.withValues(alpha: 0.14);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(size),
      onPressed: onPressed,
      child: ClipOval(
        child: BackdropFilter(
          filter: ImageFilter.blur(
            sigmaX: AppSpacing.sm,
            sigmaY: AppSpacing.sm,
          ),
          child: Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: fill,
              shape: BoxShape.circle,
              border: Border.all(color: outline, width: AppSpacing.hairline),
            ),
            child: Icon(icon, color: foregroundColor, size: iconSize),
          ),
        ),
      ),
    );
  }
}

class MediaViewerBottomBar extends StatelessWidget {
  final int shareCount;
  final int commentCount;
  final int likeCount;
  final bool isLiked;
  final VoidCallback onShare;
  final VoidCallback onComment;
  final VoidCallback onLike;
  final VoidCallback? onAssistant;

  const MediaViewerBottomBar({
    super.key,
    required this.shareCount,
    required this.commentCount,
    required this.likeCount,
    required this.isLiked,
    required this.onShare,
    required this.onComment,
    required this.onLike,
    this.onAssistant,
  });

  @override
  Widget build(BuildContext context) {
    final bottomPadding = context.safeGetIntraGroupSpacing(SpacingSize.sm);
    final safeBottom = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.only(
        top: context.safeGetIntraGroupSpacing(SpacingSize.sm),
        bottom: safeBottom + bottomPadding,
      ),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [AppColors.overlayStrong, AppColors.transparent],
        ),
      ),
      child: ImmersiveViewerLayout.alignToRail(
        context: context,
        child: Row(
          children: [
            Expanded(
              child: _buildActionSlot(
                context,
                iconWidget: Icon(
                  isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
                  color: isLiked ? AppColors.error : AppColors.white,
                  size: AppSpacing.iconMedium,
                ),
                count: likeCount,
                onTap: onLike,
              ),
            ),
            Expanded(
              child: _buildActionSlot(
                context,
                iconWidget: Icon(
                  CupertinoIcons.arrowshape_turn_up_right,
                  color: AppColors.white,
                  size: AppSpacing.iconMedium,
                ),
                count: shareCount,
                onTap: onShare,
              ),
            ),
            Expanded(
              child: _buildActionSlot(
                context,
                iconWidget: AppBubbleIcon(
                  size: AppSpacing.iconMedium,
                  color: AppColors.white,
                ),
                count: commentCount,
                onTap: onComment,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionSlot(
    BuildContext context, {
    required Widget iconWidget,
    required int count,
    required VoidCallback onTap,
  }) {
    return Center(
      child: MediaViewerActionButton(
        iconWidget: iconWidget,
        count: count,
        onTap: onTap,
      ),
    );
  }
}

class MediaViewerActionButton extends StatelessWidget {
  final Widget iconWidget;
  final int count;
  final VoidCallback onTap;

  const MediaViewerActionButton({
    super.key,
    required this.iconWidget,
    required this.count,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
        horizontal: context.safeGetIntraGroupSpacing(SpacingSize.xs),
      ),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          iconWidget,
          if (count > 0) ...[
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
            Text(
              formatCompactActionCount(count),
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.medium,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
