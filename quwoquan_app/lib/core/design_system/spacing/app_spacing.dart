import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';

/// 应用间距常量
/// 根据设计规则文档 (03_DESIGN_RULES.md) 定义
class AppSpacing {
  // ==================== 响应式断点 ====================
  static const double compactBreakpoint = 360.0;
  static const double expandedBreakpoint = 600.0;

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

  // ==================== 按钮语义尺寸（小、正常、中、大，不受容器约束） ====================
  /// 按钮高度 xs: 28.0
  static const double buttonHeightXs = 28.0;
  /// 按钮高度 sm: 32.0
  static const double buttonHeightSm = 32.0;
  /// 按钮高度 md: 36.0（与「重置」等次要操作一致）
  static const double buttonHeightMd = 36.0;
  /// 按钮高度 lg: 48.0
  static const double buttonHeightLg = 48.0;
  /// 图标按钮最小点击区域 sm: 44.0
  static const double iconButtonMinSizeSm = 44.0;
  /// 图标按钮最小点击区域 md: 64.0
  static const double iconButtonMinSizeMd = 64.0;
  /// 统一可点击区域最低标准（WCAG 触控建议）
  static const double minInteractiveSize = 44.0;
  
  /// 获取文案按钮内边距（按断点适配，不受容器约束）
  static EdgeInsets buttonPadding(
    BuildContext context,
    String size,
  ) {
    final horizontal = getSpacing(
      DesignSemanticConstants.container,
      size == DesignSemanticConstants.lg
          ? DesignSemanticConstants.lg
          : DesignSemanticConstants.md,
      context: context,
    );
    final vertical = getSpacing(
      DesignSemanticConstants.intraGroup,
      size == DesignSemanticConstants.lg
          ? DesignSemanticConstants.sm
          : DesignSemanticConstants.xs,
      context: context,
    );
    return EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical);
  }
  
  /// 获取文案按钮高度（固定语义值，不受容器约束）
  static double buttonHeightForSize(String size) {
    switch (size) {
      case DesignSemanticConstants.xs:
        return buttonHeightXs;
      case DesignSemanticConstants.sm:
        return buttonHeightSm;
      case DesignSemanticConstants.lg:
        return buttonHeightLg;
      case DesignSemanticConstants.md:
      default:
        return buttonHeightMd;
    }
  }

  // ==================== 按钮紧凑语义（每档尺寸对应更小内边距/高度，用于关注等紧凑场景） ====================
  /// 紧凑按钮高度 sm: 26.0
  static const double buttonHeightSmCompact = 26.0;
  /// 紧凑按钮高度 md: 28.0（复用 xs）
  static const double buttonHeightMdCompact = 28.0;
  /// 紧凑按钮高度 lg: 32.0（复用 sm）
  static const double buttonHeightLgCompact = 32.0;

  /// 获取文案按钮内边距（紧凑模式：左右上下更小，语义统一）
  static EdgeInsets buttonPaddingCompact(
    BuildContext context,
    String size,
  ) {
    final horizontal = getSpacing(
      DesignSemanticConstants.container,
      size == DesignSemanticConstants.lg
          ? DesignSemanticConstants.sm
          : DesignSemanticConstants.xs,
      context: context,
    );
    final vertical = getSpacing(
      DesignSemanticConstants.intraGroup,
      DesignSemanticConstants.xs,
      context: context,
    );
    return EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical);
  }

  /// 获取文案按钮高度（紧凑模式，固定语义值）
  static double buttonHeightForSizeCompact(String size) {
    switch (size) {
      case DesignSemanticConstants.xs:
        return buttonHeightXs;
      case DesignSemanticConstants.sm:
        return buttonHeightSmCompact;
      case DesignSemanticConstants.lg:
        return buttonHeightLgCompact;
      case DesignSemanticConstants.md:
      default:
        return buttonHeightMdCompact;
    }
  }
  
  /// 头像尺寸: 40.0（向后兼容）
  static const double avatarSize = 40.0;

  /// 小头像尺寸: 32.0（向后兼容）
  static const double smallAvatarSize = 32.0;

  /// 大头像尺寸: 64.0（向后兼容）
  static const double largeAvatarSize = 64.0;

  // ==================== 头像语义尺寸（AVATAR_DESIGN_SYSTEM，Mobile 基准） ====================
  /// 个人/作者/AI 头像 xs: 24px
  static const double avatarUserXs = 24.0;
  static const double avatarCircleXs = 24.0;
  /// 个人/作者/AI 头像 sm: 32px
  static const double avatarUserSm = 32.0;
  static const double avatarCircleSm = 32.0;
  /// 个人/作者/AI 头像 md: 40px
  static const double avatarUserMd = 40.0;
  static const double avatarCircleMd = 40.0;
  /// 个人/作者/AI 头像 lg: 56px
  static const double avatarUserLg = 56.0;
  static const double avatarCircleLg = 56.0;
  /// 个人/作者/AI 头像 xl: 72px
  static const double avatarUserXl = 72.0;
  static const double avatarCircleXl = 72.0;

  /// 圈子头像圆角比例（border-radius: 20%）
  static const double avatarCircleBorderRadiusRatio = 0.2;
  
  /// 底部导航高度: 56.0
  static const double bottomNavHeight = 56.0;
  
  /// 标签导航高度: 48.0
  static const double tabNavigationHeight = 48.0;
  
  /// 子标签导航高度: 44.0
  static const double subTabNavigationHeight = 44.0;

  /// 一级 Tab 芯片基准宽度（居中滚动 Tab 栏用；2 CJK 字 ≈ 32px + 触控余量 ≥ minInteractiveSize）
  static const double tabChipBaseWidth = 48.0;

  /// 视频沉浸模式下一级 Tab 芯片宽度（略大，避免「视频」等两字被裁切、只显示「视」亮色）
  static const double tabChipBaseWidthVideoImmersion = 64.0;

  /// 一级 Tab 芯片间距（发现、圈子统一；组内语义 intraGroup.md，同一导航组内间距）
  static const double primaryTabChipGap = intraGroupMd;

  /// 发现/圈子内容区左右边距（微趣、文章、图片宫格、圈子各 tab 页统一使用）
  static double feedContentHorizontal(BuildContext context) =>
      getSpacing(
        DesignSemanticConstants.container,
        DesignSemanticConstants.md,
        context: context,
      );
  /// 顶部工具栏高度（常规）
  static const double toolbarHeight = 56.0;
  /// 底部工具栏最小触控高度
  static const double toolbarMinTouchHeight = 48.0;
  
  /// 模态框头部高度: 56.0
  static const double modalHeaderHeight = 56.0;

  /// 创作入口抽屉最大高度比例 (67vh)
  static const double createEntrySheetMaxHeightRatio = 0.67;

  /// 创作入口抽屉顶部拖拽手柄宽度
  static const double createEntrySheetHandleWidth = 40.0;

  /// 创作入口抽屉顶部拖拽手柄高度
  static const double createEntrySheetHandleHeight = 4.0;

  /// 私人助理半屏面板高度比例 (55-60vh)
  static const double assistantPanelHeightRatioMin = 0.55;
  static const double assistantPanelHeightRatioMax = 0.60;

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

  /// 关注按钮宽度（紧凑，用于媒体查看器顶栏，左右间距更小）: 56.0
  static const double followButtonWidthCompact = 56.0;

  /// 媒体查看器顶栏位置指示器预估宽度（如 "1/9"）: 44.0
  static const double mediaViewerPositionIndicatorWidth = 44.0;

  // ==================== 图标尺寸 ====================
  /// 小图标: 16.0
  static const double iconSmall = 16.0;
  
  /// 中图标: 24.0
  static const double iconMedium = 24.0;
  
  /// 大图标: 32.0
  static const double iconLarge = 32.0;

  // ==================== 工具面板功能项（裁剪比例 / 旋转四项 / 专业工具列表） ====================
  /// 功能项图标尺寸，与 iconMedium 一致
  static const double toolPanelItemIconSize = iconMedium;
  /// 功能项：图标与文案间距，使用组内极小间距语义
  static const double toolPanelItemIconLabelGap = intraGroupSm;
  /// 功能项单行文案行高（与 toolPanelItemLabel / xs 字号搭配，用于滤镜等单行标签）
  static const double toolPanelItemLabelLineHeight = 14.0;
  /// 滤镜模板卡片预览图尺寸（正方形，与底部栏高一致便于一行展示）
  static const double filterTemplatePreviewSize = bottomNavHeight + intraGroupMd;
  /// 滤镜模板名称色块高度（图下标签条）
  static const double filterTemplateLabelBarHeight = buttonHeightXs;
  /// 滤镜模板卡片单项宽度（预览 + 与专业工具一致的组间间距）
  static const double filterTemplateItemWidth = filterTemplatePreviewSize + interGroupLg;
  /// 滤镜模板卡片之间的水平间距
  static const double filterTemplateItemGap = intraGroupSm;
  /// 滤镜分类标签之间的水平间距（较原方案更舒展）
  static const double filterCategoryChipGap = interGroupSm;
  /// 滤镜模板跨分类分段间距（约为常规模板间距的两倍）
  static const double filterTemplateCategoryGap = filterTemplateItemGap * 2;
  /// 滤镜分类分组间距（同组间距约2x）
  static const double filterCategoryGroupGap = interGroupMd;
  /// 滤镜模板横向滚动步长（单项宽度 + 项间距）
  static const double filterTemplateItemExtent =
      filterTemplateItemWidth + filterTemplateItemGap;
  /// 功能项选中边框线宽（如裁剪比例框）
  static const double toolPanelItemBorderWidthSelected = 2.0;

  /// 视频封面中央播放按钮尺寸（圆形）
  static const double videoPlayOverlaySize = 52.0;
  /// 视频封面中央播放图标尺寸
  static const double videoPlayOverlayIconSize = 22.0;
  /// 功能项未选中边框线宽
  static const double toolPanelItemBorderWidthUnselected = 1.0;

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

  static double responsiveValue(
    BuildContext context, {
    required double compact,
    required double regular,
    required double expanded,
  }) {
    final width = MediaQuery.sizeOf(context).width;
    if (width < compactBreakpoint) return compact;
    if (width >= expandedBreakpoint) return expanded;
    return regular;
  }
}
