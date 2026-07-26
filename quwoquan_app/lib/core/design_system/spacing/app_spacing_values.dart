part of 'app_spacing.dart';

class AppSpacing {
  // ==================== 扩展语义尺寸（用于记录页面去字面量） ====================
  /// 占位/未测量维度（如媒体元数据占位）
  static const double zero = 0.0, one = 1.0;
  static const double hairline = 0.5, two = 2.0;
  static const double oneHalf = 1.5, six = 6.0;
  static const double twoPointFour = 2.4, three = 3.0;
  static const double seven = 7.0, ten = 10.0;
  static const double fourteen = 14.0, eighteen = 18.0;
  static const double twenty = 20.0, thirtySix = 36.0;
  static const double twentyEight = 28.0, forty = 40.0;
  static const double oneHundred = 100.0, oneHundredSixty = 160.0;
  static const double twoHundredTwenty = 220.0;
  static const double threeHundredTwenty = 320.0, radiusTwo = 2.0;
  static const double radiusTen = 10.0, radiusEighteen = 18.0;
  static const double radiusTwenty = 20.0, radiusTwentyFour = 24.0;
  static const double radiusTwentyEight = 28.0, radiusThirtyTwo = 32.0;
  static const double radiusNinetyNine = 99.0;

  /// RTC 画中画语义尺寸。
  static const double rtcPipWidth = 120.0;
  static const double rtcPipHeight = 160.0;
  static const double rtcPipEdgePadding = 12.0;
  static const double rtcPipInitialTop = 100.0;
  // ==================== 响应式断点 ====================
  static const double compactBreakpoint = 360.0;
  static const double markdownCompactBreakpoint = 420.0;
  static const double expandedBreakpoint = 600.0, wideBreakpoint = 1024.0;

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
  static const double webPcMasonryGap = 20.0, webPcReadingMinWidth = 720.0;
  static const double webPcReadingMaxWidth = 820.0, webPcRightRailWidth = 240.0;
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
  static const double webPcCreateCardWidth = 260.0, webPcFeedCardWidth = 220.0;
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
  static const double xs = 4.0;

  static const double sm = 8.0;

  static const double md = 16.0;

  /// 字段、表单与局部操作错误行的图标和图文间距。
  static const double inlineErrorIconSize = 16.0;
  static const double inlineErrorIconTextGap = 6.0;

  static const double lg = 24.0;

  static const double xl = 32.0;
  // ==================== 组件尺寸 ====================
  static const double buttonSize = 44.0;

  static const double buttonHeight = 48.0;

  static const double largeButtonSize = 48.0;

  static const double smallButtonSize = 32.0;

  /// 两状态登录品牌图标容器尺寸（完整应用图标：蓝底圆角 + 花瓣）。
  static const double loginBrandMarkSize = 64.0;

  /// 两状态登录品牌图标字号。
  static const double loginBrandMarkIconSize = 36.0;

  /// 两状态登录品牌图标圆角（≈ iOS 图标圆角比例 0.2237 * 尺寸）。
  static const double loginBrandMarkRadius = 14.5;

  /// 两状态登录 Account Area 固定高度（容纳加高输入框 + 发码后验证码区，保持各状态等高）。
  /// 收紧到常见 iPhone 安全区一屏可容纳，避免底部"其他方式"被截断或触发滚动。
  static const double loginAccountAreaHeight = 196.0;

  /// 两状态登录已记住账号头像尺寸。
  static const double loginAvatarSize = 72.0;
  static const Duration loginAvatarRevealDuration = webPcLoginSurfaceDuration;

  /// 两状态登录主按钮高度。
  static const double loginPrimaryButtonHeight = 56.0;

  /// 两状态登录其他方式圆形入口尺寸。
  static const double loginOtherMethodSize = 46.0;

  /// 两状态登录其他方式品牌图标字号（微信/QQ/支付宝/手机均为白色字形，圆内视觉较满）。
  static const double loginOtherMethodIconSize = 17.0;

  /// 手机号验证码输入框高度。
  static const double loginPhoneFieldHeight = 56.0;

  /// 验证码单格尺寸。
  static const double loginOtpBoxSize = 48.0;

  /// 验证码单格最小尺寸，窄屏下允许轻微收缩避免横向溢出。
  static const double loginOtpBoxMinSize = 44.0;

  /// 验证码单格间距。
  static const double loginOtpBoxGap = 10.0;

  /// 登录页整体最大内容宽度（iPhone 高保宽度内收敛，iPad/Web 居中）。
  static const double loginFrameMaxWidth = 430.0;

  /// 登录页左右安全边距。
  static const double loginFrameHorizontalPadding = 28.0;

  /// 登录页正文纵向边距。
  static const double loginFrameVerticalPadding = 18.0;

  /// 登录页顶部栏到品牌区距离。
  static const double loginTopBarToHeroGap = 18.0;

  /// 登录页品牌名到标题距离。
  static const double loginBrandToTitleGap = 14.0;

  /// 登录页标题到账号区距离。
  static const double loginHeroToAccountGap = 24.0;

  /// 登录页账号区到主按钮距离。
  static const double loginAccountToButtonGap = 20.0;

  /// 登录页主按钮到协议距离。
  static const double loginButtonToAgreementGap = 20.0;

  /// 登录页协议到其他登录方式距离。
  static const double loginAgreementToOtherGap = 18.0;

  /// 登录页其他方式标题到图标行距离。
  static const double loginOtherTitleToIconsGap = 12.0;

  /// 手机号输入初始态账号区高度，只容纳单行输入框，避免挤压首屏底部入口。
  static const double loginPhoneIdleAccountAreaHeight = loginPhoneFieldHeight;

  /// 登录页输入框圆角。
  static const double loginInputRadius = 18.0;

  /// 登录页验证码格圆角。
  static const double loginOtpBoxRadius = 12.0;

  /// 登录页返回账号态三列其他方式最大宽度。
  static const double loginOtherMethodsThreeColumnWidth = 320.0;
  // ==================== 按钮语义尺寸（小、正常、中、大，不受容器约束） ====================
  static const double buttonHeightXs = 28.0;

  static const double buttonHeightSm = 32.0;

  /// 按钮高度 md: 36.0（与「重置」等次要操作一致）
  static const double buttonHeightMd = 36.0;

  static const double buttonHeightLg = 48.0;

  static const double iconButtonMinSizeSm = 44.0;

  static const double iconButtonMinSizeMd = 64.0;

  /// 统一可点击区域最低标准（WCAG 触控建议）
  static const double minInteractiveSize = 44.0;

  /// 不可恢复异常页：固定内容槽避免版本检查和容器重建状态切换时纵向跳动。
  static const double recoveryContentMaxWidth = 280.0;
  static const double recoveryHorizontalInset = 24.0;
  static const double recoveryTitleSlotHeight = 44.0;
  static const double recoverySubtitleSlotHeight = 52.0;
  static const double recoveryActionSlotHeight = 108.0;
  static const double recoveryTitleSubtitleGap = 16.0;
  static const double recoverySubtitleActionGap = 28.0;
  static const double recoveryButtonGap = 12.0;
  static const double recoveryVisualCenterAlignment = 0.1;
  static const Duration recoveryOldContentFadeDuration = Duration(
    milliseconds: 80,
  );
  static const Duration recoveryNewContentFadeDuration = Duration(
    milliseconds: 120,
  );

  /// 我的主页转发互动行最小高度。
  static const double profileShareInteractionRowMinHeight = 104.0;

  /// 我的主页转发互动头像、未读角标与目标预览。
  static const double profileShareInteractionAvatarSize = 44.0;
  static const double profileShareInteractionUnreadBadgeSize = 18.0;
  static const double profileShareInteractionPreviewSize = 64.0;
  static const double profileShareDirectionSegmentMinWidth = 64.0;

  /// 首页统一对象推荐卡最大宽度（横滑流内单卡上限，避免过宽）。
  static const double homeObjectCardMaxWidth = 260.0;
  static const double chatBubbleMaxWidth = 280.0;
  static const double chatBubbleImageSize = 200.0;
  static const double chatBubbleHorizontalPadding = 24.0;
  static const double chatBubbleRadius = 12.0;
  static const double chatBubbleTailExtent = 8.0;
  static const double chatContactRowHeight = 56.0;

  /// 首页统一对象推荐卡横滑流固定高度（含两行文案 + 行动按钮触控余量）。
  static const double homeObjectCardRailHeight = 88.0;
  static const double homepageIntroductionTimelineDateWidth = 86.0;
  static const double homepageIntroductionHorizontalCardWidth = 180.0;
  static const double homepageIntroductionInlineFigureAspectRatio = 16 / 9;
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
  static EdgeInsets buttonPadding(BuildContext context, String size) =>
      _appSpacingButtonPadding(context, size);

  /// 获取文案按钮高度（固定语义值，不受容器约束）
  static double buttonHeightForSize(String size) =>
      _appSpacingButtonHeightForSize(size);
  // ==================== 按钮紧凑语义（每档尺寸对应更小内边距/高度，用于关注等紧凑场景） ====================
  static const double buttonHeightSmCompact = 26.0;

  static const double buttonHeightMdCompact = 28.0;

  static const double buttonHeightLgCompact = 32.0;

  /// 获取文案按钮内边距（紧凑模式：左右上下更小，语义统一）
  static EdgeInsets buttonPaddingCompact(BuildContext context, String size) =>
      _appSpacingButtonPaddingCompact(context, size);

  /// 获取文案按钮高度（紧凑模式，固定语义值）
  static double buttonHeightForSizeCompact(String size) =>
      _appSpacingButtonHeightForSizeCompact(size);

  /// 头像尺寸: 40.0（向后兼容）
  static const double avatarSize = 40.0;

  /// 小头像尺寸: 32.0（向后兼容）
  static const double smallAvatarSize = 32.0;

  /// 大头像尺寸: 64.0（向后兼容）
  static const double largeAvatarSize = 64.0;
  // ==================== 头像语义尺寸（AVATAR_DESIGN_SYSTEM，Mobile 基准） ====================
  static const double avatarUserXs = 24.0, avatarCircleXs = 24.0;

  static const double avatarUserSm = 32.0, avatarCircleSm = 32.0;

  static const double avatarUserMd = 40.0, avatarCircleMd = 40.0;

  static const double avatarUserLg = 56.0, avatarCircleLg = 56.0;

  static const double avatarUserXl = 72.0, avatarCircleXl = 72.0;

  /// 横向头像栏高度
  static const double avatarRailHeight = 90.0;
  // ==================== 个人主页统计行（关注/粉丝/圈子列表行） ====================
  /// 关系行/圈子行/骨架行的左侧圆形头像直径
  static const double profileStatsRowAvatarSize = 52.0;

  /// 关注按钮骨架占位胶囊宽度
  static const double profileStatsFollowSkeletonWidth = 78.0;

  /// 关注按钮骨架占位胶囊高度
  static const double profileStatsFollowSkeletonHeight = 34.0;
  // ==================== 欢迎页动效（Figma WelcomeScreen） ====================
  static const double welcomeGraphicDiameter = 256.0, welcomePetalWidth = 52.0;
  static const double welcomePetalHeight = 94.0;
  static const double welcomePetalRadialOffset = 54.0;

  /// 图一高保花朵可见直径：约占屏宽 40%，小屏下限 132、上限 168。
  static const double welcomeFlowerWidthFraction = 0.40;
  static const double welcomeFlowerMinDiameter = 132.0;
  static const double welcomeFlowerMaxDiameter = 168.0;

  /// 花朵可见边缘到 slogan 首行的视觉间距（36~44dp 规格取中值）。
  static const double welcomeFlowerSloganVisualGap = 40.0;

  /// 底部品牌名视觉中心距屏底比例（约 90% 屏高）与安全区最小让位。
  static const double welcomeBrandFooterCenterFromBottomFraction = 0.10;
  static const double welcomeBrandFooterSafeAreaGap = 12.0;

  /// 启动提示单行槽位高度与其到品牌名的间距。
  static const double welcomeStartupHintSlotHeight = 24.0;
  static const double welcomeStartupHintToBrandGap = 10.0;

  /// 花瓣下层径向柔光直径（羽化至透明，提亮花心叠色区；刻意避开早前「独立光圈」像素断言）。
  static const double welcomeBloomDiameter = 92.0;

  /// 花蕊外层柔光与中心实心圆直径；欢迎页与全平台应用图标共用。
  static const double welcomeStamenHaloDiameter = 24.0;
  static const double welcomeStamenCoreDiameter = 9.0;

  /// 圈子头像圆角比例（border-radius: 20%）
  static const double avatarCircleBorderRadiusRatio = 0.2;

  /// 底部导航高度: 54.0
  static const double bottomNavHeight = 54.0;

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
  ) => _appSpacingPrimaryTopBarSafeTopInset(safeTop, context);

  static const double _primaryTabFontSize = 14.0;

  /// 主壳底部导航的响应式内容区高度（icon + gap + label 区域）。
  /// 在保留可读性的前提下压紧底栏垂直占位。
  static double bottomNavBarHeight(BuildContext context) => responsiveWideValue(
    context,
    compact: 44.0,
    regular: 46.0,
    expanded: 48.0,
    wide: 52.0,
  );

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
  @Deprecated('评论底栏改用 commentToolbarInputHeight，解耦聊天输入栏高度')
  static const double commentInputHeight = chatInputToolbarMinHeight;

  // ==================== 评论底栏 / 列表语义 token（对标小红书） ====================
  /// 评论底栏只读胶囊输入条高度（低于聊天输入栏，更轻量）。
  static const double commentToolbarInputHeight = thirtySix;

  /// 评论底栏胶囊输入条圆角。
  static const double commentToolbarInputRadius = radiusEighteen;

  /// 评论底栏外层上下留白：36px 胶囊 + 4px*2 = 44px，与消息单行输入栏视觉高度一致。
  static const double commentToolbarVerticalPadding = xs;

  /// 评论底栏右侧赞/转动作图标尺寸。
  static const double commentToolbarActionIconSize = 22.0;

  /// 评论底栏右侧赞/转固定动作列宽。
  static const double commentToolbarActionColumnWidth = 58.0;

  /// 评论底栏右侧赞/转固定热区高度。
  static const double commentToolbarActionHitSize = commentToolbarInputHeight;

  /// 一级评论头像边长（对标小红书一级评论头像）。
  static const double commentAvatarSize = thirtySix;

  /// 二级回复头像边长（较一级更紧凑）。
  static const double commentReplyAvatarSize = twentyEight;

  /// 评论赞/踩单个动作列宽，确保不同数字宽度不推动图标位置。
  static const double commentReactionColumnWidth = 48.0;

  /// 评论赞/踩 group 内距，两个动作需保持紧凑但仍可辨识。
  static const double commentReactionActionGap = two;

  /// 评论赞/踩固定 group 宽度，一级/二级共用同一右边界。
  static const double commentReactionGroupWidth =
      commentReactionColumnWidth * 2 + commentReactionActionGap;

  /// 评论赞/踩计数文本最大宽度（compact 计数最多 4 字符）。
  static const double commentReactionCountWidth = twentyEight;

  /// 评论赞/踩图标尺寸。
  static const double commentReactionIconSize = iconSmall;

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

  /// 一级评论图片附件最大展示宽度（按宽高比护栏布局）。
  static const double commentImageMaxWidth = 220.0;

  /// 二级回复图片附件最大展示宽度（较一级更紧凑）。
  static const double commentReplyImageMaxWidth = 160.0;

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
  ) => _appSpacingBottomNavContentSideInset(context, bottomSafeInset);

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
  static double topBarTrailingButtonInset(BuildContext context) =>
      _appSpacingTopBarTrailingButtonInset(context);

  /// 顶部右侧以「小趣」圆标作为最右视觉对象时的热区定位值。
  static double topBarTrailingAssistantButtonInset(BuildContext context) =>
      _appSpacingTopBarTrailingAssistantButtonInset(context);

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

  /// 对象主页封面基础高度：用户 / 实体 / 圈子主页共用。
  ///
  /// 常规手机约为屏高 21.5%，比旧 1/4 屏更克制；视觉上接近黄金比例
  /// 的小分割节奏（0.236）但为资料卡留出更多首屏信息密度。
  static const double profileHeaderBaseHeightRatio = 0.215;

  /// 对象主页封面在超窄长屏上的基础高度比例。
  static const double profileHeaderTallBaseHeightRatio = 0.205;

  /// 对象主页封面在 expanded / 宽屏上的基础高度比例。
  static const double profileHeaderWideBaseHeightRatio = 0.18;

  /// 对象主页下拉拉伸上限：保留沉浸感，但不再拉到半屏。
  static const double profileHeaderMaxStretchHeightRatio = 0.4;

  /// 对象主页封面在 expanded / 宽屏上的下拉拉伸上限。
  static const double profileHeaderWideMaxStretchHeightRatio = 0.32;

  /// 长屏判断比例（height / width），用于 iPhone Pro Max 等屏幕收紧头图。
  static const double profileHeaderTallScreenAspectRatio = 2.05;

  /// 响应式对象主页封面基础比例。
  static double adaptiveProfileHeaderBaseHeightRatio(BuildContext context) =>
      _appSpacingAdaptiveProfileHeaderBaseHeightRatio(context);

  /// 响应式对象主页封面下拉拉伸比例。
  static double adaptiveProfileHeaderMaxStretchHeightRatio(
    BuildContext context,
  ) => _appSpacingAdaptiveProfileHeaderMaxStretchHeightRatio(context);

  /// 顶部工具栏高度（常规）
  static const double toolbarHeight = 56.0;

  /// 底部工具栏最小触控高度
  static const double toolbarMinTouchHeight = 48.0;

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

  /// 创作入口动作图标 halo 尺寸，低于旧 72px 以贴近底栏蓝白体系。
  static const double createActionSheetActionHaloSize = 64.0;

  /// 创作入口动作图标尺寸，保留 Fluent 线性图标的呼吸感。
  static const double createActionSheetActionIconSize = 30.0;

  /// 创作入口动作图标与短文案间距。
  static const double createActionSheetActionLabelGap = containerSm;

  /// 创作入口分组标题左侧强调条宽度。
  static const double createActionSheetSectionMarkerWidth = 4.0;

  /// 创作入口分组标题左侧强调条高度。
  static const double createActionSheetSectionMarkerHeight = 24.0;

  /// 创作入口分组标题与动作行间距。
  static const double createActionSheetSectionTitleGap = containerMd;

  /// 创作入口组内/组间底部间距。
  static const double createActionSheetGroupTrailingGap = containerMd;
  static const double createActionSheetGroupGap = containerLg;

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

  static const double storyHeight = 80.0;

  static const double usernameMinWidth = 60.0;

  static const double followButtonWidth = 80.0;

  /// 关注按钮宽度（紧凑，用于媒体查看器顶栏，左右间距更小）: 56.0
  static const double followButtonWidthCompact = 56.0;

  /// 媒体查看器顶栏位置指示器预估宽度（如 "1/9"）: 44.0
  static const double mediaViewerPositionIndicatorWidth = 44.0;

  /// 底部导航中间创作按钮宽度，使用小圆角正方形避免压过普通导航项。
  static const double primaryActionPillWidth = 40.0;

  /// 底部导航中间创作按钮高度，与宽度一致形成正方形主操作入口。
  static const double primaryActionPillHeight = 40.0;

  /// 底部导航中间创作按钮圆形直径，保留给存量测试或旧样式引用。
  static const double primaryActionCircleSize = primaryActionPillHeight;

  /// 底部导航普通项图标尺寸，保持当前主壳视觉基线。
  static const double bottomNavItemIconSize = iconMedium;

  /// 底部导航普通项图标的响应式尺寸，按设备形态匹配高保多尺寸规格：
  /// 手机 28、平板 32、宽屏 Web 40（极窄机降到 24 防溢出）。
  /// 图标为矢量绘制，任意尺寸均像素级清晰。
  static double bottomNavBarItemIconSize(BuildContext context) =>
      _appSpacingBottomNavBarItemIconSize(context);

  /// 底部导航主操作内图标尺寸，随胶囊缩小避免 “+” 过重。
  static const double bottomNavPrimaryActionIconSize = 22.0;

  /// 底部导航图标与标签间距，压紧图文关系以降低底栏视觉高度。
  static const double bottomNavIconLabelGap = one;

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
  static const double iconSmall = 16.0;

  static const double iconMedium = 24.0;

  static const double iconLarge = 32.0;

  /// iOS 列表行尾导航 chevron 尺寸（介于小/中图标之间，对齐系统 disclosure indicator）
  static const double listTrailingChevronSize = 18.0;

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

  /// 视频中央播放提示的语义占位尺寸
  static const double videoPlayOverlaySize = 52.0;

  /// 旧视频封面中央播放图标尺寸
  static const double videoPlayOverlayIconSize = 22.0;

  /// 沉浸视频无背景圆角播放三角尺寸
  static const double videoPlayRoundedGlyphSize = 44.0;

  /// 视频拖动预览最大尺寸
  static const double videoTimelinePreviewMaxWidth = 160.0;
  static const double videoTimelinePreviewMaxHeight = 120.0;

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
  static final Map<String, Map<String, double>> semantic = _appSpacingSemantic;

  // ==================== 语义间距快捷常量（向后兼容） ====================
  // 组内间距
  static const double intraGroupXs = 4.0, intraGroupSm = 6.0;
  static const double intraGroupMd = 8.0, intraGroupLg = 12.0;
  static const double intraGroupXl = 16.0;

  // 组间间距
  static const double interGroupXs = 8.0, interGroupSm = 12.0;
  static const double interGroupMd = 16.0, interGroupLg = 24.0;
  static const double interGroupXl = 32.0;

  // 容器间距
  static const double containerXs = 8.0, containerSm = 12.0;
  static const double containerMd = 16.0, containerLg = 20.0;
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
  }) => _appSpacingGetSpacing(
    semanticType,
    size,
    context: context,
    screenType: screenType,
  );

  static double responsiveValue(
    BuildContext context, {
    required double compact,
    required double regular,
    required double expanded,
  }) => _appSpacingResponsiveValue(
    context,
    compact: compact,
    regular: regular,
    expanded: expanded,
  );

  static double responsiveWideValue(
    BuildContext context, {
    required double compact,
    required double regular,
    required double expanded,
    required double wide,
  }) => _appSpacingResponsiveWideValue(
    context,
    compact: compact,
    regular: regular,
    expanded: expanded,
    wide: wide,
  );

  static bool isWideLayout(BuildContext context) =>
      MediaQuery.sizeOf(context).width >= wideBreakpoint;

  static double webInstallBannerHeight(BuildContext context) =>
      _appSpacingWebInstallBannerHeight(context);

  static EdgeInsets webShellContentPadding(BuildContext context) =>
      _AppSpacingWebLayout.shellContentPadding(context);

  static int webPcMasonryColumns(BuildContext context) =>
      _appSpacingWebPcMasonryColumns(context);

  static double webPcReadingWidth(BuildContext context) =>
      _appSpacingWebPcReadingWidth(context);

  // ==================== 响应式内容网格 ====================

  /// 宽屏主页/圈子页主内容最大宽度：窄屏沿用基准宽，宽屏与背景层同宽铺满。
  static double adaptiveFeedMaxContentWidth(double availableWidth) =>
      _appSpacingAdaptiveFeedMaxContentWidth(availableWidth);

  static const double _gridIdealColumnWidth =
      _AppSpacingGridValues.idealColumnWidth;
  static const int gridMinColumns = _AppSpacingGridValues.minColumns;
  static const int gridMaxColumns = _AppSpacingGridValues.maxColumns;

  /// 根据可用宽度计算 Post 预览瀑布流/宫格列数。
  /// 保证至少 [gridMinColumns] 列，并限制不超过 [gridMaxColumns]。
  static int responsiveGridColumns(
    BuildContext context, {
    double? availableWidth,
  }) =>
      _appSpacingResponsiveGridColumns(context, availableWidth: availableWidth);

  /// 关注流在宽屏下的列数（单列微博风格 → 多列卡片流过渡）。
  /// 手机始终单列；平板及以上复用 Post 预览网格列数，并继承最大列数上限。
  static int feedResponsiveColumns(BuildContext context) =>
      _appSpacingFeedResponsiveColumns(context);
}
