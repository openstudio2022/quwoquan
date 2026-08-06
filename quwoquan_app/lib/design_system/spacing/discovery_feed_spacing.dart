import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 首页推荐 feed 媒体 / 交集证据行 / 骨架屏 / 九宫格 / 文章变体的间距与几何 token。
///
/// 从 [AppSpacing] 拆出的内聚语义类（R03 文件行数预算收口）。基础刻度仍唯一来源于
/// [AppSpacing]（如 `AppSpacing.contentPreviewCornerRadius` / `AppSpacing.sm`），本类
/// 仅承载首页推荐域的语义别名，禁止在 UI 写裸字面量。
class DiscoveryFeedSpacing {
  /// 首页推荐媒体统一小圆角语义。
  static const double homeFeedMediaCornerRadius =
      AppSpacing.contentPreviewCornerRadius;

  /// 首页推荐卡竖屏/方形素材在手机窄屏下的占宽比例。
  static const double homeFeedMediaPortraitWidthFactor = 2 / 3;

  /// 首页推荐卡竖屏/方形素材在宽屏下的占宽比例，避免大屏窄图过宽。
  static const double homeFeedMediaPortraitWideWidthFactor = 0.56;

  /// 首页推荐媒体卡最大宽高比 clamp，避免超宽/超长素材破坏信息流节奏。
  static const double homeFeedMediaMaxAspectRatio = 16 / 9;

  /// 首页推荐媒体卡最小宽高比 clamp，限制超长竖图高度。
  static const double homeFeedMediaMinAspectRatio = 2 / 3;

  /// 首页推荐竖屏素材最大高度占屏比例。
  static const double homeFeedMediaPortraitMaxHeightFactor = 0.62;

  /// 首页推荐个人记录 1/2 图稀疏网格占宽比例。
  static const double homeFeedMomentSparseGridWidthFactor = 1 / 3;

  /// 首页推荐竖屏视频在大屏上的最大宽度，避免竖视频被拉得过宽。
  static const double homeFeedVideoPortraitMaxWidth = 360.0;

  /// 首页推荐轮播页码毛玻璃背景模糊半径。
  static const double homeFeedCarouselDotsBackdropBlur = 18.0;

  /// 首页推荐交集关系 glyph 尺寸。
  static const double homeFeedIntersectionIconSize = AppSpacing.eighteen;

  /// 首页推荐交集关系 glyph 线宽。
  static const double homeFeedIntersectionStrokeWidth = AppSpacing.oneHalf;

  /// 首页推荐交集关系 glyph 蓝色混合强度。
  static const double homeFeedIntersectionRingAccentBlend = 0.28;

  /// 首页推荐交集关系文字与 glyph 的间距。
  static const double homeFeedIntersectionGap = AppSpacing.seven;

  /// 首页推荐交集证据行内边距。
  static const double homeFeedIntersectionPadding = AppSpacing.six;

  /// 首页推荐交集证据行导语与正文间距。
  static const double homeFeedIntersectionLabelGap = AppSpacing.sm;

  /// 首页推荐交集证据行背景透明度（事实型 / 强）。
  static const double homeFeedIntersectionBackgroundOpacity = 0.07;

  /// 首页推荐交集证据行描边透明度（事实型 / 强）。
  static const double homeFeedIntersectionBorderOpacity = 0.14;

  /// 首页推荐交集证据行背景透明度（推测型 / 弱）。
  static const double homeFeedIntersectionBackgroundOpacitySoft = 0.035;

  /// 首页推荐交集证据行描边透明度（推测型 / 弱）。
  static const double homeFeedIntersectionBorderOpacitySoft = 0.08;

  /// 推测型交集导语颜色向次级文本混合的强度（弱化事实强度）。
  static const double homeFeedIntersectionSoftLabelBlend = 0.45;

  /// 首页推荐加载骨架屏脉冲最小透明度。
  static const double homeFeedSkeletonShimmerMinOpacity = 0.35;

  /// 首页推荐加载骨架屏脉冲最大透明度。
  static const double homeFeedSkeletonShimmerMaxOpacity = 0.75;

  /// 首页推荐加载骨架屏占位文本块高度。
  static const double homeFeedSkeletonLineHeight = AppSpacing.ten;

  /// 首页推荐加载骨架屏占位作者名宽度。
  static const double homeFeedSkeletonNameWidth = 120.0;

  /// 首页推荐加载骨架屏占位元信息宽度。
  static const double homeFeedSkeletonMetaWidth = 72.0;

  /// 首页推荐加载骨架屏占位正文第二行宽度。
  static const double homeFeedSkeletonBodyWidth = 220.0;

  /// 首页推荐加载骨架屏占位媒体块宽高比。
  static const double homeFeedSkeletonMediaAspectRatio = 16 / 10;

  /// 首页推荐卡片主区块之间的紧凑节奏。
  static const double homeFeedCardSectionGapCompact = AppSpacing.ten;

  /// 首页推荐九宫格剩余图片提示的柔和顶部遮罩透明度。
  static const double homeFeedGridMoreScrimTopOpacity = 0.04;

  /// 首页推荐九宫格剩余图片提示的柔和底部遮罩透明度。
  static const double homeFeedGridMoreScrimBottomOpacity = 0.18;

  /// 首页推荐九宫格剩余图片计数胶囊高度。
  static const double homeFeedGridMorePillHeight = AppSpacing.twenty;

  /// 首页推荐九宫格剩余图片计数胶囊水平内边距。
  static const double homeFeedGridMorePillHorizontalPadding = AppSpacing.six;

  /// 首页推荐九宫格剩余图片计数胶囊背景透明度。
  static const double homeFeedGridMorePillOpacity = 0.34;

  /// 首页推荐九宫格剩余图片计数胶囊描边透明度。
  static const double homeFeedGridMorePillBorderOpacity = 0.18;

  /// 首页推荐文章右侧缩略图占宽比例。
  static const double homeFeedArticleThumbWidthFactor = 1 / 3;

  /// 首页推荐文章右侧缩略图最大宽度。
  static const double homeFeedArticleSideThumbMaxWidth = 180.0;

  /// 首页推荐文章左文右图缩略图宽高比（width / height）。
  static const double homeFeedArticleSideThumbAspectRatio = 3 / 2;

  /// 首页推荐文章三图变体缩略图高度。
  static const double homeFeedArticleGridImageHeight = 88.0;

  /// 首页推荐文章进入上文下图布局的正文长度阈值。
  static const int homeFeedArticleTopImageTextLength = 56;
}
