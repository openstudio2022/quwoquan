part of 'article_presentation_models.dart';

@immutable
class ArticleLayoutFragment {
  const ArticleLayoutFragment({
    this.id = '',
    required this.kind,
    this.block,
    this.text = '',
    this.asset,
    this.wrapLayout,
    this.textStyleKey = '',
    this.textAlign = '',
    this.leadingText = '',
    this.trailingText = '',
    this.binding,
  });

  final String id;
  final ArticleLayoutFragmentKind kind;
  final ArticleDocumentBlock? block;
  final String text;
  final ArticleDocumentAsset? asset;
  final ArticleWrapLayoutData? wrapLayout;
  final String textStyleKey;
  final String textAlign;
  final String leadingText;
  final String trailingText;
  final ArticlePageBinding? binding;

  bool get hasText => text.trim().isNotEmpty;
  bool get hasAsset => asset != null && asset!.hasImage;

  ArticleLayoutFragment copyWith({
    String? id,
    ArticleLayoutFragmentKind? kind,
    ArticleDocumentBlock? block,
    String? text,
    ArticleDocumentAsset? asset,
    ArticleWrapLayoutData? wrapLayout,
    String? textStyleKey,
    String? textAlign,
    String? leadingText,
    String? trailingText,
    ArticlePageBinding? binding,
  }) {
    return ArticleLayoutFragment(
      id: id ?? this.id,
      kind: kind ?? this.kind,
      block: block ?? this.block,
      text: text ?? this.text,
      asset: asset ?? this.asset,
      wrapLayout: wrapLayout ?? this.wrapLayout,
      textStyleKey: textStyleKey ?? this.textStyleKey,
      textAlign: textAlign ?? this.textAlign,
      leadingText: leadingText ?? this.leadingText,
      trailingText: trailingText ?? this.trailingText,
      binding: binding ?? this.binding,
    );
  }
}

@immutable
class ArticlePageData {
  const ArticlePageData({
    required this.id,
    this.title = '',
    this.body = '',
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
    this.contentBlocks = const <ArticleDocumentBlock>[],
    this.fragments = const <ArticleLayoutFragment>[],
    this.binding,
  });

  factory ArticlePageData.fromMap(Map<String, dynamic> map) {
    return ArticlePageData(
      id: (map['id'] ?? '').toString(),
      title: (map['title'] ?? '').toString(),
      body: (map['body'] ?? '').toString(),
      imageUrl: (map['imageUrl'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
    );
  }

  final String id;
  final String title;
  final String body;
  final String imageUrl;
  final String imageLayout;
  final String caption;
  final List<ArticleDocumentBlock> contentBlocks;
  final List<ArticleLayoutFragment> fragments;
  final ArticlePageBinding? binding;

  bool get hasText =>
      title.trim().isNotEmpty ||
      body.trim().isNotEmpty ||
      contentBlocks.any((block) => block.isTextLike && block.hasText);
  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get isEmpty => !hasText && !hasImage;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';

  ArticlePageData copyWith({
    String? id,
    String? title,
    String? body,
    String? imageUrl,
    String? imageLayout,
    String? caption,
    List<ArticleDocumentBlock>? contentBlocks,
    List<ArticleLayoutFragment>? fragments,
    ArticlePageBinding? binding,
  }) {
    return ArticlePageData(
      id: id ?? this.id,
      title: title ?? this.title,
      body: body ?? this.body,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
      contentBlocks: contentBlocks ?? this.contentBlocks,
      fragments: fragments ?? this.fragments,
      binding: binding ?? this.binding,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'title': title,
      'body': body,
      'imageUrl': imageUrl,
      'imageLayout': imageLayout,
      'caption': caption,
    };
  }
}

/// [book]：过往版本卡片式纸面，仅保留给缩略卡和兼容场景。
/// [plainEdit]：编辑纸页（连续白纸页，仅保留页眉页脚，不显示卡片相框）。
/// [readerSheet]：阅读纸页（真正沉浸效果由舞台层承担，单页本体不再自带相框）。
/// [immersiveEdgeToEdge]：侵入式阅读纸页，纸张填满宿主内容区，正文只在纸张内部留白。
enum ArticlePageShellVariant {
  book,
  plainEdit,
  readerSheet,
  immersiveEdgeToEdge,
}

@immutable
class ArticlePaperSpec {
  const ArticlePaperSpec({
    required this.aspectRatio,
    required this.contentPadding,
    required this.headerReservedHeight,
    required this.footerReservedHeight,
    this.outerPadding = EdgeInsets.zero,
  });

  final double aspectRatio;
  final EdgeInsets outerPadding;
  final EdgeInsets contentPadding;
  final double headerReservedHeight;
  final double footerReservedHeight;
}

@immutable
class ArticleReaderStageSpec {
  const ArticleReaderStageSpec({
    required this.pagePadding,
    required this.editorPageGapHeight,
    required this.pageStackCount,
    required this.pageStackSpacing,
    required this.spineShadowWidth,
  });

  final EdgeInsets pagePadding;
  final double editorPageGapHeight;
  final int pageStackCount;
  final double pageStackSpacing;
  final double spineShadowWidth;
}

const ArticlePaperSpec _kUnifiedArticlePaperSpec = ArticlePaperSpec(
  aspectRatio: 0.72,
  outerPadding: EdgeInsets.zero,
  contentPadding: EdgeInsets.fromLTRB(
    AppSpacing.containerLg,
    AppSpacing.containerLg,
    AppSpacing.containerLg,
    AppSpacing.containerMd,
  ),
  headerReservedHeight:
      AppSpacing.containerSm + AppSpacing.hairline + AppSpacing.intraGroupXs,
  footerReservedHeight:
      AppSpacing.containerSm + AppSpacing.hairline + AppSpacing.intraGroupXs,
);

const ArticleReaderStageSpec _kUnifiedArticleReaderStageSpec =
    ArticleReaderStageSpec(
      pagePadding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      editorPageGapHeight: AppSpacing.containerLg,
      pageStackCount: 4,
      pageStackSpacing: 1.0,
      spineShadowWidth: 15,
    );

ArticlePaperSpec resolveUnifiedArticlePaperSpec() {
  return _kUnifiedArticlePaperSpec;
}

ArticleReaderStageSpec resolveArticleReaderStageSpec() {
  return _kUnifiedArticleReaderStageSpec;
}

@immutable
class ArticlePaperFrameSpec {
  const ArticlePaperFrameSpec({
    required this.viewportSize,
    required this.paperSize,
    required this.contentSize,
  });

  final Size viewportSize;
  final Size paperSize;
  final Size contentSize;
}

@immutable
class ArticleCanvasMetrics {
  const ArticleCanvasMetrics({
    required this.aspectRatio,
    required this.outerPadding,
    required this.contentPadding,
    required this.headerReservedHeight,
    required this.footerReservedHeight,
    required this.wrapImageGap,
    required this.wrapImageMaxWidth,
    required this.fullWidthImageAspectRatio,
    required this.journalImageAspectRatio,
    required this.inlineImageSpacing,
  });

  factory ArticleCanvasMetrics.snapshot() {
    final paperSpec = resolveUnifiedArticlePaperSpec();
    return ArticleCanvasMetrics(
      aspectRatio: paperSpec.aspectRatio,
      outerPadding: paperSpec.outerPadding,
      contentPadding: paperSpec.contentPadding,
      headerReservedHeight: paperSpec.headerReservedHeight,
      footerReservedHeight: paperSpec.footerReservedHeight,
      wrapImageGap: AppSpacing.containerMd,
      wrapImageMaxWidth: 156,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: articleParagraphSpacing(),
    );
  }

  factory ArticleCanvasMetrics.fromView(ArticleCanvasMetricsView view) {
    return ArticleCanvasMetrics(
      aspectRatio: view.aspectRatio,
      outerPadding: EdgeInsets.fromLTRB(
        view.outerPadding.left,
        view.outerPadding.top,
        view.outerPadding.right,
        view.outerPadding.bottom,
      ),
      contentPadding: EdgeInsets.fromLTRB(
        view.contentPadding.left,
        view.contentPadding.top,
        view.contentPadding.right,
        view.contentPadding.bottom,
      ),
      headerReservedHeight: view.headerReservedHeight,
      footerReservedHeight: view.footerReservedHeight,
      wrapImageGap: view.wrapImageGap,
      wrapImageMaxWidth: view.wrapImageMaxWidth,
      fullWidthImageAspectRatio: view.fullWidthImageAspectRatio,
      journalImageAspectRatio: view.journalImageAspectRatio,
      inlineImageSpacing: view.inlineImageSpacing,
    );
  }

  final double aspectRatio;
  final EdgeInsets outerPadding;
  final EdgeInsets contentPadding;
  final double headerReservedHeight;
  final double footerReservedHeight;
  final double wrapImageGap;
  final double wrapImageMaxWidth;
  final double fullWidthImageAspectRatio;
  final double journalImageAspectRatio;
  final double inlineImageSpacing;

  ArticleCanvasMetricsView toView() {
    return ArticleCanvasMetricsView(
      aspectRatio: aspectRatio,
      outerPadding: ArticleEdgeInsetsView(
        left: outerPadding.left,
        top: outerPadding.top,
        right: outerPadding.right,
        bottom: outerPadding.bottom,
      ),
      contentPadding: ArticleEdgeInsetsView(
        left: contentPadding.left,
        top: contentPadding.top,
        right: contentPadding.right,
        bottom: contentPadding.bottom,
      ),
      headerReservedHeight: headerReservedHeight,
      footerReservedHeight: footerReservedHeight,
      wrapImageGap: wrapImageGap,
      wrapImageMaxWidth: wrapImageMaxWidth,
      fullWidthImageAspectRatio: fullWidthImageAspectRatio,
      journalImageAspectRatio: journalImageAspectRatio,
      inlineImageSpacing: inlineImageSpacing,
    );
  }

  ArticlePaperFrameSpec frameSpecForStageWidth(double stageWidth) {
    final safeStageWidth = math.max(stageWidth, 1).toDouble();
    final availableWidth = math
        .max(0.0, safeStageWidth - outerPadding.horizontal)
        .toDouble();
    if (availableWidth <= 0) {
      return ArticlePaperFrameSpec(
        viewportSize: Size(safeStageWidth, 0),
        paperSize: Size.zero,
        contentSize: Size.zero,
      );
    }
    final paperWidth = availableWidth;
    final paperHeight = paperWidth / aspectRatio;
    final contentHeight =
        paperHeight -
        contentPadding.vertical -
        headerReservedHeight -
        footerReservedHeight;
    return ArticlePaperFrameSpec(
      viewportSize: Size(safeStageWidth, paperHeight + outerPadding.vertical),
      paperSize: Size(paperWidth, paperHeight),
      contentSize: Size(
        math.max(0.0, paperWidth - contentPadding.horizontal),
        math.max(0.0, contentHeight),
      ),
    );
  }

  ArticlePaperFrameSpec frameSpecForViewport(Size viewportSize) {
    final viewportWidth = math.max(1.0, viewportSize.width).toDouble();
    return frameSpecForStageWidth(viewportWidth);
  }

  Size contentSizeForStageWidth(double stageWidth) {
    return frameSpecForStageWidth(stageWidth).contentSize;
  }

  /// 文内环绕图默认宽度：目标为内容区约 50%。
  ///
  /// [wrapImageMaxWidth] 仅在大屏上当「收紧上限」（不小于半栏宽）使用；记录上
  /// `min(0.5*w, 112~168)` 会把竖屏半栏压成约 1/3 栏宽，与版式约定冲突。
  double wrapImageWidthForContent(double contentWidth) {
    final w = contentWidth.clamp(0.0, double.infinity);
    final half = w * 0.5;
    if (wrapImageMaxWidth <= 0) {
      return half;
    }
    final effectiveMax = wrapImageMaxWidth < half ? half : wrapImageMaxWidth;
    return math.min(half, effectiveMax);
  }

  @override
  bool operator ==(Object other) {
    return other is ArticleCanvasMetrics &&
        other.aspectRatio == aspectRatio &&
        other.outerPadding == outerPadding &&
        other.contentPadding == contentPadding &&
        other.headerReservedHeight == headerReservedHeight &&
        other.footerReservedHeight == footerReservedHeight &&
        other.wrapImageGap == wrapImageGap &&
        other.wrapImageMaxWidth == wrapImageMaxWidth &&
        other.fullWidthImageAspectRatio == fullWidthImageAspectRatio &&
        other.journalImageAspectRatio == journalImageAspectRatio &&
        other.inlineImageSpacing == inlineImageSpacing;
  }

  @override
  int get hashCode => Object.hash(
    aspectRatio,
    outerPadding,
    contentPadding,
    headerReservedHeight,
    footerReservedHeight,
    wrapImageGap,
    wrapImageMaxWidth,
    fullWidthImageAspectRatio,
    journalImageAspectRatio,
    inlineImageSpacing,
  );
}

/// 与 [ArticleCanvasMetrics.snapshot] 的环绕宽度算法一致（无 BuildContext 时的回退）。
double articleWrapImageColumnWidth(double contentWidth) {
  return ArticleCanvasMetrics.snapshot().wrapImageWidthForContent(contentWidth);
}

EdgeInsets articleReaderStagePagePadding() {
  return resolveArticleReaderStageSpec().pagePadding;
}

double articleEditorPageGapHeight() {
  return resolveArticleReaderStageSpec().editorPageGapHeight;
}

double resolveArticlePaperStageWidth(
  BuildContext context,
  BoxConstraints constraints, {
  EdgeInsets? stagePadding,
  bool allowLandscapeSpread = false,
}) {
  final viewportWidth = constraints.maxWidth.isFinite
      ? constraints.maxWidth
      : MediaQuery.sizeOf(context).width;
  final viewportHeight = constraints.maxHeight.isFinite
      ? constraints.maxHeight
      : MediaQuery.sizeOf(context).height;
  final inset = stagePadding ?? EdgeInsets.zero;
  final availableWidth = math.max(1.0, viewportWidth - inset.horizontal);
  if (!viewportHeight.isFinite) {
    return availableWidth;
  }
  if (!allowLandscapeSpread ||
      availableWidth < AppSpacing.articleLandscapeSpreadMinWidth) {
    return availableWidth;
  }
  return ((availableWidth - resolveArticleReaderStageSpec().spineShadowWidth) /
          2)
      .clamp(1.0, availableWidth)
      .toDouble();
}

ArticleCanvasMetrics resolveArticleCanvasMetrics(
  BuildContext context,
  BoxConstraints constraints, {
  ArticleCanvasVariant variant = ArticleCanvasVariant.preview,
}) {
  final width = constraints.maxWidth.isFinite
      ? constraints.maxWidth
      : MediaQuery.sizeOf(context).width;
  if (variant == ArticleCanvasVariant.thumbnail) {
    return const ArticleCanvasMetrics(
      aspectRatio: 72 / 104,
      outerPadding: EdgeInsets.all(AppSpacing.two),
      contentPadding: EdgeInsets.fromLTRB(8, 10, 8, 8),
      headerReservedHeight: 0,
      footerReservedHeight: 0,
      wrapImageGap: AppSpacing.intraGroupXs,
      wrapImageMaxWidth: 88,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: AppSpacing.intraGroupXs,
    );
  }
  final paperSpec = resolveUnifiedArticlePaperSpec();
  if (variant == ArticleCanvasVariant.immersive) {
    // 与沉浸浏览器底部 chrome 共用同一对齐轨道（REQ-019）：
    // 不叠加底部安全区侧向保护，避免正文与 caption/工具栏左右漂移。
    final horizontalInset = AppSpacing.containerLg;
    final basePadding = paperSpec.contentPadding;
    return ArticleCanvasMetrics(
      aspectRatio: paperSpec.aspectRatio,
      outerPadding: paperSpec.outerPadding,
      contentPadding: EdgeInsets.fromLTRB(
        horizontalInset,
        basePadding.top,
        horizontalInset,
        basePadding.bottom,
      ),
      headerReservedHeight: 0,
      footerReservedHeight: 0,
      wrapImageGap: width >= AppSpacing.articleWrapImageBreakpoint
          ? AppSpacing.containerMd
          : AppSpacing.containerSm,
      wrapImageMaxWidth: width >= AppSpacing.articleWrapImageBreakpoint
          ? AppSpacing.articleWrapImageMaxWidthWide
          : AppSpacing.articleWrapImageMaxWidthCompact,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: articleParagraphSpacing(),
    );
  }
  return ArticleCanvasMetrics(
    aspectRatio: paperSpec.aspectRatio,
    outerPadding: paperSpec.outerPadding,
    contentPadding: paperSpec.contentPadding,
    headerReservedHeight: paperSpec.headerReservedHeight,
    footerReservedHeight: paperSpec.footerReservedHeight,
    wrapImageGap: width >= AppSpacing.articleWrapImageBreakpoint
        ? AppSpacing.containerMd
        : AppSpacing.containerSm,
    wrapImageMaxWidth: width >= AppSpacing.articleWrapImageBreakpoint
        ? AppSpacing.articleWrapImageMaxWidthWide
        : AppSpacing.articleWrapImageMaxWidthCompact,
    fullWidthImageAspectRatio: 4 / 3,
    journalImageAspectRatio: 1,
    inlineImageSpacing: articleParagraphSpacing(),
  );
}

/// 元数据派生比例的版式区间（REQ-017）：竖图下限 3:4、横图上限 2:1，
/// 超界部分由框内 cover 吸收。
const double articleFigureMetadataAspectMin = 3 / 4;
const double articleFigureMetadataAspectMax = 2.0;

/// 文章图片占位比例的唯一决定函数（REQ-017 / GWT-016）。
///
/// - 资产元数据（像素宽高）优先，并 clamp 到版式区间；
/// - 元数据缺席时按布局取后备比例（fullWidth 4:3、journalCard 由 metrics 声明），
///   分页与渲染同取同值；
/// - 分页测量与阅读渲染都必须经此函数取比例，运行时解码尺寸不得进入分页输入。
double resolveArticleFigureAspectRatio({
  required ArticleCanvasMetrics metrics,
  required ArticleDocumentAsset asset,
}) {
  final metadata = asset.metadataAspectRatio;
  if (metadata != null) {
    return metadata
        .clamp(articleFigureMetadataAspectMin, articleFigureMetadataAspectMax)
        .toDouble();
  }
  return asset.imageLayout == 'journalCard'
      ? metrics.journalImageAspectRatio
      : metrics.fullWidthImageAspectRatio;
}

/// wrap 图缺席（引用未解析出交付 URL）时的降级正文（REQ-017/GWT-016）：
/// 图旁与图下文字合并为全宽顺序正文；分页测量与渲染必须同用此函数，
/// 防止缺席图把整段文字一并丢失。
String articleWrapAbsentFallbackText(ArticleLayoutFragment fragment) {
  return <String>[
    fragment.leadingText,
    fragment.text,
    fragment.trailingText,
  ].map((value) => value.trim()).where((value) => value.isNotEmpty).join('\n');
}
