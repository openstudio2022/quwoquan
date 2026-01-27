import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';

/// 应用间距常量
/// 根据设计规则文档 (03_DESIGN_RULES.md) 定义
class AppSpacing {
  // ==================== 基础间距 ====================
  /// 极小间距: 4.0
  static const double xs = 4.0;
  
  /// 小间距: 8.0
  static const double sm = 8.0;
  
  /// 中等间距: 16.0
  static const double md = 16.0;
  
  /// 大间距: 24.0
  static const double lg = 24.0;
  
  /// 超大间距: 32.0
  static const double xl = 32.0;

  // ==================== 组件尺寸 ====================
  /// 按钮尺寸: 44.0
  static const double buttonSize = 44.0;
  
  /// 按钮高度: 48.0
  static const double buttonHeight = 48.0;
  
  /// 大按钮尺寸: 48.0
  static const double largeButtonSize = 48.0;
  
  /// 小按钮尺寸: 32.0
  static const double smallButtonSize = 32.0;
  
  /// 头像尺寸: 40.0
  static const double avatarSize = 40.0;
  
  /// 小头像尺寸: 32.0
  static const double smallAvatarSize = 32.0;
  
  /// 大头像尺寸: 64.0
  static const double largeAvatarSize = 64.0;
  
  /// 底部导航高度: 56.0
  static const double bottomNavHeight = 56.0;
  
  /// 标签导航高度: 48.0
  static const double tabNavigationHeight = 48.0;
  
  /// 子标签导航高度: 44.0
  static const double subTabNavigationHeight = 44.0;
  
  /// 模态框头部高度: 56.0
  static const double modalHeaderHeight = 56.0;

  // ==================== 内容间距 ====================
  /// 内容间距 - 极小
  static const double contentSpacingXs = 4.0;
  
  /// 内容间距 - 小
  static const double contentSpacingSm = 8.0;
  
  /// 内容间距 - 中
  static const double contentSpacingMd = 16.0;
  
  /// 帖子间距 - 极小
  static const double postSpacingXs = 4.0;
  
  /// 故事高度: 80.0
  static const double storyHeight = 80.0;
  
  /// 用户名最小宽度: 60.0
  static const double usernameMinWidth = 60.0;
  
  /// 关注按钮宽度: 80.0
  static const double followButtonWidth = 80.0;

  // ==================== 图标尺寸 ====================
  /// 小图标: 16.0
  static const double iconSmall = 16.0;
  
  /// 中图标: 24.0
  static const double iconMedium = 24.0;
  
  /// 大图标: 32.0
  static const double iconLarge = 32.0;

  // ==================== 圆角 ====================
  /// 小圆角: 4.0 (按钮、标签、输入框、小卡片)
  static const double smallBorderRadius = 4.0;
  
  /// 标准圆角: 8.0 (卡片、模态框、图片、头像)
  static const double borderRadius = 8.0;
  
  /// 大圆角: 12.0 (大卡片、页面容器、特殊组件)
  static const double largeBorderRadius = 12.0;
  
  /// 圆形: 999.0 (小头像、圆形按钮、圆形图标)
  static const double circularBorderRadius = 999.0;
  
  /// 完全圆形: 999.0
  static const double fullBorderRadius = 999.0;

  // ==================== 语义间距（基础值，Mobile屏幕） ====================
  /// 语义间距映射表
  /// 根据设计规则文档定义的响应式间距系统
  /// 格式: semantic[语义类型][尺寸等级]
  /// 
  /// 使用示例:
  /// ```dart
  /// AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd
  /// ```
  static final Map<String, Map<String, double>> semantic = {
    // 组内间距 (intraGroup) - 同一组内相关元素之间
    DesignSemanticConstants.intraGroup: {
      DesignSemanticConstants.xs: 4.0,   // Mobile: 4px - 紧密标签组
      DesignSemanticConstants.sm: 6.0,   // Mobile: 6px - 标签组、按钮组
      DesignSemanticConstants.md: 8.0,   // Mobile: 8px - 表单项、列表项
      DesignSemanticConstants.lg: 12.0,  // Mobile: 12px - 卡片内容
      DesignSemanticConstants.xl: 16.0,  // Mobile: 16px - 宽松布局
    },
    
    // 组间间距 (interGroup) - 不同组之间
    DesignSemanticConstants.interGroup: {
      DesignSemanticConstants.xs: 8.0,   // Mobile: 8px - 紧密相关组
      DesignSemanticConstants.sm: 12.0,  // Mobile: 12px - 相关组
      DesignSemanticConstants.md: 16.0,  // Mobile: 16px - 一般组
      DesignSemanticConstants.lg: 24.0,  // Mobile: 24px - 独立组
      DesignSemanticConstants.xl: 32.0,  // Mobile: 32px - 页面区块
    },
    
    // 容器间距 (container) - 容器内边距
    DesignSemanticConstants.container: {
      DesignSemanticConstants.xs: 8.0,   // Mobile: 8px - 极小容器
      DesignSemanticConstants.sm: 12.0,  // Mobile: 12px - 小容器
      DesignSemanticConstants.md: 16.0,  // Mobile: 16px - 中等容器
      DesignSemanticConstants.lg: 20.0,  // Mobile: 20px - 大容器
      DesignSemanticConstants.xl: 24.0,  // Mobile: 24px - 超大容器
    },
  };

  // ==================== 语义间距快捷常量（向后兼容） ====================
  // 组内间距
  static const double intraGroupXs = 4.0;
  static const double intraGroupSm = 6.0;
  static const double intraGroupMd = 8.0;
  static const double intraGroupLg = 12.0;
  static const double intraGroupXl = 16.0;

  // 组间间距
  static const double interGroupXs = 8.0;
  static const double interGroupSm = 12.0;
  static const double interGroupMd = 16.0;
  static const double interGroupLg = 24.0;
  static const double interGroupXl = 32.0;

  // 容器间距
  static const double containerXs = 8.0;
  static const double containerSm = 12.0;
  static const double containerMd = 16.0;
  static const double containerLg = 20.0;
  static const double containerXl = 24.0;

  // ==================== 响应式间距方法 ====================
  /// 获取响应式间距
  /// 
  /// [semanticType] 语义类型: 'intraGroup', 'interGroup', 'container'
  /// [size] 尺寸等级: 'xs', 'sm', 'md', 'lg', 'xl'
  /// [context] BuildContext，用于获取屏幕尺寸（可选）
  /// [screenType] 屏幕类型: 'mobile', 'tablet', 'desktop'（可选，优先使用）
  /// 
  /// 返回对应屏幕尺寸的间距值
  static double getSpacing(
    String semanticType,
    String size, {
    BuildContext? context,
    String? screenType,
  }) {
    // 如果指定了screenType，使用指定类型
    if (screenType != null) {
      return _getSpacingForScreenType(semanticType, size, screenType);
    }
    
    // 如果有context，自动检测屏幕类型
    if (context != null) {
      final screenWidth = MediaQuery.of(context).size.width;
      final detectedType = _detectScreenType(screenWidth);
      return _getSpacingForScreenType(semanticType, size, detectedType);
    }
    
    // 默认返回Mobile屏幕的间距（基础值）
    return semantic[semanticType]?[size] ?? _getDefaultSpacing(size);
  }

  /// 根据屏幕类型获取间距
  static double _getSpacingForScreenType(
    String semanticType,
    String size,
    String screenType,
  ) {
    // 响应式间距映射表（根据设计规则文档）
    final responsiveMap = _getResponsiveSpacingMap(screenType);
    return responsiveMap[semanticType]?[size] ?? 
           semantic[semanticType]?[size] ?? 
           _getDefaultSpacing(size);
  }

  /// 检测屏幕类型
  static String _detectScreenType(double screenWidth) {
    if (screenWidth < 768) {
      return 'mobile';
    } else if (screenWidth < 1024) {
      return 'tablet';
    } else {
      return 'desktop';
    }
  }

  /// 获取响应式间距映射表
  static Map<String, Map<String, double>> _getResponsiveSpacingMap(String screenType) {
    switch (screenType) {
      case 'tablet':
        return {
          DesignSemanticConstants.intraGroup: {
            DesignSemanticConstants.xs: 6.0,
            DesignSemanticConstants.sm: 8.0,
            DesignSemanticConstants.md: 12.0,
            DesignSemanticConstants.lg: 16.0,
            DesignSemanticConstants.xl: 20.0,
          },
          DesignSemanticConstants.interGroup: {
            DesignSemanticConstants.xs: 12.0,
            DesignSemanticConstants.sm: 16.0,
            DesignSemanticConstants.md: 24.0,
            DesignSemanticConstants.lg: 32.0,
            DesignSemanticConstants.xl: 40.0,
          },
          DesignSemanticConstants.container: {
            DesignSemanticConstants.xs: 12.0,
            DesignSemanticConstants.sm: 16.0,
            DesignSemanticConstants.md: 20.0,
            DesignSemanticConstants.lg: 24.0,
            DesignSemanticConstants.xl: 32.0,
          },
        };
      
      case 'desktop':
        return {
          DesignSemanticConstants.intraGroup: {
            DesignSemanticConstants.xs: 8.0,
            DesignSemanticConstants.sm: 12.0,
            DesignSemanticConstants.md: 16.0,
            DesignSemanticConstants.lg: 20.0,
            DesignSemanticConstants.xl: 24.0,
          },
          DesignSemanticConstants.interGroup: {
            DesignSemanticConstants.xs: 16.0,
            DesignSemanticConstants.sm: 24.0,
            DesignSemanticConstants.md: 32.0,
            DesignSemanticConstants.lg: 40.0,
            DesignSemanticConstants.xl: 48.0,
          },
          DesignSemanticConstants.container: {
            DesignSemanticConstants.xs: 16.0,
            DesignSemanticConstants.sm: 20.0,
            DesignSemanticConstants.md: 24.0,
            DesignSemanticConstants.lg: 32.0,
            DesignSemanticConstants.xl: 40.0,
          },
        };
      
      case 'mobile':
      default:
        return semantic;
    }
  }

  /// 获取默认间距值
  static double _getDefaultSpacing(String size) {
    switch (size) {
      case DesignSemanticConstants.xs:
        return xs;
      case DesignSemanticConstants.sm:
        return sm;
      case DesignSemanticConstants.md:
        return md;
      case DesignSemanticConstants.lg:
        return lg;
      case DesignSemanticConstants.xl:
        return xl;
      default:
        return md;
    }
  }
}
