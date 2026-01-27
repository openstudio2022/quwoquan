/// 趣我圈设计系统 Token 定义
/// Instagram风格的设计Token，支持完整的响应式设计和夜间模式

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 颜色系统 (Instagram 风格配色)
class DesignTokens {
  // Instagram 主色调
  static const Map<String, String> instagram = {
    'blue': '#1877F2',      // Instagram 蓝色 (点赞、链接)
    'blueHover': '#166FE5',  // 蓝色悬停态
    'blueLight': '#E7F3FF',  // 蓝色浅色背景
    'blueDark': '#1565C0',   // 蓝色深色
  };

  // 基础颜色 - 浅色模式
  static const Map<String, Map<String, String>> light = {
    'background': {
      'primary': '#FFFFFF',     // 主背景
      'secondary': '#FAFAFA',   // 次要背景
      'tertiary': '#F5F5F5',    // 三级背景
      'overlay': 'rgba(0, 0, 0, 0.6)', // 遮罩层
    },
    'foreground': {
      'primary': '#262626',     // 主文字颜色
      'secondary': '#737373',   // 次要文字颜色
      'tertiary': '#C7C7C7',    // 辅助文字颜色
      'inverse': '#FFFFFF',     // 反色文字
    },
    'border': {
      'primary': '#DBDBDB',     // 主边框
      'secondary': '#EFEFEF',   // 次要边框
      'tertiary': '#F5F5F5',    // 三级边框
      'focus': '#1877F2',       // 聚焦边框
    },
    'functional': {
      'success': '#00BA7C',     // 成功色
      'warning': '#FF9500',     // 警告色
      'error': '#ED4956',       // 错误色
      'info': '#1877F2',        // 信息色
    },
  };

  // 基础颜色 - 深色模式
  static const Map<String, Map<String, String>> dark = {
    'background': {
      'primary': '#000000',     // 主背景
      'secondary': '#121212',   // 次要背景
      'tertiary': '#262626',    // 三级背景
      'overlay': 'rgba(0, 0, 0, 0.8)', // 遮罩层
    },
    'foreground': {
      'primary': '#FFFFFF',     // 主文字颜色
      'secondary': '#A8A8A8',   // 次要文字颜色
      'tertiary': '#737373',    // 辅助文字颜色
      'inverse': '#000000',     // 反色文字
    },
    'border': {
      'primary': '#363636',     // 主边框
      'secondary': '#262626',   // 次要边框
      'tertiary': '#1C1C1C',    // 三级边框
      'focus': '#1877F2',       // 聚焦边框
    },
    'functional': {
      'success': '#00BA7C',     // 成功色
      'warning': '#FF9500',     // 警告色
      'error': '#ED4956',       // 错误色
      'info': '#1877F2',        // 信息色
    },
  };

  // 按钮颜色系统
  static const Map<String, Map<String, String>> button = {
    'primary': {
      'background': '#1877F2',
      'backgroundHover': '#166FE5',
      'backgroundActive': '#1565C0',
      'backgroundDisabled': '#A8A8A8',
      'foreground': '#FFFFFF',
      'foregroundDisabled': '#FFFFFF',
    },
    'secondary': {
      'background': 'transparent',
      'backgroundHover': '#F5F5F5',
      'backgroundActive': '#EFEFEF',
      'backgroundDisabled': 'transparent',
      'foreground': '#262626',
      'foregroundDisabled': '#A8A8A8',
      'border': '#DBDBDB',
    },
    'tertiary': {
      'background': 'transparent',
      'backgroundHover': '#F5F5F5',
      'backgroundActive': '#EFEFEF',
      'backgroundDisabled': 'transparent',
      'foreground': '#1877F2',
      'foregroundDisabled': '#A8A8A8',
    },
    'destructive': {
      'background': '#ED4956',
      'backgroundHover': '#D73A49',
      'backgroundActive': '#CB2431',
      'backgroundDisabled': '#A8A8A8',
      'foreground': '#FFFFFF',
      'foregroundDisabled': '#FFFFFF',
    },
  };
}

/// 字体尺寸枚举 - 类型安全
enum FontSize {
  xs,           // 12.0 - 极小号 - 时间戳、标签
  sm,           // 13.0 - 小号 - 辅助信息
  base,         // 14.0 - 标准 - 正文内容
  lg,           // 16.0 - 大号 - 重要信息
  xl,           // 18.0 - 超大号 - 标题
  headingSm,    // 16.0 - 小标题
  headingMd,    // 18.0 - 中标题
  headingLg,    // 20.0 - 大标题
  headingXl,    // 24.0 - 超大标题
  heading2xl,   // 28.0 - 特大标题
  displaySm,    // 32.0 - 显示字号
  displayMd,    // 36.0 - 显示字号
  displayLg,    // 48.0 - 显示字号
  modalTitle,   // 16.0 - 弹窗标题
}

/// 间距类型枚举 - 类型安全
enum SpacingType {
  intraGroup,   // 组内间距
  interGroup,   // 组间间距
  container,    // 容器间距
}

// SpacingSize 枚举已移动到 app_spacing.dart 中，避免重复定义

/// 屏幕类型枚举 - 类型安全
enum ScreenType {
  mobile,       // 手机
  tablet,       // 平板
  desktop,      // 桌面
}

/// 字重枚举 - 类型安全
enum AppFontWeight {
  light,        // 300
  normal,       // 400
  medium,       // 500
  semibold,     // 600
  bold,         // 700
}

/// 行高枚举 - 类型安全
enum LineHeight {
  tight,        // 1.2
  normal,       // 1.4
  relaxed,      // 1.6
  loose,        // 1.8
}

/// 字母间距枚举 - 类型安全
enum LetterSpacing {
  tight,        // -0.025
  normal,       // 0.0
  wide,         // 0.025
}

/// 类型安全的字体系统 - 空安全
class SafeAppTypography {
  // 私有构造函数，防止实例化
  SafeAppTypography._();

  // 字体大小映射 - 保证所有值都存在
  static const Map<FontSize, double> _fontSizeValues = {
    FontSize.xs: 12.0,
    FontSize.sm: 13.0,
    FontSize.base: 14.0,
    FontSize.lg: 16.0,
    FontSize.xl: 18.0,
    FontSize.headingSm: 16.0,
    FontSize.headingMd: 18.0,
    FontSize.headingLg: 20.0,
    FontSize.headingXl: 24.0,
    FontSize.heading2xl: 28.0,
    FontSize.displaySm: 32.0,
    FontSize.displayMd: 36.0,
    FontSize.displayLg: 48.0,
    FontSize.modalTitle: 16.0,
  };

  // 字重映射
  static const Map<AppFontWeight, int> _fontWeightValues = {
    AppFontWeight.light: 300,
    AppFontWeight.normal: 400,
    AppFontWeight.medium: 500,
    AppFontWeight.semibold: 600,
    AppFontWeight.bold: 700,
  };

  // 行高映射
  static const Map<LineHeight, double> _lineHeightValues = {
    LineHeight.tight: 1.2,
    LineHeight.normal: 1.4,
    LineHeight.relaxed: 1.6,
    LineHeight.loose: 1.8,
  };

  // 字母间距映射
  static const Map<LetterSpacing, double> _letterSpacingValues = {
    LetterSpacing.tight: -0.025,
    LetterSpacing.normal: 0.0,
    LetterSpacing.wide: 0.025,
  };

  /// 类型安全的字体大小获取方法 - 保证永远不会返回null或抛出异常
  static double fontSize(FontSize size) {
    return _fontSizeValues[size] ?? 14.0; // 默认值作为最后的保障
  }

  /// 类型安全的字重获取方法
  static int fontWeight(AppFontWeight weight) {
    return _fontWeightValues[weight] ?? 400; // 默认值作为最后的保障
  }

  /// 类型安全的行高获取方法
  static double lineHeight(LineHeight height) {
    return _lineHeightValues[height] ?? 1.4; // 默认值作为最后的保障
  }

  /// 类型安全的字母间距获取方法
  static double letterSpacing(LetterSpacing spacing) {
    return _letterSpacingValues[spacing] ?? 0.0; // 默认值作为最后的保障
  }

  /// 响应式字体大小获取方法 - 类型安全
  static double responsiveFontSize({
    required FontSize mobile,
    FontSize? tablet,
    FontSize? desktop,
    required bool isDesktop,
    required bool isTablet,
  }) {
    if (isDesktop && desktop != null) {
      return fontSize(desktop);
    }
    if (isTablet && tablet != null) {
      return fontSize(tablet);
    }
    return fontSize(mobile);
  }

  // 常用字体大小的便捷访问器 - 类型安全
  static double get xs => fontSize(FontSize.xs);
  static double get sm => fontSize(FontSize.sm);
  static double get base => fontSize(FontSize.base);
  static double get lg => fontSize(FontSize.lg);
  static double get xl => fontSize(FontSize.xl);
  
  static double get headingSm => fontSize(FontSize.headingSm);
  static double get headingMd => fontSize(FontSize.headingMd);
  static double get headingLg => fontSize(FontSize.headingLg);
  static double get headingXl => fontSize(FontSize.headingXl);
  static double get heading2xl => fontSize(FontSize.heading2xl);
  
  static double get modalTitle => fontSize(FontSize.modalTitle);

  // 常用字重的便捷访问器 - 类型安全
  static int get light => fontWeight(AppFontWeight.light);
  static int get normal => fontWeight(AppFontWeight.normal);
  static int get medium => fontWeight(AppFontWeight.medium);
  static int get semibold => fontWeight(AppFontWeight.semibold);
  static int get bold => fontWeight(AppFontWeight.bold);

  // 字体族 - 保持不变
  static const List<String> fontFamily = [
    'system-ui',
    '-apple-system',
    'BlinkMacSystemFont',
    'Segoe UI',
    'Roboto',
    'Helvetica Neue',
    'Arial',
    'sans-serif'
  ];

  static const List<String> fontFamilyMono = [
    'SF Mono',
    'Monaco',
    'Inconsolata',
    'Fira Code',
    'monospace'
  ];
}

/// 类型安全的间距系统 - 空安全
class SafeAppSpacing {
  // 私有构造函数，防止实例化
  SafeAppSpacing._();

  // 响应式间距映射表 - 保证所有值都存在
  static const Map<ScreenType, Map<SpacingType, Map<SpacingSize, double>>> _responsiveSpacing = {
    // Mobile 屏幕间距
    ScreenType.mobile: {
      SpacingType.intraGroup: {
        SpacingSize.xs: 4.0,   // 紧密标签组
        SpacingSize.sm: 6.0,   // 标签组、按钮组
        SpacingSize.md: 8.0,   // 表单项、列表项
        SpacingSize.lg: 12.0,  // 卡片内容
        SpacingSize.xl: 16.0,  // 宽松布局
      },
      SpacingType.interGroup: {
        SpacingSize.xs: 8.0,   // 紧密相关组
        SpacingSize.sm: 12.0,  // 相关组
        SpacingSize.md: 16.0,  // 一般组
        SpacingSize.lg: 24.0,  // 独立组
        SpacingSize.xl: 32.0,  // 页面区块
      },
      SpacingType.container: {
        SpacingSize.xs: 8.0,   // 极小容器
        SpacingSize.sm: 12.0,  // 小容器
        SpacingSize.md: 16.0,  // 中等容器
        SpacingSize.lg: 20.0,  // 大容器
        SpacingSize.xl: 24.0,  // 超大容器
      },
    },
    
    // Tablet 屏幕间距
    ScreenType.tablet: {
      SpacingType.intraGroup: {
        SpacingSize.xs: 6.0,   // 紧密标签组
        SpacingSize.sm: 8.0,   // 标签组、按钮组
        SpacingSize.md: 12.0,  // 表单项、列表项
        SpacingSize.lg: 16.0,  // 卡片内容
        SpacingSize.xl: 20.0,  // 宽松布局
      },
      SpacingType.interGroup: {
        SpacingSize.xs: 12.0,  // 紧密相关组
        SpacingSize.sm: 16.0,  // 相关组
        SpacingSize.md: 24.0,  // 一般组
        SpacingSize.lg: 32.0,  // 独立组
        SpacingSize.xl: 40.0,  // 页面区块
      },
      SpacingType.container: {
        SpacingSize.xs: 12.0,  // 极小容器
        SpacingSize.sm: 16.0,  // 小容器
        SpacingSize.md: 20.0,  // 中等容器
        SpacingSize.lg: 24.0,  // 大容器
        SpacingSize.xl: 32.0,  // 超大容器
      },
    },
    
    // Desktop 屏幕间距
    ScreenType.desktop: {
      SpacingType.intraGroup: {
        SpacingSize.xs: 8.0,   // 紧密标签组
        SpacingSize.sm: 12.0,  // 标签组、按钮组
        SpacingSize.md: 16.0,  // 表单项、列表项
        SpacingSize.lg: 20.0,  // 卡片内容
        SpacingSize.xl: 24.0,  // 宽松布局
      },
      SpacingType.interGroup: {
        SpacingSize.xs: 16.0,  // 紧密相关组
        SpacingSize.sm: 24.0,  // 相关组
        SpacingSize.md: 32.0,  // 一般组
        SpacingSize.lg: 40.0,  // 独立组
        SpacingSize.xl: 48.0,  // 页面区块
      },
      SpacingType.container: {
        SpacingSize.xs: 16.0,  // 极小容器
        SpacingSize.sm: 20.0,  // 小容器
        SpacingSize.md: 24.0,  // 中等容器
        SpacingSize.lg: 32.0,  // 大容器
        SpacingSize.xl: 40.0,  // 超大容器
      },
    },
  };

  /// 类型安全的间距获取方法 - 保证永远不会抛出异常
  static double getSpacing({
    required SpacingType spacingType,
    required SpacingSize size,
    required ScreenType screenType,
  }) {
    // 安全地获取屏幕类型的间距
    final screenSpacing = _responsiveSpacing[screenType];
    if (screenSpacing == null) {
      return _getDefaultSpacing(spacingType, size); // 返回默认值
    }
    
    // 安全地获取间距类型的间距
    final typeSpacing = screenSpacing[spacingType];
    if (typeSpacing == null) {
      return _getDefaultSpacing(spacingType, size); // 返回默认值
    }
    
    // 安全地获取具体尺寸的间距
    final spacing = typeSpacing[size];
    if (spacing == null) {
      return _getDefaultSpacing(spacingType, size); // 返回默认值
    }
    
    return spacing;
  }

  /// 获取默认间距值 - 使用mobile屏幕的默认值
  static double _getDefaultSpacing(SpacingType spacingType, SpacingSize size) {
    final mobileSpacing = _responsiveSpacing[ScreenType.mobile];
    if (mobileSpacing == null) {
      return 16.0; // 最后的默认值
    }
    
    final typeSpacing = mobileSpacing[spacingType];
    if (typeSpacing == null) {
      return 16.0; // 最后的默认值
    }
    
    return typeSpacing[size] ?? 16.0; // 最后的默认值
  }

  /// 响应式间距获取方法 - 类型安全
  static double responsiveSpacing({
    required SpacingType spacingType,
    required SpacingSize size,
    required bool isDesktop,
    required bool isTablet,
  }) {
    final screenType = isDesktop 
        ? ScreenType.desktop 
        : isTablet 
            ? ScreenType.tablet 
            : ScreenType.mobile;
    
    return getSpacing(
      spacingType: spacingType,
      size: size,
      screenType: screenType,
    );
  }

  /// 便捷的语义间距获取方法 - 类型安全
  static double getIntraGroupSpacing({
    required SpacingSize size,
    required bool isDesktop,
    required bool isTablet,
  }) {
    return responsiveSpacing(
      spacingType: SpacingType.intraGroup,
      size: size,
      isDesktop: isDesktop,
      isTablet: isTablet,
    );
  }
  
  static double getInterGroupSpacing({
    required SpacingSize size,
    required bool isDesktop,
    required bool isTablet,
  }) {
    return responsiveSpacing(
      spacingType: SpacingType.interGroup,
      size: size,
      isDesktop: isDesktop,
      isTablet: isTablet,
    );
  }
  
  static double getContainerSpacing({
    required SpacingSize size,
    required bool isDesktop,
    required bool isTablet,
  }) {
    return responsiveSpacing(
      spacingType: SpacingType.container,
      size: size,
      isDesktop: isDesktop,
      isTablet: isTablet,
    );
  }

  /// 图标尺寸系统 - 类型安全
  static const Map<ScreenType, double> _iconMediumSizes = {
    ScreenType.mobile: 20.0,
    ScreenType.tablet: 22.0,
    ScreenType.desktop: 24.0,
  };

  static double getIconSize({
    required bool isDesktop,
    required bool isTablet,
  }) {
    final screenType = isDesktop 
        ? ScreenType.desktop 
        : isTablet 
            ? ScreenType.tablet 
            : ScreenType.mobile;
    
    return _iconMediumSizes[screenType] ?? 20.0; // 默认值
  }

  /// 屏幕类型检测 - 类型安全
  static ScreenType getScreenType(double screenWidth) {
    if (screenWidth >= 1024) {
      return ScreenType.desktop;
    } else if (screenWidth >= 768) {
      return ScreenType.tablet;
    } else {
      return ScreenType.mobile;
    }
  }

}

/// 字体尺寸枚举扩展 - 支持字符串常量
extension FontSizeExtension on FontSize {
  /// 获取字体尺寸的字符串常量值
  String get value {
    switch (this) {
      case FontSize.xs:
        return 'xs';
      case FontSize.sm:
        return 'sm';
      case FontSize.base:
        return 'base';
      case FontSize.lg:
        return 'lg';
      case FontSize.xl:
        return 'xl';
      case FontSize.headingSm:
        return 'heading-sm';
      case FontSize.headingMd:
        return 'heading-md';
      case FontSize.headingLg:
        return 'heading-lg';
      case FontSize.headingXl:
        return 'heading-xl';
      case FontSize.heading2xl:
        return 'heading-2xl';
      case FontSize.displaySm:
        return 'display-sm';
      case FontSize.displayMd:
        return 'display-md';
      case FontSize.displayLg:
        return 'display-lg';
      case FontSize.modalTitle:
        return 'modal-title';
    }
  }
}

/// 间距类型枚举扩展 - 支持字符串常量
extension SpacingTypeExtension on SpacingType {
  /// 获取间距类型的字符串常量值
  String get value {
    switch (this) {
      case SpacingType.intraGroup:
        return 'intraGroup';
      case SpacingType.interGroup:
        return 'interGroup';
      case SpacingType.container:
        return 'container';
    }
  }
}

/// 间距尺寸枚举扩展 - 支持字符串常量
extension SpacingSizeExtension on SpacingSize {
  /// 获取间距尺寸的字符串常量值
  String get value {
    switch (this) {
      case SpacingSize.xs:
        return 'xs';
      case SpacingSize.sm:
        return 'sm';
      case SpacingSize.md:
        return 'md';
      case SpacingSize.lg:
        return 'lg';
      case SpacingSize.xl:
        return 'xl';
    }
  }
}

/// 屏幕类型枚举扩展 - 支持字符串常量
extension ScreenTypeExtension on ScreenType {
  /// 获取屏幕类型的字符串常量值
  String get value {
    switch (this) {
      case ScreenType.mobile:
        return 'mobile';
      case ScreenType.tablet:
        return 'tablet';
      case ScreenType.desktop:
        return 'desktop';
    }
  }
}

/// 字重枚举扩展 - 支持字符串常量
extension AppFontWeightExtension on AppFontWeight {
  /// 获取字重的字符串常量值
  String get value {
    switch (this) {
      case AppFontWeight.light:
        return 'light';
      case AppFontWeight.normal:
        return 'normal';
      case AppFontWeight.medium:
        return 'medium';
      case AppFontWeight.semibold:
        return 'semibold';
      case AppFontWeight.bold:
        return 'bold';
    }
  }
}

/// 行高枚举扩展 - 支持字符串常量
extension LineHeightExtension on LineHeight {
  /// 获取行高的字符串常量值
  String get value {
    switch (this) {
      case LineHeight.tight:
        return 'tight';
      case LineHeight.normal:
        return 'normal';
      case LineHeight.relaxed:
        return 'relaxed';
      case LineHeight.loose:
        return 'loose';
    }
  }
}

/// 字母间距枚举扩展 - 支持字符串常量
extension LetterSpacingExtension on LetterSpacing {
  /// 获取字母间距的字符串常量值
  String get value {
    switch (this) {
      case LetterSpacing.tight:
        return 'tight';
      case LetterSpacing.normal:
        return 'normal';
      case LetterSpacing.wide:
        return 'wide';
    }
  }
}

/// 字体系统

/// 间距系统
class AppBreakpoints {
  // 断点值
  static const Map<String, double> values = {
    'xs': 0.0,      // 0px 及以上 (手机竖屏)
    'sm': 480.0,    // 480px 及以上 (手机横屏)
    'md': 768.0,    // 768px 及以上 (平板竖屏)
    'lg': 1024.0,   // 1024px 及以上 (平板横屏/小屏笔记本)
    'xl': 1280.0,   // 1280px 及以上 (大屏笔记本/小屏桌面)
    'xxl': 1536.0,  // 1536px 及以上 (大屏桌面)
  };

  // 容器最大宽度
  static const Map<String, double> container = {
    'sm': 640.0,    // 小容器
    'md': 768.0,    // 中容器
    'lg': 1024.0,   // 大容器
    'xl': 1280.0,   // 超大容器
    'xxl': 1536.0,  // 特大容器
    
    // 内容容器 (实际使用)
    'content': 1200.0,  // 主内容区最大宽度
    'reading': 680.0,   // 阅读内容最大宽度
  };
}

/// Z-Index 层级
class AppZIndex {
  static const Map<String, int> values = {
    // 基础层级
    'base': 0,
    
    // 内容层级
    'content': 10,
    'overlay': 20,
    
    // 导航层级
    'header': 40,
    'tabNavigation': 40,
    'bottomNav': 50,
    
    // 弹出层级
    'dropdown': 100,
    'modal': 200,
    'popover': 300,
    'tooltip': 400,
    'toast': 500,
    
    // 最高层级
    'max': 9999,
  };
}

/// 动画系统
class AppAnimation {
  // 动画时长
  static const Map<String, Duration> duration = {
    'fast': Duration(milliseconds: 150),
    'normal': Duration(milliseconds: 200),
    'slow': Duration(milliseconds: 300),
    'slower': Duration(milliseconds: 500),
  };

  // 动画缓动
  static final Map<String, Curve> easing = {
    'linear': Curves.linear,
    'easeIn': Curves.easeIn,
    'easeOut': Curves.easeOut,
    'easeInOut': Curves.easeInOut,
    'spring': Curves.elasticOut,
  };

  // 常用动画组合
  static final Map<String, Map<String, dynamic>> preset = {
    'fadeIn': {
      'duration': Duration(milliseconds: 200),
      'easing': Curves.easeOut,
    },
    'slideUp': {
      'duration': Duration(milliseconds: 300),
      'easing': Curves.easeOut,
    },
    'bounce': {
      'duration': Duration(milliseconds: 400),
      'easing': Curves.elasticOut,
    },
  };
}

