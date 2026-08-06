import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';

part 'article_presentation_layout_models.dart';

class BackwardPaintSourceDiagnostic {
  const BackwardPaintSourceDiagnostic({
    required this.label,
    required this.zOrder,
    required this.pageIndex,
    required this.surfaceKind,
    required this.status,
    required this.viewportBounds,
    required this.polygonSignature,
    this.viewportPolygon = const <Offset>[],
  });

  final String label;
  final int zOrder;
  final int? pageIndex;
  final String surfaceKind;
  final String status;
  final Rect? viewportBounds;
  final String polygonSignature;
  final List<Offset> viewportPolygon;

  bool get hasVisibleBounds =>
      viewportBounds != null && !viewportBounds!.isEmpty;

  String get summary {
    final pageLabel = pageIndex == null ? '-' : '${pageIndex! + 1}';
    final rect = viewportBounds;
    final rectLabel = rect == null
        ? '-'
        : '${rect.left.toStringAsFixed(1)},${rect.top.toStringAsFixed(1)},${rect.right.toStringAsFixed(1)},${rect.bottom.toStringAsFixed(1)}';
    return '$zOrder:$label:p$pageLabel/$surfaceKind/$status/$rectLabel/$polygonSignature';
  }
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
    this.textHalfLeading = 0,
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

  /// 正文 half-leading = (lineHeight - fontSize) / 2。
  /// 图片列需要加 Padding(top: textHalfLeading) 来与文字视觉顶部对齐。
  final double textHalfLeading;

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
    ArticleDocumentBlockType.sectionTitle =>
      ArticleSpacingSemantic.headingMajor,
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
    ArticleLayoutFragmentKind.semanticBlock =>
      fragment.block == null
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
    this.leadingText,
    this.trailingText,
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
          AppSpacing.containerSm +
          AppSpacing.hairline +
          AppSpacing.intraGroupXs,
      footerReservedHeight:
          AppSpacing.containerSm +
          AppSpacing.hairline +
          AppSpacing.intraGroupXs,
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
  final String? leadingText;
  final String? trailingText;
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

ArticleWrapLayoutResult resolveArticleWrapLayout(ArticleWrapLayoutInput input) {
  final fullBody = input.body;
  final hasExplicitSegments =
      input.leadingText != null || input.trailingText != null;
  var explicitLeading = input.leadingText ?? '';
  var explicitTrailing = input.trailingText ?? '';
  final rowContentWidth = input.rowContentWidth;
  final gap = input.metrics.wrapImageGap;
  final imageWidth = input.metrics.wrapImageWidthForContent(rowContentWidth);
  final baseImageHeight = imageWidth / input.metrics.fullWidthImageAspectRatio;
  const wrapBesideMinPreferred = 120.0;
  final rawBesideWidth = rowContentWidth - imageWidth - gap;
  // `clamp(lower, upper)` 要求 lower≤upper；窄版心（如排版缩略图 ~100pt）时不得用 min=120 且 max<120。
  final besideWidth =
      (rowContentWidth < wrapBesideMinPreferred
              ? rawBesideWidth.clamp(0.0, rowContentWidth)
              : rawBesideWidth.clamp(wrapBesideMinPreferred, rowContentWidth))
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

  // 只有实际渲染 caption 时才计入 captionSpacing + captionHeight。
  // 无配文且不需要 placeholder 时，imageColumn 不包含 caption，
  // besideHeight 不应加 captionSpacing。
  final hasCaption =
      input.captionText.trim().isNotEmpty || reserveCaptionPlaceholder;
  final effectiveCaptionSpacing = hasCaption ? captionSpacing : 0.0;
  final effectiveCaptionHeight = hasCaption ? captionHeight : 0.0;

  var besideHeight =
      baseImageHeight + effectiveCaptionSpacing + effectiveCaptionHeight;
  var maxLines = (besideHeight / lineHeight).ceil().clamp(2, 24);
  var split = hasExplicitSegments
      ? explicitLeading.length
      : resolveWrappedSplitIndex(
          text: fullBody,
          sideWidth: besideWidth,
          style: input.bodyStyle,
          maxLines: maxLines,
        );
  var leading = hasExplicitSegments
      ? explicitLeading
      : fullBody.substring(0, split);
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

  final fontSize = input.bodyStyle.fontSize ?? AppTypography.base;
  final textHalfLeading = (lineHeight - fontSize) / 2;

  // displayImageHeight = besideHeight - 2*halfLeading - caption
  // 因为编辑器会给图片加 Padding(top: halfLeading)，
  // 图片列总高度 = halfLeading + displayImageHeight + captionSpacing + captionHeight
  // 这个总高度应该 = besideHeight - halfLeading（最后一行底部 leading 不需要图片覆盖）
  // 所以 displayImageHeight = besideHeight - 2*halfLeading - captionSpacing - captionHeight
  var displayImageHeight =
      besideHeight -
      2 * textHalfLeading -
      effectiveCaptionSpacing -
      effectiveCaptionHeight;
  displayImageHeight = displayImageHeight.clamp(
    baseImageHeight * 0.88,
    baseImageHeight * 2.35,
  );
  // 回算 besideHeight，确保 = halfLeading + displayImageHeight + caption + halfLeading
  besideHeight = math.max(
    displayImageHeight +
        2 * textHalfLeading +
        effectiveCaptionSpacing +
        effectiveCaptionHeight,
    math.max(leadingHeight, minLineAlignedBesideHeight),
  );

  maxLines = (besideHeight / lineHeight).ceil().clamp(2, 24);
  split = hasExplicitSegments
      ? explicitLeading.length
      : resolveWrappedSplitIndex(
          text: fullBody,
          sideWidth: besideWidth,
          style: input.bodyStyle,
          maxLines: maxLines,
        );
  leading = hasExplicitSegments
      ? explicitLeading
      : fullBody.substring(0, split);
  leadingHeight = measureArticleTextHeight(
    leading,
    input.bodyStyle,
    besideWidth,
  );
  besideHeight = math.max(
    besideHeight,
    math.max(leadingHeight, maxLines * lineHeight),
  );
  displayImageHeight =
      (besideHeight -
              2 * textHalfLeading -
              effectiveCaptionSpacing -
              effectiveCaptionHeight)
          .clamp(baseImageHeight * 0.88, baseImageHeight * 2.35);
  besideHeight = math.max(
    displayImageHeight +
        2 * textHalfLeading +
        effectiveCaptionSpacing +
        effectiveCaptionHeight,
    math.max(leadingHeight, maxLines * lineHeight),
  );
  final trailing = hasExplicitSegments
      ? explicitTrailing
      : fullBody.substring(split);

  return ArticleWrapLayoutResult(
    layout: ArticleWrapLayoutData(
      imageWidth: imageWidth,
      imageHeight: displayImageHeight,
      captionHeight: effectiveCaptionHeight,
      captionSpacing: effectiveCaptionSpacing,
      besideWidth: besideWidth,
      besideHeight: besideHeight,
      sideGap: gap,
      sameParagraphSpacing: input.metrics.inlineImageSpacing,
      trailingSpacing: input.metrics.inlineImageSpacing,
      maxLinesBeside: maxLines,
      splitOffset: split,
      reserveCaptionPlaceholder: reserveCaptionPlaceholder,
      textHalfLeading: textHalfLeading,
    ),
    leadingText: leading,
    trailingText: trailing,
  );
}
