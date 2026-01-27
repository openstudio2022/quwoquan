import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/comment_system/comment_models.dart';

/// 评论组件响应式适配工具（类型安全版本）
class CommentResponsive {
  /// 获取响应式弹窗高度 - 基于类型安全的间距系统
  static double getModalHeight(
    BuildContext context, 
    CommentModalHeight mode,
    int commentCount,
    int totalReplies,
  ) {
    final screenHeight = MediaQuery.of(context).size.height;
    
    switch (mode) {
      case CommentModalHeight.third:
        return screenHeight * 0.33;
      case CommentModalHeight.twoThirds:
        return screenHeight * 0.67;
      case CommentModalHeight.adaptive:
        // 根据内容计算合适高度
        final estimatedHeight = _estimateContentHeight(
          context,
          commentCount, 
          totalReplies,
        );
        if (estimatedHeight < screenHeight * 0.4) {
          return screenHeight * 0.4; // 最小高度
        } else if (estimatedHeight > screenHeight * 0.8) {
          return screenHeight * 0.8; // 最大高度
        }
        return estimatedHeight;
    }
  }

  /// 获取最小弹窗高度（1/3屏幕高度）
  static double getMinModalHeight(BuildContext context) {
    return MediaQuery.of(context).size.height * 0.33;
  }

  /// 获取最大弹窗高度（2/3屏幕高度）
  static double getMaxModalHeight(BuildContext context) {
    return MediaQuery.of(context).size.height * 0.67;
  }

  /// 估算内容高度
  static double _estimateContentHeight(
    BuildContext context,
    int commentCount,
    int totalReplies,
  ) {
    final screenHeight = MediaQuery.of(context).size.height;
    final screenType = context.safeScreenType;
    
    // 基础高度（头部 + 输入框 + 底部安全区域）
    double baseHeight = context.safeGetContainerSpacing(SpacingSize.lg) * 3;
    
    // 评论项高度估算
    double commentItemHeight = _getCommentItemHeight(context, screenType);
    double replyItemHeight = _getReplyItemHeight(context, screenType);
    
    // 计算总高度
    double estimatedHeight = baseHeight + 
        (commentCount * commentItemHeight) + 
        (totalReplies * replyItemHeight * 0.7); // 回复项通常更紧凑
    
    // 限制在合理范围内
    return estimatedHeight.clamp(
      screenHeight * 0.4,
      screenHeight * 0.8,
    );
  }

  /// 获取评论项高度
  static double _getCommentItemHeight(BuildContext context, ScreenType screenType) {
    final baseSpacing = context.safeGetIntraGroupSpacing(SpacingSize.md);
    
    switch (screenType) {
      case ScreenType.desktop:
        return baseSpacing * 8; // 桌面端更高
      case ScreenType.tablet:
        return baseSpacing * 7; // 平板端中等
      case ScreenType.mobile:
        return baseSpacing * 6; // 移动端紧凑
    }
  }

  /// 获取回复项高度
  static double _getReplyItemHeight(BuildContext context, ScreenType screenType) {
    final baseSpacing = context.safeGetIntraGroupSpacing(SpacingSize.sm);
    
    switch (screenType) {
      case ScreenType.desktop:
        return baseSpacing * 6; // 桌面端
      case ScreenType.tablet:
        return baseSpacing * 5; // 平板端
      case ScreenType.mobile:
        return baseSpacing * 4; // 移动端
    }
  }

  /// 获取响应式字体大小 - 基于类型安全的字体系统
  static double getFontSize(BuildContext context, CommentFontSize fontSize) {
    final screenType = context.safeScreenType;
    
    switch (fontSize) {
      case CommentFontSize.title:
        return SafeAppTypography.responsiveFontSize(
          mobile: FontSize.base,
          tablet: FontSize.lg,
          desktop: FontSize.xl,
          isDesktop: screenType == ScreenType.desktop,
          isTablet: screenType == ScreenType.tablet,
        );
      case CommentFontSize.body:
        return SafeAppTypography.responsiveFontSize(
          mobile: FontSize.sm,
          tablet: FontSize.base,
          desktop: FontSize.base,
          isDesktop: screenType == ScreenType.desktop,
          isTablet: screenType == ScreenType.tablet,
        );
      case CommentFontSize.small:
        return SafeAppTypography.responsiveFontSize(
          mobile: FontSize.xs,
          tablet: FontSize.sm,
          desktop: FontSize.sm,
          isDesktop: screenType == ScreenType.desktop,
          isTablet: screenType == ScreenType.tablet,
        );
      case CommentFontSize.caption:
        return SafeAppTypography.responsiveFontSize(
          mobile: FontSize.xs,
          tablet: FontSize.xs,
          desktop: FontSize.xs,
          isDesktop: screenType == ScreenType.desktop,
          isTablet: screenType == ScreenType.tablet,
        );
    }
  }

  /// 获取响应式图标尺寸 - 基于类型安全的图标系统
  static double getIconSize(BuildContext context) {
    final screenType = context.safeScreenType;
    
    return SafeAppSpacing.getIconSize(
      isDesktop: screenType == ScreenType.desktop,
      isTablet: screenType == ScreenType.tablet,
    );
  }

  /// 获取响应式弹窗内边距 - 基于类型安全的间距系统
  static EdgeInsets getModalPadding(BuildContext context) {
    final horizontalPadding = context.safeGetContainerSpacing(SpacingSize.md);
    final verticalPadding = context.safeGetIntraGroupSpacing(SpacingSize.sm);
    
    return EdgeInsets.symmetric(
      horizontal: horizontalPadding,
      vertical: verticalPadding,
    );
  }

  /// 获取响应式评论项内边距
  static EdgeInsets getCommentItemPadding(BuildContext context) {
    final horizontalPadding = context.safeGetContainerSpacing(SpacingSize.md);
    final verticalPadding = context.safeGetIntraGroupSpacing(SpacingSize.sm);
    
    return EdgeInsets.symmetric(
      horizontal: horizontalPadding,
      vertical: verticalPadding,
    );
  }

  /// 获取响应式回复项内边距
  static EdgeInsets getReplyItemPadding(BuildContext context) {
    final horizontalPadding = context.safeGetContainerSpacing(SpacingSize.sm);
    final verticalPadding = context.safeGetIntraGroupSpacing(SpacingSize.xs);
    
    return EdgeInsets.symmetric(
      horizontal: horizontalPadding,
      vertical: verticalPadding,
    );
  }

  /// 获取响应式间距 - 使用类型安全的间距系统
  static double getSpacing(
    BuildContext context, 
    SpacingType spacingType, 
    SpacingSize size,
  ) {
    return context.safeGetSpacing(spacingType, size);
  }

  /// 便捷方法：获取组内间距
  static double getIntraGroupSpacing(BuildContext context, SpacingSize size) {
    return context.safeGetIntraGroupSpacing(size);
  }

  /// 便捷方法：获取组间间距
  static double getInterGroupSpacing(BuildContext context, SpacingSize size) {
    return context.safeGetInterGroupSpacing(size);
  }

  /// 便捷方法：获取容器间距
  static double getContainerSpacing(BuildContext context, SpacingSize size) {
    return context.safeGetContainerSpacing(size);
  }

  /// 获取弹窗拖拽指示器宽度
  static double getModalDragHandleWidth(BuildContext context) {
    final screenType = context.safeScreenType;
    
    switch (screenType) {
      case ScreenType.desktop:
        return 40.0;
      case ScreenType.tablet:
        return 36.0;
      case ScreenType.mobile:
        return 32.0;
    }
  }

  /// 获取弹窗拖拽指示器高度
  static double getModalDragHandleHeight(BuildContext context) {
    return context.safeGetIntraGroupSpacing(SpacingSize.xs);
  }

  /// 获取弹窗标题字体大小
  static double getModalTitleFontSize(BuildContext context) {
    return getFontSize(context, CommentFontSize.title);
  }

  /// 获取评论项宽度
  static double getCommentItemWidth(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final padding = context.safeGetContainerSpacing(SpacingSize.md) * 2;
    
    return screenWidth - padding;
  }

  /// 获取评论项尺寸
  static double getCommentItemSize(BuildContext context) {
    final screenType = context.safeScreenType;
    
    switch (screenType) {
      case ScreenType.desktop:
        return 48.0;
      case ScreenType.tablet:
        return 44.0;
      case ScreenType.mobile:
        return 40.0;
    }
  }

  /// 获取评论项图标尺寸
  static double getCommentItemIconSize(BuildContext context) {
    final screenType = context.safeScreenType;
    
    switch (screenType) {
      case ScreenType.desktop:
        return 20.0;
      case ScreenType.tablet:
        return 18.0;
      case ScreenType.mobile:
        return 16.0;
    }
  }

  /// 获取评论项字体大小
  static double getCommentItemFontSize(BuildContext context) {
    return getFontSize(context, CommentFontSize.body);
  }

  /// 获取输入框高度
  static double getInputHeight(BuildContext context) {
    final screenType = context.safeScreenType;
    final baseSpacing = context.safeGetIntraGroupSpacing(SpacingSize.md);
    
    switch (screenType) {
      case ScreenType.desktop:
        return baseSpacing * 4;
      case ScreenType.tablet:
        return baseSpacing * 3.5;
      case ScreenType.mobile:
        return baseSpacing * 3;
    }
  }

  /// 获取头像尺寸
  static double getAvatarSize(BuildContext context) {
    final screenType = context.safeScreenType;
    
    switch (screenType) {
      case ScreenType.desktop:
        return 40.0;
      case ScreenType.tablet:
        return 36.0;
      case ScreenType.mobile:
        return 32.0;
    }
  }

  /// 获取回复缩进
  static double getReplyIndent(BuildContext context, int level) {
    final baseIndent = context.safeGetIntraGroupSpacing(SpacingSize.md);
    return baseIndent * (level + 1);
  }
}

/// 评论字体尺寸枚举
enum CommentFontSize {
  title,    // 标题字体
  body,     // 正文字体
  small,    // 小字体
  caption,  // 说明字体
}
