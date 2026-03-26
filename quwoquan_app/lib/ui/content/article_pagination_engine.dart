import 'dart:math' as math;

import 'package:flutter/painting.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

class ArticlePaginationEngine {
  const ArticlePaginationEngine._();

  static List<ArticlePageData> paginate({
    required ArticleDocumentData document,
    required ArticleCanvasMetrics metrics,
    required double stageWidth,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
  }) {
    final contentSize = metrics.contentSizeForStageWidth(stageWidth);
    final contentWidth = contentSize.width;
    final contentHeight = contentSize.height;
    if (contentWidth <= 0 || contentHeight <= 0) {
      return const <ArticlePageData>[ArticlePageData(id: 'page_0')];
    }

    final title = document.title.trimRight();
    final body = document.body;
    final semanticBlocks = document.blocks
        .where(
          (block) =>
              block.type == ArticleDocumentBlockType.heading2 ||
              block.type == ArticleDocumentBlockType.heading3 ||
              block.type == ArticleDocumentBlockType.sectionTitle,
        )
        .toList(growable: false)
      ..sort((left, right) {
        final offsetCompare = left.offset.compareTo(right.offset);
        if (offsetCompare != 0) {
          return offsetCompare;
        }
        return left.id.compareTo(right.id);
      });
    final assets = document.assets
        .where((asset) => asset.hasImage)
        .toList(growable: false)
      ..sort((left, right) {
        final offsetCompare = left.offset.compareTo(right.offset);
        if (offsetCompare != 0) {
          return offsetCompare;
        }
        return left.id.compareTo(right.id);
      });

    final pages = <ArticlePageData>[];
    var titleOffset = 0;
    var bodyOffset = 0;
    var semanticIndex = 0;
    var assetIndex = 0;
    var pageIndex = 0;

    bool hasRemaining() {
      return titleOffset < title.length ||
          bodyOffset < body.length ||
          semanticIndex < semanticBlocks.length ||
          assetIndex < assets.length ||
          pages.isEmpty;
    }

    while (hasRemaining()) {
      final page = _paginateSinglePage(
        pageIndex: pageIndex,
        title: title,
        titleOffset: titleOffset,
        body: body,
        bodyOffset: bodyOffset,
        semanticBlocks: semanticBlocks,
        semanticIndex: semanticIndex,
        assets: assets,
        assetIndex: assetIndex,
        contentWidth: contentWidth,
        contentHeight: contentHeight,
        metrics: metrics,
        titleStyle: titleStyle,
        bodyStyle: bodyStyle,
      );
      pages.add(page.page);
      titleOffset = page.nextTitleOffset;
      bodyOffset = page.nextBodyOffset;
      semanticIndex = page.nextSemanticIndex;
      assetIndex = page.nextAssetIndex;
      pageIndex += 1;
      if (pages.length > 200) {
        break;
      }
    }

    return pages.isEmpty
        ? const <ArticlePageData>[ArticlePageData(id: 'page_0')]
        : pages;
  }

  static List<ArticlePageData> paginateSnapshot({
    required ArticleDocumentData document,
    ArticleCanvasMetrics metrics = const ArticleCanvasMetrics(
      aspectRatio: 0.72,
      outerPadding: EdgeInsets.all(AppSpacing.containerSm),
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerLg,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      wrapImageGap: AppSpacing.containerSm,
      wrapImageMaxWidth: 132,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: AppSpacing.intraGroupSm,
    ),
    double stageWidth = 390,
    ArticleFontPreset fontPreset = ArticleFontPreset.clean,
  }) {
    final titleStyle = _measurementTextStyle(
      fontPreset: fontPreset,
      size: AppTypography.xl,
      weight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightHeadline,
    );
    final bodyStyle = _measurementTextStyle(
      fontPreset: fontPreset,
      size: AppTypography.base,
      height: AppSpacing.textLineHeightArticleBody,
    );
    return paginate(
      document: document,
      metrics: metrics,
      stageWidth: stageWidth,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
    );
  }

  static TextStyle _measurementTextStyle({
    required ArticleFontPreset fontPreset,
    required double size,
    FontWeight weight = FontWeight.normal,
    double height = 1.6,
  }) {
    final fallback = switch (fontPreset) {
      ArticleFontPreset.classic => const <String>[
        'Times New Roman',
        'STSong',
        'Songti SC',
      ],
      ArticleFontPreset.handwritten => const <String>['Kaiti SC', 'STKaiti'],
      ArticleFontPreset.rounded => const <String>[
        'PingFang SC',
        'SF Pro Rounded',
      ],
      ArticleFontPreset.mono => const <String>['Menlo', 'Monaco'],
      ArticleFontPreset.clean => const <String>['PingFang SC'],
    };
    return TextStyle(
      fontSize: size,
      fontWeight: weight,
      height: height,
      letterSpacing: fontPreset == ArticleFontPreset.mono ? 0.15 : 0.05,
      fontFamily: switch (fontPreset) {
        ArticleFontPreset.classic => 'Times New Roman',
        ArticleFontPreset.handwritten => 'Kaiti SC',
        ArticleFontPreset.rounded => 'SF Pro Rounded',
        ArticleFontPreset.mono => 'Menlo',
        ArticleFontPreset.clean => null,
      },
      fontFamilyFallback: fallback,
    );
  }

  static _ArticlePageLayoutResult _paginateSinglePage({
    required int pageIndex,
    required String title,
    required int titleOffset,
    required String body,
    required int bodyOffset,
    required List<ArticleDocumentBlock> semanticBlocks,
    required int semanticIndex,
    required List<ArticleDocumentAsset> assets,
    required int assetIndex,
    required double contentWidth,
    required double contentHeight,
    required ArticleCanvasMetrics metrics,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
  }) {
    var remainingHeight = contentHeight;
    ArticleTextRange? titleRange;
    ArticleTextRange? bodyRange;
    ArticleDocumentAsset? pageAsset;
    final pageBlocks = <ArticleDocumentBlock>[];
    var nextTitleOffset = titleOffset;
    var nextBodyOffset = bodyOffset;
    var nextSemanticIndex = semanticIndex;
    var nextAssetIndex = assetIndex;

    if (titleOffset < title.length && remainingHeight > 0) {
      final fit = _fitText(
        text: title,
        start: titleOffset,
        endLimit: title.length,
        style: titleStyle,
        maxWidth: contentWidth,
        maxHeight: remainingHeight,
      );
      titleRange = ArticleTextRange(start: titleOffset, end: fit.endOffset);
      nextTitleOffset = fit.endOffset;
      remainingHeight -= fit.height;
      if (remainingHeight > 0 && nextTitleOffset < title.length) {
        remainingHeight -= AppSpacing.intraGroupSm;
      }
    }

    while (nextSemanticIndex < semanticBlocks.length &&
        semanticBlocks[nextSemanticIndex].offset.clamp(0, body.length) <= nextBodyOffset &&
        remainingHeight > 0) {
      final block = semanticBlocks[nextSemanticIndex];
      final spec = _semanticBlockSpec(
        block: block,
        titleStyle: titleStyle,
        bodyStyle: bodyStyle,
      );
      final spacingBefore = (titleRange == null && pageBlocks.isEmpty)
          ? 0.0
          : spec.spacingBefore;
      final textHeight = _measureTextHeight(
        text: block.text.trim(),
        style: spec.style,
        maxWidth: contentWidth,
      );
      final blockHeight = spacingBefore + textHeight + spec.spacingAfter;
      if (blockHeight > remainingHeight &&
          (titleRange != null || pageBlocks.isNotEmpty)) {
        break;
      }
      remainingHeight -= spacingBefore;
      remainingHeight -= textHeight;
      if (remainingHeight > 0) {
        remainingHeight -= spec.spacingAfter;
      }
      pageBlocks.add(block);
      nextSemanticIndex += 1;
    }

    if (nextTitleOffset >= title.length && nextAssetIndex < assets.length) {
      final candidateAsset = assets[nextAssetIndex];
      if (candidateAsset.offset.clamp(0, body.length) <= nextBodyOffset) {
        final assetHeight = _assetHeightForPage(
          asset: candidateAsset,
          metrics: metrics,
          contentWidth: contentWidth,
        );
        if (assetHeight <= remainingHeight || titleRange == null) {
          pageAsset = candidateAsset;
          nextAssetIndex += 1;
          if (!candidateAsset.usesWrappedLayout) {
            remainingHeight -= assetHeight;
            if (remainingHeight > 0) {
              remainingHeight -= metrics.inlineImageSpacing;
            }
          }
        }
      }
    }

    final nextSemanticOffset = nextSemanticIndex < semanticBlocks.length
        ? semanticBlocks[nextSemanticIndex].offset.clamp(0, body.length)
        : body.length;
    final nextAssetOffset = nextAssetIndex < assets.length
        ? assets[nextAssetIndex].offset.clamp(0, body.length)
        : body.length;
    final nextStopOffset = math.min(nextSemanticOffset, nextAssetOffset);
    final textEndLimit = math.max(nextBodyOffset, nextStopOffset);

    if (nextBodyOffset < body.length &&
        nextBodyOffset < textEndLimit &&
        remainingHeight > 0) {
      final fit = _fitBodyTextForPage(
        text: body,
        start: nextBodyOffset,
        endLimit: textEndLimit,
        style: bodyStyle,
        maxWidth: contentWidth,
        maxHeight: remainingHeight,
        asset: pageAsset,
        metrics: metrics,
      );
      if (fit.endOffset > nextBodyOffset) {
        bodyRange = ArticleTextRange(start: nextBodyOffset, end: fit.endOffset);
        nextBodyOffset = fit.endOffset;
      }
    }

    final titleText = titleRange == null
        ? ''
        : title.substring(titleRange.start, titleRange.end).trim();
    final bodyText = bodyRange == null
        ? ''
        : body.substring(bodyRange.start, bodyRange.end).trimRight();
    final insertOffset = bodyRange?.start ??
        pageAsset?.offset.clamp(0, body.length) ??
        nextBodyOffset.clamp(0, body.length);

    return _ArticlePageLayoutResult(
      page: ArticlePageData(
        id: 'page_$pageIndex',
        title: titleText,
        body: bodyText,
        imageUrl: pageAsset?.imageUrl.trim() ?? '',
        imageLayout: pageAsset?.imageLayout ?? 'fullWidth',
        caption: pageAsset?.caption ?? '',
        contentBlocks: pageBlocks,
        binding: ArticlePageBinding(
          titleRange: titleRange,
          bodyRange: bodyRange,
          assetId: pageAsset?.id,
          assetOffset: pageAsset?.offset,
          insertOffset: insertOffset,
        ),
      ),
      nextTitleOffset: nextTitleOffset,
      nextBodyOffset: nextBodyOffset,
      nextSemanticIndex: nextSemanticIndex,
      nextAssetIndex: nextAssetIndex,
    );
  }

  static double _measureTextHeight({
    required String text,
    required TextStyle style,
    required double maxWidth,
  }) {
    if (text.trim().isEmpty) {
      final fontSize = style.fontSize ?? AppTypography.base;
      return fontSize * (style.height ?? 1.2);
    }
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: maxWidth);
    return painter.height;
  }

  static _SemanticBlockSpec _semanticBlockSpec({
    required ArticleDocumentBlock block,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
  }) {
    final titleFont = titleStyle.fontSize ?? AppTypography.xl;
    final bodyFont = bodyStyle.fontSize ?? AppTypography.base;
    return switch (block.type) {
      ArticleDocumentBlockType.heading2 => _SemanticBlockSpec(
        style: titleStyle.copyWith(
          fontSize: titleFont * 0.82,
          fontWeight: FontWeight.w600,
        ),
        spacingBefore: AppSpacing.interGroupSm,
        spacingAfter: AppSpacing.intraGroupSm,
      ),
      ArticleDocumentBlockType.heading3 => _SemanticBlockSpec(
        style: bodyStyle.copyWith(
          fontSize: math.max(bodyFont * 1.14, 18),
          fontWeight: FontWeight.w600,
        ),
        spacingBefore: AppSpacing.intraGroupSm,
        spacingAfter: AppSpacing.intraGroupXs,
      ),
      ArticleDocumentBlockType.sectionTitle => _SemanticBlockSpec(
        style: titleStyle.copyWith(
          fontSize: math.max(bodyFont * 1.28, 20),
          fontWeight: FontWeight.w700,
          letterSpacing: 0.18,
        ),
        spacingBefore: AppSpacing.interGroupSm,
        spacingAfter: AppSpacing.intraGroupSm,
      ),
      _ => _SemanticBlockSpec(
        style: bodyStyle,
        spacingBefore: 0,
        spacingAfter: 0,
      ),
    };
  }

  static _TextFitResult _fitBodyTextForPage({
    required String text,
    required int start,
    required int endLimit,
    required TextStyle style,
    required double maxWidth,
    required double maxHeight,
    required ArticleDocumentAsset? asset,
    required ArticleCanvasMetrics metrics,
  }) {
    if (asset == null) {
      return _fitText(
        text: text,
        start: start,
        endLimit: endLimit,
        style: style,
        maxWidth: maxWidth,
        maxHeight: maxHeight,
      );
    }

    if (!asset.usesWrappedLayout) {
      return _fitText(
        text: text,
        start: start,
        endLimit: endLimit,
        style: style,
        maxWidth: maxWidth,
        maxHeight: maxHeight,
      );
    }

    final wrappedWidth = math.max(
      88.0,
      maxWidth - metrics.wrapImageWidthForContent(maxWidth) - metrics.wrapImageGap,
    );
    final assetHeight = _assetHeightForPage(
      asset: asset,
      metrics: metrics,
      contentWidth: maxWidth,
    );
    return _fitText(
      text: text,
      start: start,
      endLimit: endLimit,
      style: style,
      maxWidth: wrappedWidth,
      maxHeight: maxHeight,
      minimumHeight: assetHeight,
    );
  }

  static _TextFitResult _fitText({
    required String text,
    required int start,
    required int endLimit,
    required TextStyle style,
    required double maxWidth,
    required double maxHeight,
    double minimumHeight = 0,
  }) {
    final safeStart = start.clamp(0, text.length);
    final safeEnd = endLimit.clamp(safeStart, text.length);
    if (safeStart >= safeEnd) {
      return _TextFitResult(
        endOffset: safeStart,
        height: minimumHeight,
      );
    }
    if (maxHeight <= 0) {
      return _TextFitResult(
        endOffset: safeStart,
        height: minimumHeight,
      );
    }

    double heightForEnd(int end) {
      final painter = TextPainter(
        text: TextSpan(
          text: text.substring(safeStart, end).trimRight(),
          style: style,
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: maxWidth);
      return math.max(minimumHeight, painter.height);
    }

    if (heightForEnd(safeEnd) <= maxHeight) {
      return _TextFitResult(
        endOffset: safeEnd,
        height: heightForEnd(safeEnd),
      );
    }

    var low = safeStart + 1;
    var high = safeEnd;
    var best = safeStart + 1;
    while (low <= high) {
      final mid = (low + high) ~/ 2;
      if (heightForEnd(mid) <= maxHeight) {
        best = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }

    final snapped = _snapBreakOffset(text, safeStart, best, safeEnd);
    final resolvedEnd = snapped > safeStart ? snapped : best;
    return _TextFitResult(
      endOffset: resolvedEnd,
      height: heightForEnd(resolvedEnd),
    );
  }

  static int _snapBreakOffset(
    String text,
    int start,
    int candidate,
    int upperBound,
  ) {
    const breakTokens = <String>[
      '\n',
      '。',
      '！',
      '？',
      '；',
      '，',
      '、',
      '.',
      ' ',
    ];
    final lowerBound = math.max(start + 1, start + ((candidate - start) * 0.6).round());
    for (var index = candidate; index >= lowerBound; index -= 1) {
      final token = text[index - 1];
      if (breakTokens.contains(token)) {
        return index;
      }
    }
    return candidate.clamp(start + 1, upperBound);
  }

  static double _assetHeightForPage({
    required ArticleDocumentAsset asset,
    required ArticleCanvasMetrics metrics,
    required double contentWidth,
  }) {
    if (asset.usesWrappedLayout) {
      final width = metrics.wrapImageWidthForContent(contentWidth);
      return width;
    }
    final aspectRatio = asset.imageLayout == 'journalCard'
        ? metrics.journalImageAspectRatio
        : metrics.fullWidthImageAspectRatio;
    return contentWidth / aspectRatio;
  }
}

class _TextFitResult {
  const _TextFitResult({
    required this.endOffset,
    required this.height,
  });

  final int endOffset;
  final double height;
}

class _ArticlePageLayoutResult {
  const _ArticlePageLayoutResult({
    required this.page,
    required this.nextTitleOffset,
    required this.nextBodyOffset,
    required this.nextSemanticIndex,
    required this.nextAssetIndex,
  });

  final ArticlePageData page;
  final int nextTitleOffset;
  final int nextBodyOffset;
  final int nextSemanticIndex;
  final int nextAssetIndex;
}

class _SemanticBlockSpec {
  const _SemanticBlockSpec({
    required this.style,
    required this.spacingBefore,
    required this.spacingAfter,
  });

  final TextStyle style;
  final double spacingBefore;
  final double spacingAfter;
}
