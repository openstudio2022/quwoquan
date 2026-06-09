import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';

/// 应用间距常量
/// 根据设计规则文档 (03_DESIGN_RULES.md) 定义
class AppSpacing {
  // ==================== 扩展语义尺寸（用于记录页面去字面量） ====================
  /// 占位/未测量维度（如媒体元数据占位）
  static const double zero = 0.0;
  static const double one = 1.0;
  static const double hairline = 0.5;
  static const double two = 2.0;
  static const double oneHalf = 1.5;
  static const double six = 6.0;
  static const double twoPointFour = 2.4;
  static const double three = 3.0;
  static const double seven = 7.0;
  static const double ten = 10.0;
  static const double fourteen = 14.0;
  static const double eighteen = 18.0;
  static const double twenty = 20.0;
  static const double thirtySix = 36.0;
  static const double twentyEight = 28.0;
  static const double forty = 40.0;
  static const double oneHundred = 100.0;
  static const double twoHundredTwenty = 220.0;
  static const double threeHundredTwenty = 320.0;
  static const double radiusTwo = 2.0;
  static const double radiusTen = 10.0;
  static const double radiusEighteen = 18.0;
  static const double radiusTwenty = 20.0;
  static const double radiusTwentyEight = 28.0;
  static const double radiusThirtyTwo = 32.0;
  static const double radiusNinetyNine = 99.0;

  // ==================== 响应式断点 ====================
  static const double compactBreakpoint = 360.0;
  static const double expandedBreakpoint = 600.0;
  static const double wideBreakpoint = 1024.0;

  /// Web/桌面公开内容入口布局语义尺寸。
  static const double webContentMaxWidth = 1120.0;
  static const double webInstallBannerCompactHeight = 72.0;
  static const double webInstallBannerWideHeight = 56.0;
  static const double webNavigationRailWidth = 96.0;
  static const double webPcHeaderHeight = 64.0;
  static const double webPcToolbarBrandSlotWidth = 96.0;
  static const double webPcToolbarBrandIconSize = 20.0;
  static const double webPcToolbarActionSize = 36.0;
  static const double webPcToolbarActionIconSize = 18.0;
  static const double webPcMasonryColumnWidth = 236.0;
  static const double webPcMasonryGap = 20.0;
  static const double webPcReadingMinWidth = 720.0;
  static const double webPcReadingMaxWidth = 820.0;
  static const double webPcRightRailWidth = 240.0;
  static const double webPcInstallCtaCardWidth = 260.0;
  static const double webPcShellMaxWidth = 1320.0;

  /// 宽屏认证态页面（消息/我的/设置/更多）统一的内容最大宽度。
  /// 中间内容区固定该宽度并居中，左右用 page background 填充以区分阅读区。
  static const double webPageContentMaxWidth = 860.0;
  static const double webPcSearchMinWidth = 320.0;
  static const double webPcSearchMaxWidth = 460.0;
  static const double webPcWelcomeHeroHeight = 144.0;
  static const double webPcWelcomeVisualDiameter = 88.0;
  static const double webPcDownloadQrSize = 64.0;
  static const double webPcCreateCardWidth = 260.0;
  static const double webPcFeedCardWidth = 220.0;
  static const double webPcHeroCardHeight = 240.0;
  static const double webPcFeedCardImageHeight = 124.0;
  static const double webPcContextTabSelectedIndicatorWidth = 20.0;
  static const double webPcContextTabIndicatorHeight = 2.0;
  static const double webPcHeroPinnedProgressDistance = 360.0;
  static const double webPcHeroParallaxDistance = 32.0;
  static const double webPcToolbarElevationBlurRadius = 18.0;
  static const double webPcLoginSurfaceWidth = 440.0;
  static const double webPcLoginSurfaceMaxHeight = 720.0;
  static const double webPcLoginSurfaceBackdropBlur = 18.0;
  static const double webPcLoginSurfaceInset = 40.0;
  static const int webPcFeedPreviewItemLimit = 12;
  static const Duration webPcContextTabSwitchDuration = Duration(
    milliseconds: 180,
  );
  static const Duration webPcScrollToContentDuration = Duration(
    milliseconds: 360,
  );
  static const Duration webPcLoginSurfaceDuration = Duration(milliseconds: 220);

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

  /// 首页统一对象推荐卡最大宽度（横滑流内单卡上限，避免过宽）。
  static const double homeObjectCardMaxWidth = 260.0;
  /// 首页统一对象推荐卡横滑流固定高度（含两行文案 + 行动按钮触控余量）。
  static const double homeObjectCardRailHeight = 88.0;
  static const double objectIntersectionCardWideWidth = 132.0;
  static const double objectIntersectionCardWideCoverHeight = 92.0;
  // ==================== 文本行高语义 ====================
  /// 单行紧凑标题/标签（line height 倍数 1.0）
  static const double textLineHeightSingle = 1.0;

  /// 紧凑文案行高，适用于 badge / 紧凑标签
  static const double textLineHeightCompact = 1.2;

  /// 极紧标题行高，适用于用户名/时间等单行紧凑排版
  static const double textLineHeightDense = 1.02;

  /// 默认正文行高，适用于表单与说明文案
  static const double textLineHeightBody = 1.35;

  /// 宽松正文行高，适用于 feed 文本内容
  static const double textLineHeightBodyRelaxed = 1.36;

  /// 标题行高，适用于中大字号标题
  static const double textLineHeightHeadline = 1.4;

  /// 标签/说明行高，适用于 footnote / caption
  static const double textLineHeightLabel = 1.5;

  /// 长文正文行高，适用于文章分页阅读场景
  static const double textLineHeightArticleBody = 1.82;

  /// 辅助文案行高，适用于 footnote 级别的说明文本
  static const double textLineHeightFootnote = 1.3;

  /// 角标说明行高，适用于 caption 级别的短说明文本
  static const double textLineHeightCaption = 1.25;

  /// 获取文案按钮内边距（按断点适配，不受容器约束）
  static EdgeInsets buttonPadding(BuildContext context, String size) {
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
  static EdgeInsets buttonPaddingCompact(BuildContext context, String size) {
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

  /// 横向头像栏高度
  static const double avatarRailHeight = 90.0;

  // ==================== 欢迎页动效（Figma WelcomeScreen） ====================
  static const double welcomeGraphicDiameter = 256.0;
  static const double welcomePetalWidth = 52.0;
  static const double welcomePetalHeight = 94.0;
  static const double welcomePetalRadialOffset = 54.0;

  /// 花瓣下层径向柔光直径（羽化至透明，提亮花心叠色区；刻意避开早前「独立光圈」像素断言）。
  static const double welcomeBloomDiameter = 92.0;

  /// 圈子头像圆角比例（border-radius: 20%）
  static const double avatarCircleBorderRadiusRatio = 0.2;

  /// 底部导航高度: 56.0
  static const double bottomNavHeight = 56.0;

  /// 标签导航高度: 48.0
  static const double tabNavigationHeight = 48.0;

  /// 主壳顶部一级 Tab 栏的响应式高度。
  /// 手机优先节省垂直空间（44），平板/宽屏保持 48，让顶部工具栏离手机
  /// 状态栏的视觉间距与底部导航的上下留白对齐。
  static double primaryTopBarHeight(BuildContext context) =>
      responsiveValue(context, compact: 44.0, regular: 44.0, expanded: 48.0);

  /// 顶部一级工具栏在挖孔/灵动岛机型上的安全区压缩值。
  /// Tab 容器上半段延伸入安全区，使 label 上边缘与圈子搜索框顶部对齐
  /// （均距安全区底线 xs 呼吸间距），视觉上 label 紧贴安全区。
  static double primaryTopBarSafeTopInset(
    double safeTop,
    BuildContext context,
  ) {
    if (safeTop <= zero) {
      return zero;
    }
    final labelTopPadding =
        (primaryTopBarHeight(context) - _primaryTabFontSize) / 2;
    return (safeTop - labelTopPadding + xs).clamp(zero, safeTop);
  }

  static const double _primaryTabFontSize = 14.0;

  /// 主壳底部导航的响应式内容区高度（icon + gap + label 区域）。
  /// 手机紧凑 50（与 iOS CupertinoTabBar 标准一致），平板/宽屏保持 56。
  static double bottomNavBarHeight(BuildContext context) =>
      responsiveValue(context, compact: 50.0, regular: 50.0, expanded: 56.0);

  /// 工具栏统一上下内边距。
  /// 顶部/底部工具栏共享，让间距与顶部工具栏 label-to-underline 视觉距离一致。
  /// compact = xs(4)，保证图标紧凑不浪费垂直空间。
  static double toolbarVerticalPadding(BuildContext context) =>
      responsiveValue(context, compact: xs, regular: sm, expanded: sm);

  /// 应用级顶部 chrome 安全区入口，复用一级 Tab 的压缩安全区算法。
  static double appChromeTopSafeInset(double safeTop, BuildContext context) =>
      primaryTopBarSafeTopInset(safeTop, context);

  /// 应用级顶部 chrome 高度，所有一级顶栏/沉浸顶栏共享。
  static double appChromeTopBarHeight(BuildContext context) =>
      primaryTopBarHeight(context);

  /// 媒体可铺进状态栏的最大宽高比；竖图/方图可沉浸，宽横图保留安全区。
  static const double immersiveStatusBarMaxAspectRatio = one;

  /// 普通导航栏 chrome 高度（CupertinoNavigationBar / Inset / 内页）。
  static const double appChromeNavigationBarHeight = toolbarHeight;

  /// 应用级 toolbar 纵向节奏，顶部按钮行与底部动作栏共享。
  static double appChromeToolbarVerticalPadding(BuildContext context) =>
      toolbarVerticalPadding(context);

  /// 应用级 toolbar 操作按钮热区。
  static const double appChromeActionButtonSize = minInteractiveSize;

  /// 应用级 toolbar 操作图标尺寸。
  static const double appChromeActionIconSize = iconMedium;

  /// 全局「小趣」入口品牌圆标直径，与搜索等顶栏图标保持同一视觉尺寸。
  static const double globalAssistantEntryMarkSize = appChromeActionIconSize;

  /// 全局「小趣」入口圆标内星光尺寸，首页、消息、我的主页保持一致。
  static const double globalAssistantEntryGlyphSize = iconSmall;

  /// 全局「小趣」入口圆标与文字标签的垂直间距，与底部导航图标/文字节奏一致。
  static const double globalAssistantEntryLabelGap = bottomNavIconLabelGap;

  /// 首页「小趣搜」搜索框高度，与 iOS 最小可触控高度对齐。
  static const double globalSearchFieldHeight = minInteractiveSize;

  /// 顶栏文字操作最小热区高度。
  static const double appChromeTextActionMinHeight = appChromeActionButtonSize;

  /// 顶栏文字操作水平内边距。
  static const double appChromeTextActionHorizontalPadding = containerXs;

  /// 应用级 toolbar 操作组内间距。
  static double appChromeActionGap(BuildContext context) => responsiveValue(
    context,
    compact: intraGroupXs,
    regular: intraGroupSm,
    expanded: intraGroupSm,
  );

  /// 底部 chrome 在圆弧/Home Indicator 机型上的额外左右保护。
  static double appChromeBottomSafeSideInset(
    BuildContext context,
    double bottomSafeInset,
  ) => bottomNavContentSideInset(context, bottomSafeInset);

  /// 对话输入栏单行默认中心槽高度。
  static const double chatInputToolbarMinHeight = appChromeActionButtonSize;

  /// 对话输入栏外层上下留白，保持默认单行状态轻量。
  static const double chatInputToolbarVerticalPadding = xs;

  /// 对话输入栏图标按钮热区。
  static const double chatInputIconButtonSize = appChromeActionButtonSize;

  /// 对话输入栏发送按钮直径。
  static const double chatInputSendButtonSize = appChromeActionButtonSize;

  /// 评论输入默认高度，与对话输入单行槽一致。
  static const double commentInputHeight = chatInputToolbarMinHeight;

  /// 侵入式分屏评论区默认占屏高比例（评论区 2/3，媒体区 1/3）。
  static const double immersiveCommentSheetRatio = 0.66;

  /// 侵入式分屏评论区可拖拽的最小/最大占屏高比例。
  static const double immersiveCommentSheetMinRatio = 0.5;
  static const double immersiveCommentSheetMaxRatio = 0.9;

  /// 评论输入浮层多行输入框默认两行高度与最多五行高度。
  static const double commentComposerMinHeight = 64.0;
  static const double commentComposerMaxHeight = 132.0;

  /// 评论输入浮层最近 emoji 横条高度。
  static const double commentComposerRecentEmojiHeight = 44.0;

  /// 评论输入浮层底部单张图片缩略图边长。
  static const double commentAttachmentThumbnailSize = 72.0;

  /// 评论缩略图删除角标图标尺寸。
  static const double iconXSmall = 12.0;

  /// 评论列表虚拟化缓存高度（约一屏评论高度）。
  static const double commentListCacheExtent = 520.0;

  /// 简版媒体底栏内容区高度。
  static double mediaBottomBarHeight(BuildContext context) =>
      bottomNavBarHeight(context);

  /// 主壳底部导航条左右内收量（让 tab 项与机身底部圆角/曲面屏对齐）。
  static double bottomNavSideInset(BuildContext context) => responsiveValue(
    context,
    compact: containerXs,
    regular: zero,
    expanded: zero,
  );

  /// 底部导航在存在 home indicator/底部圆角时的内容左右保护量。
  /// 通过加大左右留白，允许内容在垂直方向上与底部安全区做对称收口。
  static double bottomNavContentSideInset(
    BuildContext context,
    double bottomSafeInset,
  ) {
    final baseInset = bottomNavSideInset(context);
    if (bottomSafeInset <= zero) {
      return baseInset;
    }
    return baseInset +
        responsiveValue(
          context,
          compact: containerXs,
          regular: containerSm,
          expanded: containerMd,
        );
  }

  /// 子标签导航高度: 44.0
  static const double subTabNavigationHeight = 44.0;

  /// 一级 Tab 芯片基准宽度（居中滚动 Tab 栏用；2 CJK 字 ≈ 32px + 触控余量 ≥ minInteractiveSize）
  static const double tabChipBaseWidth = 48.0;

  /// 视频沉浸模式下一级 Tab 芯片宽度（略大，避免「视频」等两字被裁切、只显示「视」亮色）
  static const double tabChipBaseWidthVideoImmersion = 64.0;

  /// 一级 Tab 芯片间距（首页/趣信/作者主页统一，精选带下拉位时只允许略增视觉宽度）
  static const double primaryTabChipGap = interGroupXs;

  /// 一级 Tab 常规文本左右安全留白，统一首页/趣信/作者主页的触控与视觉节奏。
  static double primaryTabSlotSidePadding(BuildContext context) =>
      responsiveValue(
        context,
        compact: intraGroupSm,
        regular: intraGroupSm,
        expanded: interGroupXs,
      );

  /// 一级 Tab 组间距语义。首页、趣信、作者主页都走同一套值，不再按页面例外处理。
  static double primaryTabGroupGap(BuildContext context) => responsiveValue(
    context,
    compact: intraGroupSm,
    regular: interGroupXs,
    expanded: ten,
  );

  /// 首页「精选」等带选项入口的一级 Tab 预留附件位，保证位置稳定但不过度拉大间距。
  static double primaryTabAccessoryReserve(BuildContext context) =>
      responsiveValue(
        context,
        compact: ten,
        regular: containerSm,
        expanded: fourteen,
      );

  /// 一级 Tab 选中下划线统一厚度。
  static const double primaryTabUnderlineHeight = 2.0;

  /// 一级 Tab 居中判定容差：允许轻微文案变化仍保持同一锚点布局，避免模式切换跳变。
  static const double primaryTabAnchorTolerance = 6.0;

  /// 发现页一级 Tab 左右锚点最小占位宽度（用于两侧动作位对称，避免视觉中轴漂移）。
  static const double discoveryHeaderSideAnchorMinWidth = 60.0;

  /// 顶部右侧操作入口的视觉右边距。
  /// 统一首页、趣聊与圈子频道管理按钮的安全热区，避免贴边导致曲面屏难点。
  static double topBarTrailingVisualInset(BuildContext context) =>
      responsiveValue(
        context,
        compact: containerMd,
        regular: containerMd,
        expanded: containerLg,
      );

  /// 顶部右侧操作入口热区的实际定位值。
  /// 通过把 44x44 热区整体向内收，让 24px 图标的视觉右边距稳定对齐。
  static double topBarTrailingButtonInset(BuildContext context) {
    final inset =
        topBarTrailingVisualInset(context) -
        ((minInteractiveSize - iconMedium) / 2);
    return inset < 0 ? 0 : inset;
  }

  /// 顶部右侧以「小趣」圆标作为最右视觉对象时的热区定位值。
  static double topBarTrailingAssistantButtonInset(BuildContext context) {
    final inset =
        topBarTrailingVisualInset(context) -
        ((minInteractiveSize - globalAssistantEntryMarkSize) / 2);
    return inset < 0 ? 0 : inset;
  }

  /// 二级 Tab 组间距语义。趣信、作者主页与其他二级筛选统一使用。
  static double secondaryTabGap(BuildContext context) => responsiveValue(
    context,
    compact: intraGroupXs,
    regular: intraGroupSm,
    expanded: interGroupXs,
  );

  /// 二级 Tab 胶囊内部横向留白。
  static double secondaryTabChipHorizontalPadding(BuildContext context) =>
      responsiveValue(
        context,
        compact: ten,
        regular: containerSm,
        expanded: fourteen,
      );

  /// 二级 Tab 胶囊内部纵向留白。
  static double secondaryTabChipVerticalPadding(BuildContext context) =>
      responsiveValue(
        context,
        compact: intraGroupXs,
        regular: intraGroupXs,
        expanded: intraGroupSm,
      );

  /// 二级 Tab 条整体上下留白。
  static double secondaryTabBarVerticalPadding(BuildContext context) =>
      responsiveValue(
        context,
        compact: intraGroupXs,
        regular: intraGroupXs,
        expanded: intraGroupSm,
      );

  /// 发现/圈子内容区左右边距（微趣、文章、图片宫格、圈子各 tab 页统一使用）
  static double feedContentHorizontal(BuildContext context) => getSpacing(
    DesignSemanticConstants.container,
    DesignSemanticConstants.xs,
    context: context,
  );

  /// 关注流/作者主页等主内容区的手机/窄屏基准最大宽度语义。
  static const double feedMaxContentWidth = 720.0;

  /// Post 预览卡片统一外边距/列表区边距语义。
  static const double postPreviewSectionPadding = containerXs;

  /// Post 预览网格统一卡片间距语义。
  static const double postPreviewGridSpacing = intraGroupMd;

  /// Post 预览卡片统一内边距语义。
  static const double postPreviewCardPadding = sm;

  /// Post 与圈子封面等内容预览统一圆角语义。
  static const double contentPreviewCornerRadius = borderRadius;

  /// Post 预览卡片统一圆角语义。
  static const double postPreviewCornerRadius = contentPreviewCornerRadius;

  /// 作者主页背景基础高度：默认保持约 1/4 屏高。
  static const double profileHeaderBaseHeightRatio = 0.25;

  /// 作者主页下拉拉伸上限：可拉升到约 1/2 屏高。
  static const double profileHeaderMaxStretchHeightRatio = 0.5;

  /// 顶部工具栏高度（常规）
  static const double toolbarHeight = 56.0;

  /// 底部工具栏最小触控高度
  static const double toolbarMinTouchHeight = 48.0;

  /// 模态框头部高度: 56.0
  static const double modalHeaderHeight = 56.0;

  /// 创作入口抽屉最大高度比例 (67vh)
  static const double createEntrySheetMaxHeightRatio = 0.67;

  /// 全局非全屏底部面板的最大高度比例。
  /// 创作、更多功能、评论等均按内容自适应，超过此值后内部滚动。
  static const double modalSheetMaxHeightRatio = 0.82;

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

  /// 底部导航中间创作按钮圆形直径，靠主色突出而不高于普通项视觉块。
  static const double primaryActionCircleSize = 32.0;

  /// 底部导航普通项图标尺寸，保持当前主壳视觉基线。
  static const double bottomNavItemIconSize = 22.0;

  /// 底部导航主操作内图标尺寸。
  static const double bottomNavPrimaryActionIconSize = 18.0;

  /// 底部导航图标与标签间距，保留小幅呼吸感。
  static const double bottomNavIconLabelGap = six;

  /// 底部导航标签字距。
  static const double bottomNavLabelLetterSpacing = -0.08;

  /// 底部导航主操作阴影垂直偏移。
  static const double bottomNavPrimaryActionShadowOffsetDy = two;

  /// 沉浸媒体底栏作者头像尺寸，三档统一避免压过动作列。
  static double immersiveEngagementAvatarSize(BuildContext context) =>
      responsiveValue(
        context,
        compact: avatarUserSm,
        regular: avatarUserSm,
        expanded: avatarUserSm,
      );

  /// 沉浸媒体底栏动作标签字号，与主壳底栏 label 基线一致。
  static const double immersiveEngagementActionLabelSize = 11.0;

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
  static const double filterTemplatePreviewSize =
      bottomNavHeight + intraGroupMd;

  /// 滤镜模板名称色块高度（图下标签条）
  static const double filterTemplateLabelBarHeight = buttonHeightXs;

  /// 滤镜模板卡片单项宽度（预览 + 与专业工具一致的组间间距）
  static const double filterTemplateItemWidth =
      filterTemplatePreviewSize + interGroupLg;

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
  static Map<String, Map<String, double>> _getResponsiveSpacingMap(
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

  static double responsiveWideValue(
    BuildContext context, {
    required double compact,
    required double regular,
    required double expanded,
    required double wide,
  }) {
    final width = MediaQuery.sizeOf(context).width;
    if (width >= wideBreakpoint) return wide;
    if (width >= expandedBreakpoint) return expanded;
    if (width < compactBreakpoint) return compact;
    return regular;
  }

  static bool isWideLayout(BuildContext context) =>
      MediaQuery.sizeOf(context).width >= wideBreakpoint;

  static double webInstallBannerHeight(BuildContext context) =>
      responsiveWideValue(
        context,
        compact: webInstallBannerCompactHeight,
        regular: webInstallBannerCompactHeight,
        expanded: webInstallBannerCompactHeight,
        wide: webInstallBannerWideHeight,
      );

  static EdgeInsets webShellContentPadding(BuildContext context) =>
      EdgeInsets.symmetric(
        horizontal: responsiveWideValue(
          context,
          compact: containerXs,
          regular: containerSm,
          expanded: containerMd,
          wide: containerLg,
        ),
      );

  static int webPcMasonryColumns(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final horizontalPadding = webShellContentPadding(context).horizontal;
    final usable = (width - horizontalPadding).clamp(0, webContentMaxWidth);
    final columnAndGap = webPcMasonryColumnWidth + webPcMasonryGap;
    final columns = ((usable + webPcMasonryGap) / columnAndGap).floor();
    return columns.clamp(2, 5).toInt();
  }

  static double webPcReadingWidth(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final horizontalPadding = webShellContentPadding(context).horizontal;
    final usable = (width - horizontalPadding).clamp(0, webContentMaxWidth);
    return usable.clamp(webPcReadingMinWidth, webPcReadingMaxWidth).toDouble();
  }

  // ==================== 响应式内容网格 ====================

  /// 宽屏主页/圈子页主内容最大宽度：窄屏沿用基准宽，宽屏与背景层同宽铺满。
  static double adaptiveFeedMaxContentWidth(double availableWidth) {
    if (availableWidth <= feedMaxContentWidth) {
      return feedMaxContentWidth;
    }
    return availableWidth;
  }

  /// Post 预览网格的最佳列宽（理想单列内容宽度），用于计算列数。
  static const double _gridIdealColumnWidth = 220.0;

  /// Post 预览网格的最小列数。
  static const int gridMinColumns = 2;

  /// Post 预览网格的最大列数，避免 iPad/桌面出现 5-6 列的过密卡片。
  static const int gridMaxColumns = 4;

  /// 根据可用宽度计算 Post 预览瀑布流/宫格列数。
  /// 保证至少 [gridMinColumns] 列，并限制不超过 [gridMaxColumns]。
  static int responsiveGridColumns(
    BuildContext context, {
    double? availableWidth,
  }) {
    final width = availableWidth ?? MediaQuery.sizeOf(context).width;
    final usable = width - feedContentHorizontal(context) * 2;
    final cols = (usable / _gridIdealColumnWidth).floor();
    return cols.clamp(gridMinColumns, gridMaxColumns).toInt();
  }

  /// 关注流在宽屏下的列数（单列微博风格 → 多列卡片流过渡）。
  /// 手机始终单列；平板及以上复用 Post 预览网格列数，并继承最大列数上限。
  static int feedResponsiveColumns(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width < expandedBreakpoint) return 1;
    return responsiveGridColumns(context, availableWidth: width);
  }
}
