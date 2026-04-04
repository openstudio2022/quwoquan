import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';

enum ArticleTemplatePreset { gentle, ritual, diffuse, journal, tech }

extension ArticleTemplatePresetX on ArticleTemplatePreset {
  String get label => switch (this) {
    ArticleTemplatePreset.gentle => '柔和',
    ArticleTemplatePreset.ritual => '礼记',
    ArticleTemplatePreset.diffuse => '弥散',
    ArticleTemplatePreset.journal => '手帐',
    ArticleTemplatePreset.tech => '科技',
  };
}

ArticleTemplatePreset articleTemplatePresetFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'ritual' => ArticleTemplatePreset.ritual,
    'diffuse' => ArticleTemplatePreset.diffuse,
    'journal' => ArticleTemplatePreset.journal,
    'tech' => ArticleTemplatePreset.tech,
    _ => ArticleTemplatePreset.gentle,
  };
}

// ── 纸张质感系统（替代模版） ──

enum ArticlePaperTexture {
  white,
  cream,
  sepia,
  parchment,
  eyeCare,
  quiet,
  night,
}

extension ArticlePaperTextureX on ArticlePaperTexture {
  String get label => switch (this) {
    ArticlePaperTexture.white => '纯白',
    ArticlePaperTexture.cream => '柔纸',
    ArticlePaperTexture.sepia => '暖黄',
    ArticlePaperTexture.parchment => '羊皮纸',
    ArticlePaperTexture.eyeCare => '护眼',
    ArticlePaperTexture.quiet => '宁静',
    ArticlePaperTexture.night => '夜间',
  };
}

ArticlePaperTexture articlePaperTextureFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'cream' => ArticlePaperTexture.cream,
    'sepia' => ArticlePaperTexture.sepia,
    'parchment' => ArticlePaperTexture.parchment,
    'eyeCare' => ArticlePaperTexture.eyeCare,
    'quiet' => ArticlePaperTexture.quiet,
    'night' => ArticlePaperTexture.night,
    _ => ArticlePaperTexture.white,
  };
}

/// 旧模版 → 纸张质感的兼容映射。
ArticlePaperTexture paperTextureFromTemplate(ArticleTemplatePreset template) {
  return switch (template) {
    ArticleTemplatePreset.gentle => ArticlePaperTexture.cream,
    ArticleTemplatePreset.ritual => ArticlePaperTexture.sepia,
    ArticleTemplatePreset.diffuse => ArticlePaperTexture.parchment,
    ArticleTemplatePreset.journal => ArticlePaperTexture.eyeCare,
    ArticleTemplatePreset.tech => ArticlePaperTexture.white,
  };
}

enum ArticleFontPreset { clean, classic, handwritten, rounded, mono }

extension ArticleFontPresetX on ArticleFontPreset {
  String get label => switch (this) {
    ArticleFontPreset.clean => '黑体',
    ArticleFontPreset.classic => '宋体',
    ArticleFontPreset.handwritten => '楷体',
    ArticleFontPreset.rounded => '圆体',
    ArticleFontPreset.mono => '等宽',
  };
}

ArticleFontPreset articleFontPresetFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'classic' => ArticleFontPreset.classic,
    'handwritten' => ArticleFontPreset.handwritten,
    'rounded' => ArticleFontPreset.rounded,
    'mono' => ArticleFontPreset.mono,
    _ => ArticleFontPreset.clean,
  };
}

enum ArticleViewportClass { compact, regular, expanded }

enum ArticleLayoutFragmentKind {
  title,
  semanticBlock,
  wrapContent,
  fullWidthImage,
  body,
}

@immutable
class ArticleWrapLayoutData {
  const ArticleWrapLayoutData({
    required this.imageWidth,
    required this.imageHeight,
    required this.captionHeight,
    required this.captionSpacing,
    required this.besideWidth,
    required this.besideHeight,
    required this.sideGap,
    required this.sameParagraphSpacing,
    required this.trailingSpacing,
    required this.maxLinesBeside,
    required this.splitOffset,
    this.reserveCaptionPlaceholder = false,
  });

  final double imageWidth;
  final double imageHeight;
  final double captionHeight;
  final double captionSpacing;
  final double besideWidth;
  final double besideHeight;
  final double sideGap;
  final double sameParagraphSpacing;
  final double trailingSpacing;
  final int maxLinesBeside;
  final int splitOffset;
  final bool reserveCaptionPlaceholder;

  double get figureHeight =>
      imageHeight + (captionHeight > 0 ? captionSpacing + captionHeight : 0);
}

@immutable
class ArticleRhythmSpec {
  const ArticleRhythmSpec({
    required this.bodyLineHeight,
    required this.paragraphGap,
    required this.headingMajorGapBefore,
    required this.headingMajorGapAfter,
    required this.headingMinorGapBefore,
    required this.headingMinorGapAfter,
    required this.figureGapBefore,
    required this.figureGapAfter,
    required this.captionGap,
    required this.captionLineHeight,
  });

  final double bodyLineHeight;
  final double paragraphGap;
  final double headingMajorGapBefore;
  final double headingMajorGapAfter;
  final double headingMinorGapBefore;
  final double headingMinorGapAfter;
  final double figureGapBefore;
  final double figureGapAfter;
  final double captionGap;
  final double captionLineHeight;
}

const ArticleRhythmSpec _kUnifiedArticleRhythmSpec = ArticleRhythmSpec(
  bodyLineHeight: AppSpacing.textLineHeightArticleBody,
  paragraphGap: AppSpacing.interGroupSm,
  headingMajorGapBefore: AppSpacing.interGroupLg,
  headingMajorGapAfter: AppSpacing.interGroupSm,
  headingMinorGapBefore: AppSpacing.interGroupMd,
  headingMinorGapAfter: AppSpacing.interGroupXs,
  figureGapBefore: AppSpacing.interGroupSm,
  figureGapAfter: AppSpacing.interGroupSm,
  captionGap: AppSpacing.intraGroupSm,
  captionLineHeight: AppSpacing.textLineHeightLabel,
);

ArticleRhythmSpec resolveUnifiedArticleRhythmSpec() {
  return _kUnifiedArticleRhythmSpec;
}

double articleChapterSpacing() {
  return resolveUnifiedArticleRhythmSpec().headingMajorGapBefore;
}

double articleParagraphSpacing() {
  return resolveUnifiedArticleRhythmSpec().paragraphGap;
}

double articleBodyLineHeight() {
  return resolveUnifiedArticleRhythmSpec().bodyLineHeight;
}

double articleCaptionSpacing() {
  return resolveUnifiedArticleRhythmSpec().captionGap;
}

double articleCaptionLineHeight() {
  return resolveUnifiedArticleRhythmSpec().captionLineHeight;
}

enum ArticleSpacingSemantic {
  documentTitle,
  headingMajor,
  headingMinor,
  paragraph,
  figure,
  caption,
}

@immutable
class ArticleSpacingResolver {
  const ArticleSpacingResolver(this.spec);

  final ArticleRhythmSpec spec;

  double before(ArticleSpacingSemantic semantic) {
    return switch (semantic) {
      ArticleSpacingSemantic.documentTitle => 0,
      ArticleSpacingSemantic.headingMajor => spec.headingMajorGapBefore,
      ArticleSpacingSemantic.headingMinor => spec.headingMinorGapBefore,
      ArticleSpacingSemantic.paragraph => 0,
      ArticleSpacingSemantic.figure => spec.figureGapBefore,
      ArticleSpacingSemantic.caption => spec.captionGap,
    };
  }

  double after(ArticleSpacingSemantic semantic) {
    return switch (semantic) {
      ArticleSpacingSemantic.documentTitle => spec.headingMajorGapBefore,
      ArticleSpacingSemantic.headingMajor => spec.headingMajorGapAfter,
      ArticleSpacingSemantic.headingMinor => spec.headingMinorGapAfter,
      ArticleSpacingSemantic.paragraph => spec.paragraphGap,
      ArticleSpacingSemantic.figure => spec.figureGapAfter,
      ArticleSpacingSemantic.caption => spec.paragraphGap,
    };
  }

  double between(
    ArticleSpacingSemantic? previous,
    ArticleSpacingSemantic current,
  ) {
    if (previous == null) {
      return 0;
    }
    return math.max(after(previous), before(current));
  }

  /// 连续图片（通栏图、环绕块）之间的纵向间距：对齐正文自然段距，避免与 [between] 在 figure+figure 上随 figure 上下边距独立调大而叠加过大。
  double betweenConsecutiveFigures() => spec.paragraphGap;
}

const ArticleSpacingResolver _kArticleSpacingResolver = ArticleSpacingResolver(
  _kUnifiedArticleRhythmSpec,
);

ArticleSpacingResolver articleSpacingResolver() {
  return _kArticleSpacingResolver;
}

ArticleSpacingSemantic articleSpacingSemanticForBlock(
  ArticleDocumentBlock block,
) {
  return switch (block.type) {
    ArticleDocumentBlockType.heading2 ||
    ArticleDocumentBlockType.sectionTitle => ArticleSpacingSemantic.headingMajor,
    ArticleDocumentBlockType.heading3 => ArticleSpacingSemantic.headingMinor,
    ArticleDocumentBlockType.image => ArticleSpacingSemantic.figure,
    _ => ArticleSpacingSemantic.paragraph,
  };
}

ArticleSpacingSemantic articleSpacingSemanticForFragment(
  ArticleLayoutFragment fragment,
) {
  return switch (fragment.kind) {
    ArticleLayoutFragmentKind.title => ArticleSpacingSemantic.documentTitle,
    ArticleLayoutFragmentKind.semanticBlock => fragment.block == null
        ? ArticleSpacingSemantic.paragraph
        : articleSpacingSemanticForBlock(fragment.block!),
    ArticleLayoutFragmentKind.fullWidthImage ||
    ArticleLayoutFragmentKind.wrapContent => ArticleSpacingSemantic.figure,
    ArticleLayoutFragmentKind.body => ArticleSpacingSemantic.paragraph,
  };
}

@immutable
class ArticleWrapLayoutInput {
  const ArticleWrapLayoutInput({
    required this.body,
    required this.rowContentWidth,
    required this.bodyStyle,
    required this.captionText,
    required this.captionStyle,
    this.captionPlaceholderWhenEmpty = true,
    this.imageLayout = 'wrapLeft',
    this.metrics = const ArticleCanvasMetrics(
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
      wrapImageGap: AppSpacing.containerMd,
      wrapImageMaxWidth: 156,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: AppSpacing.interGroupSm,
    ),
  });

  final String body;
  final double rowContentWidth;
  final TextStyle bodyStyle;
  final String captionText;
  final TextStyle captionStyle;
  final bool captionPlaceholderWhenEmpty;
  final String imageLayout;
  final ArticleCanvasMetrics metrics;
}

@immutable
class ArticleWrapLayoutResult {
  const ArticleWrapLayoutResult({
    required this.layout,
    required this.leadingText,
    required this.trailingText,
  });

  final ArticleWrapLayoutData layout;
  final String leadingText;
  final String trailingText;
}

int resolveWrappedSplitIndex({
  required String text,
  required double sideWidth,
  required TextStyle style,
  required int maxLines,
}) {
  var low = 0;
  var high = text.length;
  var best = 0;
  while (low <= high) {
    final mid = (low + high) ~/ 2;
    final painter = TextPainter(
      text: TextSpan(text: text.substring(0, mid), style: style),
      textDirection: TextDirection.ltr,
      maxLines: maxLines,
    )..layout(maxWidth: sideWidth);
    if (!painter.didExceedMaxLines) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return best.clamp(0, text.length);
}

double measureArticleTextHeight(String text, TextStyle style, double maxWidth) {
  if (text.trim().isEmpty) {
    final fs = style.fontSize ?? AppTypography.base;
    return fs * (style.height ?? 1.2);
  }
  final painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textDirection: TextDirection.ltr,
  )..layout(maxWidth: maxWidth);
  return painter.height;
}

ArticleWrapLayoutResult resolveArticleWrapLayout(
  ArticleWrapLayoutInput input,
) {
  final fullBody = input.body;
  final rowContentWidth = input.rowContentWidth;
  final gap = input.metrics.wrapImageGap;
  final imageWidth =
      input.metrics.wrapImageWidthForContent(rowContentWidth);
  final baseImageHeight =
      imageWidth / input.metrics.fullWidthImageAspectRatio;
  final besideWidth =
      (rowContentWidth - imageWidth - gap).clamp(120.0, rowContentWidth)
          .toDouble();
  final lineHeight =
      (input.bodyStyle.fontSize ?? AppTypography.base) *
      (input.bodyStyle.height ?? 1.0);
  final captionSpacing = articleCaptionSpacing();
  var captionHeight = measureArticleTextHeight(
    input.captionText,
    input.captionStyle,
    imageWidth,
  );
  final reserveCaptionPlaceholder =
      input.captionPlaceholderWhenEmpty && input.captionText.trim().isEmpty;
  if (reserveCaptionPlaceholder) {
    captionHeight = math.max(
      captionHeight,
      (input.captionStyle.fontSize ?? AppTypography.sm) * 1.35 + 6,
    );
  }

  var besideHeight = baseImageHeight + captionSpacing + captionHeight;
  var maxLines = (besideHeight / lineHeight).ceil().clamp(2, 24);
  var split = resolveWrappedSplitIndex(
    text: fullBody,
    sideWidth: besideWidth,
    style: input.bodyStyle,
    maxLines: maxLines,
  );
  var leading = fullBody.substring(0, split);
  var leadingHeight = measureArticleTextHeight(
    leading,
    input.bodyStyle,
    besideWidth,
  );
  final minLineAlignedBesideHeight = maxLines * lineHeight;
  besideHeight = math.max(
    besideHeight,
    math.max(leadingHeight, minLineAlignedBesideHeight),
  );
  var displayImageHeight = besideHeight - captionSpacing - captionHeight;
  displayImageHeight = displayImageHeight.clamp(
    baseImageHeight * 0.88,
    baseImageHeight * 2.35,
  );
  besideHeight = math.max(
    displayImageHeight + captionSpacing + captionHeight,
    math.max(leadingHeight, minLineAlignedBesideHeight),
  );

  maxLines = (besideHeight / lineHeight).ceil().clamp(2, 24);
  split = resolveWrappedSplitIndex(
    text: fullBody,
    sideWidth: besideWidth,
    style: input.bodyStyle,
    maxLines: maxLines,
  );
  leading = fullBody.substring(0, split);
  leadingHeight = measureArticleTextHeight(
    leading,
    input.bodyStyle,
    besideWidth,
  );
  besideHeight = math.max(
    besideHeight,
    math.max(leadingHeight, maxLines * lineHeight),
  );
  displayImageHeight = (besideHeight - captionSpacing - captionHeight).clamp(
    baseImageHeight * 0.88,
    baseImageHeight * 2.35,
  );
  besideHeight = math.max(
    displayImageHeight + captionSpacing + captionHeight,
    math.max(leadingHeight, maxLines * lineHeight),
  );
  final trailing = fullBody.substring(split);

  return ArticleWrapLayoutResult(
    layout: ArticleWrapLayoutData(
      imageWidth: imageWidth,
      imageHeight: displayImageHeight,
      captionHeight: captionHeight,
      captionSpacing: captionSpacing,
      besideWidth: besideWidth,
      besideHeight: besideHeight,
      sideGap: gap,
      sameParagraphSpacing: input.metrics.inlineImageSpacing,
      trailingSpacing: input.metrics.inlineImageSpacing,
      maxLinesBeside: maxLines,
      splitOffset: split,
      reserveCaptionPlaceholder: reserveCaptionPlaceholder,
    ),
    leadingText: leading,
    trailingText: trailing,
  );
}

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
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
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

enum ArticleCanvasVariant { editor, preview, detail, immersive, thumbnail }

/// [book]：旧版卡片式纸面，仅保留给缩略卡和兼容场景。
/// [plainEdit]：编辑纸页（连续白纸页，仅保留页眉页脚，不显示卡片相框）。
/// [readerSheet]：阅读纸页（真正沉浸效果由舞台层承担，单页本体不再自带相框）。
enum ArticlePageShellVariant { book, plainEdit, readerSheet }

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

const double _kArticleLandscapeSpreadMinWidth = 920;

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

  ArticlePaperFrameSpec frameSpecForStageWidth(double stageWidth) {
    final safeStageWidth = math.max(stageWidth, 1).toDouble();
    final availableWidth = math.max(
      0.0,
      safeStageWidth - outerPadding.horizontal,
    ).toDouble();
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
  /// [wrapImageMaxWidth] 仅在大屏上当「收紧上限」（不小于半栏宽）使用；历史上
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
  if (!allowLandscapeSpread || availableWidth < _kArticleLandscapeSpreadMinWidth) {
    return availableWidth;
  }
  return ((availableWidth - resolveArticleReaderStageSpec().spineShadowWidth) / 2)
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
  return ArticleCanvasMetrics(
    aspectRatio: paperSpec.aspectRatio,
    outerPadding: paperSpec.outerPadding,
    contentPadding: paperSpec.contentPadding,
    headerReservedHeight: paperSpec.headerReservedHeight,
    footerReservedHeight: paperSpec.footerReservedHeight,
    wrapImageGap: width >= 430 ? AppSpacing.containerMd : AppSpacing.containerSm,
    wrapImageMaxWidth: width >= 430 ? 156 : 144,
    fullWidthImageAspectRatio: 4 / 3,
    journalImageAspectRatio: 1,
    inlineImageSpacing: articleParagraphSpacing(),
  );
}
