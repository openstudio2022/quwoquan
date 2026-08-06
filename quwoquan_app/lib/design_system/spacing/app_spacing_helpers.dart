part of 'app_spacing.dart';

final Map<String, Map<String, double>> _appSpacingSemantic = {
  // 组内间距 (intraGroup) - 同一组内相关元素之间
  DesignSemanticConstants.intraGroup: {
    DesignSemanticConstants.xs: 4.0, // Mobile: 4px - 紧密标签组
    DesignSemanticConstants.sm: 6.0, // Mobile: 6px - 标签组、按钮组
    DesignSemanticConstants.md: 8.0, // Mobile: 8px - 表单项、列表项
    DesignSemanticConstants.lg: 12.0, // Mobile: 12px - 卡片内容
    DesignSemanticConstants.xl: 16.0, // Mobile: 16px - 宽松布局
  },

  // 组间间距 (interGroup) - 不同组之间
  DesignSemanticConstants.interGroup: {
    DesignSemanticConstants.xs: 8.0, // Mobile: 8px - 紧密相关组
    DesignSemanticConstants.sm: 12.0, // Mobile: 12px - 相关组
    DesignSemanticConstants.md: 16.0, // Mobile: 16px - 一般组
    DesignSemanticConstants.lg: 24.0, // Mobile: 24px - 独立组
    DesignSemanticConstants.xl: 32.0, // Mobile: 32px - 页面区块
  },

  // 容器间距 (container) - 容器内边距
  DesignSemanticConstants.container: {
    DesignSemanticConstants.xs: 8.0, // Mobile: 8px - 极小容器
    DesignSemanticConstants.sm: 12.0, // Mobile: 12px - 小容器
    DesignSemanticConstants.md: 16.0, // Mobile: 16px - 中等容器
    DesignSemanticConstants.lg: 20.0, // Mobile: 20px - 大容器
    DesignSemanticConstants.xl: 24.0, // Mobile: 24px - 超大容器
  },
};

EdgeInsets _appSpacingButtonPadding(BuildContext context, String size) {
  final horizontal = _appSpacingGetSpacing(
    DesignSemanticConstants.container,
    size == DesignSemanticConstants.lg
        ? DesignSemanticConstants.lg
        : DesignSemanticConstants.md,
    context: context,
  );
  final vertical = _appSpacingGetSpacing(
    DesignSemanticConstants.intraGroup,
    size == DesignSemanticConstants.lg
        ? DesignSemanticConstants.sm
        : DesignSemanticConstants.xs,
    context: context,
  );
  return EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical);
}

double _appSpacingButtonHeightForSize(String size) {
  switch (size) {
    case DesignSemanticConstants.xs:
      return AppSpacing.buttonHeightXs;
    case DesignSemanticConstants.sm:
      return AppSpacing.buttonHeightSm;
    case DesignSemanticConstants.lg:
      return AppSpacing.buttonHeightLg;
    case DesignSemanticConstants.md:
    default:
      return AppSpacing.buttonHeightMd;
  }
}

EdgeInsets _appSpacingButtonPaddingCompact(BuildContext context, String size) {
  final horizontal = _appSpacingGetSpacing(
    DesignSemanticConstants.container,
    size == DesignSemanticConstants.lg
        ? DesignSemanticConstants.sm
        : DesignSemanticConstants.xs,
    context: context,
  );
  final vertical = _appSpacingGetSpacing(
    DesignSemanticConstants.intraGroup,
    DesignSemanticConstants.xs,
    context: context,
  );
  return EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical);
}

double _appSpacingButtonHeightForSizeCompact(String size) {
  switch (size) {
    case DesignSemanticConstants.xs:
      return AppSpacing.buttonHeightXs;
    case DesignSemanticConstants.sm:
      return AppSpacing.buttonHeightSmCompact;
    case DesignSemanticConstants.lg:
      return AppSpacing.buttonHeightLgCompact;
    case DesignSemanticConstants.md:
    default:
      return AppSpacing.buttonHeightMdCompact;
  }
}

double _appSpacingTopBarTrailingButtonInset(BuildContext context) {
  final inset =
      AppSpacing.topBarTrailingVisualInset(context) -
      ((AppSpacing.minInteractiveSize - AppSpacing.iconMedium) / 2);
  return inset < 0 ? 0 : inset;
}

double _appSpacingTopBarTrailingAssistantButtonInset(BuildContext context) {
  final inset =
      AppSpacing.topBarTrailingVisualInset(context) -
      ((AppSpacing.minInteractiveSize -
              AppSpacing.globalAssistantEntryMarkSize) /
          2);
  return inset < 0 ? 0 : inset;
}

double _appSpacingAdaptiveProfileHeaderBaseHeightRatio(BuildContext context) {
  final size = MediaQuery.sizeOf(context);
  if (size.width >= AppSpacing.expandedBreakpoint) {
    return AppSpacing.profileHeaderWideBaseHeightRatio;
  }
  final aspect = size.height / size.width;
  if (aspect >= AppSpacing.profileHeaderTallScreenAspectRatio) {
    return AppSpacing.profileHeaderTallBaseHeightRatio;
  }
  return AppSpacing.profileHeaderBaseHeightRatio;
}

double _appSpacingAdaptiveProfileHeaderMaxStretchHeightRatio(
  BuildContext context,
) {
  if (MediaQuery.sizeOf(context).width >= AppSpacing.expandedBreakpoint) {
    return AppSpacing.profileHeaderWideMaxStretchHeightRatio;
  }
  return AppSpacing.profileHeaderMaxStretchHeightRatio;
}

double _appSpacingGetSpacing(
  String semanticType,
  String size, {
  BuildContext? context,
  String? screenType,
}) {
  // 如果指定了screenType，使用指定类型
  if (screenType != null) {
    return _appSpacingGetSpacingForScreenType(semanticType, size, screenType);
  }

  // 如果有context，自动检测屏幕类型
  if (context != null) {
    final screenWidth = MediaQuery.of(context).size.width;
    final detectedType = _appSpacingDetectScreenType(screenWidth);
    return _appSpacingGetSpacingForScreenType(semanticType, size, detectedType);
  }

  // 默认返回Mobile屏幕的间距（基础值）
  return _appSpacingSemantic[semanticType]?[size] ??
      _appSpacingGetDefaultSpacing(size);
}

double _appSpacingGetSpacingForScreenType(
  String semanticType,
  String size,
  String screenType,
) {
  // 响应式间距映射表（根据设计规则文档）
  final responsiveMap = _appSpacingGetResponsiveSpacingMap(screenType);
  return responsiveMap[semanticType]?[size] ??
      _appSpacingSemantic[semanticType]?[size] ??
      _appSpacingGetDefaultSpacing(size);
}

String _appSpacingDetectScreenType(double screenWidth) {
  if (screenWidth < 768) {
    return 'mobile';
  } else if (screenWidth < 1024) {
    return 'tablet';
  } else {
    return 'desktop';
  }
}

Map<String, Map<String, double>> _appSpacingGetResponsiveSpacingMap(
  String screenType,
) {
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
      return _appSpacingSemantic;
  }
}

double _appSpacingGetDefaultSpacing(String size) {
  switch (size) {
    case DesignSemanticConstants.xs:
      return AppSpacing.xs;
    case DesignSemanticConstants.sm:
      return AppSpacing.sm;
    case DesignSemanticConstants.md:
      return AppSpacing.md;
    case DesignSemanticConstants.lg:
      return AppSpacing.lg;
    case DesignSemanticConstants.xl:
      return AppSpacing.xl;
    default:
      return AppSpacing.md;
  }
}

double _appSpacingResponsiveValue(
  BuildContext context, {
  required double compact,
  required double regular,
  required double expanded,
}) {
  final width = MediaQuery.sizeOf(context).width;
  if (width < AppSpacing.compactBreakpoint) return compact;
  if (width >= AppSpacing.expandedBreakpoint) return expanded;
  return regular;
}

double _appSpacingResponsiveWideValue(
  BuildContext context, {
  required double compact,
  required double regular,
  required double expanded,
  required double wide,
}) {
  final width = MediaQuery.sizeOf(context).width;
  if (width >= AppSpacing.wideBreakpoint) return wide;
  if (width >= AppSpacing.expandedBreakpoint) return expanded;
  if (width < AppSpacing.compactBreakpoint) return compact;
  return regular;
}

int _appSpacingWebPcMasonryColumns(BuildContext context) {
  final width = MediaQuery.sizeOf(context).width;
  final horizontalPadding = AppSpacing.webShellContentPadding(
    context,
  ).horizontal;
  final usable = (width - horizontalPadding).clamp(
    0,
    AppSpacing.webContentMaxWidth,
  );
  final columnAndGap =
      AppSpacing.webPcMasonryColumnWidth + AppSpacing.webPcMasonryGap;
  final columns = ((usable + AppSpacing.webPcMasonryGap) / columnAndGap)
      .floor();
  return columns.clamp(2, 5).toInt();
}

double _appSpacingWebPcReadingWidth(BuildContext context) {
  final width = MediaQuery.sizeOf(context).width;
  final horizontalPadding = AppSpacing.webShellContentPadding(
    context,
  ).horizontal;
  final usable = (width - horizontalPadding).clamp(
    0,
    AppSpacing.webContentMaxWidth,
  );
  return usable
      .clamp(AppSpacing.webPcReadingMinWidth, AppSpacing.webPcReadingMaxWidth)
      .toDouble();
}

double _appSpacingAdaptiveFeedMaxContentWidth(double availableWidth) {
  if (availableWidth <= AppSpacing.feedMaxContentWidth) {
    return AppSpacing.feedMaxContentWidth;
  }
  return availableWidth;
}

int _appSpacingResponsiveGridColumns(
  BuildContext context, {
  double? availableWidth,
}) {
  final width = availableWidth ?? MediaQuery.sizeOf(context).width;
  final usable = width - AppSpacing.feedContentHorizontal(context) * 2;
  final cols = (usable / AppSpacing._gridIdealColumnWidth).floor();
  return cols
      .clamp(AppSpacing.gridMinColumns, AppSpacing.gridMaxColumns)
      .toInt();
}

int _appSpacingFeedResponsiveColumns(BuildContext context) {
  final width = MediaQuery.sizeOf(context).width;
  if (width < AppSpacing.expandedBreakpoint) return 1;
  return _appSpacingResponsiveGridColumns(context, availableWidth: width);
}
