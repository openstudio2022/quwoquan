import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_image_intrinsic_registry.dart';
import 'package:quwoquan_app/ui/content/article_pagination_engine.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

/// 单段流式布局单元（绑定一个可渲染 fragment + 测量高度）。
@immutable
class ArticleFlowRun {
  const ArticleFlowRun({
    required this.id,
    required this.fragment,
    required this.measuredHeight,
    required this.sourcePage,
    required this.sourcePageIndex,
  });

  final String id;
  final ArticleLayoutFragment fragment;
  final double measuredHeight;
  final ArticlePageData sourcePage;
  final int sourcePageIndex;
}

/// 文档顺序流式测量 + 视口切片（预览横向页数不再与「资产张数」机械对齐）。
class ArticleFlowLayoutEngine {
  ArticleFlowLayoutEngine._();

  static const double structuralPaginationHeight = 2e6;

  static List<ArticlePageData> buildStructuralPages({
    required ArticleDocumentData document,
    required ArticleCanvasMetrics metrics,
    required double stageWidth,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
  }) {
    return ArticlePaginationEngine.paginate(
      document: document,
      metrics: metrics,
      stageWidth: stageWidth,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      contentHeightOverride: structuralPaginationHeight,
    );
  }

  /// 先按文档结构分页（极大内容高），再扁平化为有序 runs 并测量高度。
  static List<ArticleFlowRun> computeRuns({
    required ArticleDocumentData document,
    required ArticleCanvasMetrics metrics,
    required double stageWidth,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
    Map<String, double>? intrinsicAspectByAssetId,
  }) {
    final pages = buildStructuralPages(
      document: document,
      metrics: metrics,
      stageWidth: stageWidth,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
    );
    return computeRunsFromPages(
      document: document,
      pages,
      metrics: metrics,
      stageWidth: stageWidth,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      intrinsicAspectByAssetId: intrinsicAspectByAssetId,
    );
  }

  static List<ArticleFlowRun> computeRunsFromPages(
    List<ArticlePageData> pages, {
    required ArticleDocumentData document,
    required ArticleCanvasMetrics metrics,
    required double stageWidth,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
    Map<String, double>? intrinsicAspectByAssetId,
  }) {
    final contentSize = metrics.contentSizeForStageWidth(stageWidth);
    final contentWidth = math.max(0.0, contentSize.width);
    final assetsById = <String, ArticleDocumentAsset>{
      for (final asset in document.assets) asset.id: asset,
    };
    var runIndex = 0;
    final runs = <ArticleFlowRun>[];
    ArticleSpacingSemantic? previousSemantic;
    for (var pageIndex = 0; pageIndex < pages.length; pageIndex += 1) {
      final page = pages[pageIndex];
      final fragments = page.fragments.isNotEmpty
          ? page.fragments
          : _fallbackFragments(page);
      for (final f in fragments) {
        final measuredFragment = _resolveMeasuredFragment(
          fragment: f,
          sourcePage: page,
          document: document,
          assetsById: assetsById,
        );
        final semantic = articleSpacingSemanticForFragment(measuredFragment);
        final h =
            articleSpacingResolver().between(previousSemantic, semantic) +
            _measureFragment(
              fragment: measuredFragment,
              contentWidth: contentWidth,
              titleStyle: titleStyle,
              bodyStyle: bodyStyle,
              metrics: metrics,
              intrinsicAspectByAssetId: intrinsicAspectByAssetId,
            );
        runs.add(
          ArticleFlowRun(
            id: 'flow_run_${runIndex++}',
            fragment: measuredFragment,
            measuredHeight: h,
            sourcePage: page,
            sourcePageIndex: pageIndex,
          ),
        );
        previousSemantic = semantic;
      }
    }
    return runs;
  }

  /// 自上而下累加 [runs] 高度，超过 [viewportHeight] 时切开（单 run 超高时独占一片）。
  static List<List<ArticleFlowRun>> sliceForViewport(
    List<ArticleFlowRun> runs,
    double viewportHeight, {
    double runGap = 0,
  }) {
    if (runs.isEmpty) {
      return const <List<ArticleFlowRun>>[<ArticleFlowRun>[]];
    }
    final safeH = viewportHeight <= 0 ? double.infinity : viewportHeight;
    final slices = <List<ArticleFlowRun>>[];
    var current = <ArticleFlowRun>[];
    var acc = 0.0;
    for (final r in runs) {
      final gap = current.isEmpty ? 0.0 : runGap;
      final h = r.measuredHeight;
      if (current.isNotEmpty && acc + gap + h > safeH) {
        slices.add(current);
        current = <ArticleFlowRun>[r];
        acc = h;
      } else {
        if (current.isEmpty) {
          acc = h;
        } else {
          acc += gap + h;
        }
        current.add(r);
      }
    }
    if (current.isNotEmpty) {
      slices.add(current);
    }
    return slices;
  }

  static List<ArticlePageData> buildPageSlicesForViewport({
    required ArticleDocumentData document,
    required ArticleCanvasMetrics metrics,
    required double stageWidth,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
    required double viewportSliceHeight,
    Map<String, double>? intrinsicAspectByAssetId,
  }) {
    final structuralPages = buildStructuralPages(
      document: document,
      metrics: metrics,
      stageWidth: stageWidth,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
    );
    final runs = computeRunsFromPages(
      document: document,
      structuralPages,
      metrics: metrics,
      stageWidth: stageWidth,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      intrinsicAspectByAssetId: intrinsicAspectByAssetId,
    );
    final slices = sliceForViewport(runs, viewportSliceHeight, runGap: 0);
    final pages = pagesFromSlices(slices, document: document);
    if (pages.isEmpty) {
      return const <ArticlePageData>[ArticlePageData(id: 'slice_0')];
    }
    return pages;
  }

  /// 兼容旧调用名：返回统一 page slices。
  static List<ArticlePageData> buildPreviewPagesForViewport({
    required ArticleDocumentData document,
    required ArticleCanvasMetrics metrics,
    required double stageWidth,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
    required double viewportSliceHeight,
    Map<String, double>? intrinsicAspectByAssetId,
  }) {
    return buildPageSlicesForViewport(
      document: document,
      metrics: metrics,
      stageWidth: stageWidth,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      viewportSliceHeight: viewportSliceHeight,
      intrinsicAspectByAssetId: intrinsicAspectByAssetId,
    );
  }

  static List<ArticlePageData> pagesFromSlices(
    List<List<ArticleFlowRun>> slices, {
    required ArticleDocumentData document,
  }) {
    final assetsById = <String, ArticleDocumentAsset>{
      for (final asset in document.assets) asset.id: asset,
    };
    return slices
        .asMap()
        .entries
        .map((MapEntry<int, List<ArticleFlowRun>> entry) {
          final index = entry.key;
          final sliceRuns = entry.value;
          final fragments = sliceRuns
              .map(
                (ArticleFlowRun run) => _materializeSliceFragment(
                  run,
                  document: document,
                  assetsById: assetsById,
                ),
              )
              .toList(growable: false);
          final contentBlocks = <ArticleDocumentBlock>[];
          final seenBlockIds = <String>{};
          final assetIds = <String>[];
          final seenAssetIds = <String>{};
          ArticleTextRange? titleRange;
          ArticleTextRange? bodyRange;
          var insertOffset = 0;

          void mergeRange(ArticleTextRange? range, bool isTitle) {
            if (range == null || range.isCollapsed) {
              return;
            }
            final current = isTitle ? titleRange : bodyRange;
            final merged = current == null
                ? range
                : ArticleTextRange(
                    start: math.min(current.start, range.start),
                    end: math.max(current.end, range.end),
                  );
            if (isTitle) {
              titleRange = merged;
            } else {
              bodyRange = merged;
            }
          }

          void appendAssetId(String? assetId) {
            final normalized = assetId?.trim() ?? '';
            if (normalized.isEmpty || !seenAssetIds.add(normalized)) {
              return;
            }
            assetIds.add(normalized);
          }

          for (final run in sliceRuns) {
            final sourcePage = run.sourcePage;
            final binding = sourcePage.binding;
            mergeRange(binding?.titleRange, true);
            mergeRange(binding?.bodyRange, false);
            if (binding != null) {
              insertOffset = math.max(insertOffset, binding.insertOffset);
              for (final assetId in binding.resolvedAssetIds) {
                appendAssetId(assetId);
              }
            }
            appendAssetId(run.fragment.asset?.id);
            for (final block in sourcePage.contentBlocks) {
              if (seenBlockIds.add(block.id)) {
                contentBlocks.add(block);
              }
            }
          }

          final resolvedTitle = titleRange == null
              ? ''
              : document.title
                    .substring(titleRange!.start, titleRange!.end)
                    .trim();
          final resolvedBody = bodyRange == null
              ? ''
              : document.body
                    .substring(bodyRange!.start, bodyRange!.end)
                    .trimRight();
          final firstAsset = assetIds.isEmpty
              ? null
              : assetsById[assetIds.first];
          final binding = ArticlePageBinding(
            titleRange: titleRange,
            bodyRange: bodyRange,
            assetId: firstAsset?.id,
            assetOffset: firstAsset?.offset,
            pageAssetIds: assetIds.length > 1 ? assetIds : null,
            insertOffset: bodyRange?.end ?? titleRange?.end ?? insertOffset,
          );

          final id = _buildSliceId(
            index: index,
            titleRange: titleRange,
            bodyRange: bodyRange,
            assetIds: assetIds,
          );
          return ArticlePageData(
            id: id,
            title: resolvedTitle,
            body: resolvedBody,
            imageUrl: firstAsset?.imageUrl ?? '',
            imageLayout: firstAsset?.imageLayout ?? 'fullWidth',
            caption: firstAsset?.caption ?? '',
            contentBlocks: contentBlocks,
            fragments: fragments,
            binding: binding,
          );
        })
        .toList(growable: false);
  }

  static String _buildSliceId({
    required int index,
    required ArticleTextRange? titleRange,
    required ArticleTextRange? bodyRange,
    required List<String> assetIds,
  }) {
    if (bodyRange != null && !bodyRange.isCollapsed) {
      return 'slice_${index}_b_${bodyRange.start}_${bodyRange.end}';
    }
    if (titleRange != null && !titleRange.isCollapsed) {
      return 'slice_${index}_t_${titleRange.start}_${titleRange.end}';
    }
    if (assetIds.isNotEmpty) {
      return 'slice_${index}_a_${assetIds.first}';
    }
    return 'slice_$index';
  }

  static ArticleLayoutFragment _materializeSliceFragment(
    ArticleFlowRun run, {
    required ArticleDocumentData document,
    required Map<String, ArticleDocumentAsset> assetsById,
  }) {
    return _resolveMeasuredFragment(
      fragment: run.fragment,
      sourcePage: run.sourcePage,
      document: document,
      assetsById: assetsById,
    );
  }

  static ArticleLayoutFragment _resolveMeasuredFragment({
    required ArticleLayoutFragment fragment,
    required ArticlePageData sourcePage,
    required ArticleDocumentData document,
    required Map<String, ArticleDocumentAsset> assetsById,
  }) {
    final binding = _resolveFragmentBinding(
      fragment: fragment,
      sourceBinding: sourcePage.binding,
      document: document,
      assetsById: assetsById,
    );
    if (fragment.kind == ArticleLayoutFragmentKind.wrapContent) {
      final hasExplicitSegments =
          fragment.leadingText.isNotEmpty || fragment.trailingText.isNotEmpty;
      final wrapText =
          binding.bodyRange == null || binding.bodyRange!.isCollapsed
          ? ''
          : document.body
                .substring(binding.bodyRange!.start, binding.bodyRange!.end)
                .trimRight();
      return fragment.copyWith(
        id: fragment.id.isNotEmpty
            ? fragment.id
            : 'wrap_${fragment.asset?.id ?? sourcePage.id}',
        text: hasExplicitSegments
            ? '${fragment.leadingText}${fragment.trailingText}'
            : wrapText,
        leadingText: hasExplicitSegments ? fragment.leadingText : '',
        trailingText: hasExplicitSegments ? fragment.trailingText : '',
        binding: binding,
      );
    }
    if (fragment.kind == ArticleLayoutFragmentKind.body &&
        binding.bodyRange != null &&
        !binding.bodyRange!.isCollapsed) {
      return fragment.copyWith(
        id: fragment.id.isNotEmpty ? fragment.id : sourcePage.id,
        text: document.body
            .substring(binding.bodyRange!.start, binding.bodyRange!.end)
            .trimRight(),
        binding: binding,
      );
    }
    return fragment.copyWith(binding: binding);
  }

  static ArticlePageBinding _resolveFragmentBinding({
    required ArticleLayoutFragment fragment,
    required ArticlePageBinding? sourceBinding,
    required ArticleDocumentData document,
    required Map<String, ArticleDocumentAsset> assetsById,
  }) {
    final asset = fragment.asset;
    if (fragment.kind == ArticleLayoutFragmentKind.wrapContent &&
        asset != null) {
      final bodyRange = _resolveWrapBodyRange(
        asset,
        sourceBinding: sourceBinding,
        assetsById: assetsById,
        documentBodyLength: document.body.length,
      );
      return ArticlePageBinding(
        bodyRange: bodyRange,
        assetId: asset.id,
        assetOffset: asset.offset,
        insertOffset: bodyRange?.end ?? asset.offset,
      );
    }
    if (fragment.kind == ArticleLayoutFragmentKind.fullWidthImage &&
        asset != null) {
      return ArticlePageBinding(
        assetId: asset.id,
        assetOffset: asset.offset,
        insertOffset: asset.offset,
      );
    }
    if (fragment.kind == ArticleLayoutFragmentKind.body) {
      return ArticlePageBinding(
        bodyRange: sourceBinding?.bodyRange,
        insertOffset: sourceBinding?.insertOffset ?? document.body.length,
      );
    }
    return ArticlePageBinding(
      titleRange: sourceBinding?.titleRange,
      bodyRange: sourceBinding?.bodyRange,
      assetId: asset?.id,
      assetOffset: asset?.offset,
      insertOffset:
          sourceBinding?.insertOffset ?? asset?.offset ?? document.body.length,
    );
  }

  static ArticleTextRange? _resolveWrapBodyRange(
    ArticleDocumentAsset asset, {
    required ArticlePageBinding? sourceBinding,
    required Map<String, ArticleDocumentAsset> assetsById,
    required int documentBodyLength,
  }) {
    final sourceRange = sourceBinding?.bodyRange;
    if (sourceRange == null || sourceRange.isCollapsed) {
      return null;
    }
    final pageAssets =
        sourceBinding?.resolvedAssetIds
            .map((id) => assetsById[id])
            .whereType<ArticleDocumentAsset>()
            .toList(growable: false) ??
        const <ArticleDocumentAsset>[];
    if (pageAssets.isEmpty) {
      final cap = documentBodyLength;
      return ArticleTextRange(
        start: sourceRange.start.clamp(0, cap),
        end: sourceRange.end.clamp(sourceRange.start, cap),
      );
    }
    final sortedAssets = pageAssets.toList(growable: false)
      ..sort((left, right) {
        final offsetCompare = left.offset.compareTo(right.offset);
        if (offsetCompare != 0) {
          return offsetCompare;
        }
        return left.id.compareTo(right.id);
      });
    final index = sortedAssets.indexWhere(
      (candidate) => candidate.id == asset.id,
    );
    if (index < 0) {
      final cap = math.min(sourceRange.end, documentBodyLength);
      return ArticleTextRange(
        start: sourceRange.start.clamp(0, cap),
        end: sourceRange.end.clamp(sourceRange.start, cap),
      );
    }
    final start = index == 0
        ? sourceRange.start
        : math.max(sourceRange.start, asset.offset);
    var end = math.min(sourceRange.end, documentBodyLength);
    for (var i = index + 1; i < sortedAssets.length; i += 1) {
      final nextOffset = sortedAssets[i].offset;
      if (nextOffset > start) {
        end = math.min(end, nextOffset);
        break;
      }
    }
    final cappedEnd = math.min(sourceRange.end, documentBodyLength);
    return ArticleTextRange(
      start: start.clamp(sourceRange.start, cappedEnd),
      end: math.max(start, end).clamp(sourceRange.start, cappedEnd),
    );
  }

  static List<ArticleLayoutFragment> _fallbackFragments(ArticlePageData page) {
    final fragments = <ArticleLayoutFragment>[];
    if (page.title.trim().isNotEmpty) {
      fragments.add(
        ArticleLayoutFragment(
          kind: ArticleLayoutFragmentKind.title,
          text: page.title.trim(),
          textStyleKey: 'title',
        ),
      );
    }
    for (final block in page.contentBlocks) {
      if (block.type == ArticleDocumentBlockType.image &&
          block.imageUrl.trim().isNotEmpty) {
        fragments.add(
          ArticleLayoutFragment(
            kind:
                block.imageLayout == 'wrapLeft' ||
                    block.imageLayout == 'wrapRight'
                ? ArticleLayoutFragmentKind.wrapContent
                : ArticleLayoutFragmentKind.fullWidthImage,
            text: page.body.trim(),
            asset: ArticleDocumentAsset(
              id: block.id,
              offset: block.offset,
              imageUrl: block.imageUrl,
              imageLayout: block.imageLayout,
              caption: block.caption,
            ),
          ),
        );
        continue;
      }
      fragments.add(
        ArticleLayoutFragment(
          kind: ArticleLayoutFragmentKind.semanticBlock,
          block: block,
          text: block.text.trim(),
          textStyleKey: switch (block.type) {
            ArticleDocumentBlockType.heading2 => 'heading2',
            ArticleDocumentBlockType.heading3 => 'heading3',
            ArticleDocumentBlockType.sectionTitle => 'sectionTitle',
            ArticleDocumentBlockType.orderedItem => 'orderedItem',
            ArticleDocumentBlockType.bulletItem => 'bulletItem',
            _ => 'body',
          },
          textAlign: block.textAlign,
        ),
      );
    }
    if (page.body.trim().isNotEmpty &&
        fragments.every(
          (ArticleLayoutFragment f) =>
              f.kind != ArticleLayoutFragmentKind.body &&
              f.kind != ArticleLayoutFragmentKind.wrapContent,
        )) {
      fragments.add(
        ArticleLayoutFragment(
          kind: ArticleLayoutFragmentKind.body,
          text: page.body.trim(),
          textStyleKey: 'body',
        ),
      );
    }
    return fragments;
  }

  static double _measureFragment({
    required ArticleLayoutFragment fragment,
    required double contentWidth,
    required TextStyle titleStyle,
    required TextStyle bodyStyle,
    required ArticleCanvasMetrics metrics,
    Map<String, double>? intrinsicAspectByAssetId,
  }) {
    switch (fragment.kind) {
      case ArticleLayoutFragmentKind.title:
        if (!fragment.hasText) {
          return _emptyLineHeight(titleStyle);
        }
        return measureArticleTextHeight(
          fragment.text.trim(),
          titleStyle,
          contentWidth,
        );
      case ArticleLayoutFragmentKind.semanticBlock:
        final block = fragment.block;
        if (block == null) {
          return 0;
        }
        final spec = _semanticBlockSpec(
          block: block,
          titleStyle: titleStyle,
          bodyStyle: bodyStyle,
        );
        return measureArticleTextHeight(
          block.text.trim(),
          spec.style,
          contentWidth,
        );
      case ArticleLayoutFragmentKind.fullWidthImage:
        final asset = fragment.asset;
        if (asset == null || !asset.hasImage) {
          return 0;
        }
        final keyAspect =
            intrinsicAspectByAssetId?[asset.id] ??
            ArticleImageIntrinsicRegistry.aspectRatioFor(asset.id);
        final aspect =
            keyAspect ??
            (asset.imageLayout == 'journalCard'
                ? metrics.journalImageAspectRatio
                : metrics.fullWidthImageAspectRatio);
        var h = contentWidth / aspect;
        final cap = asset.caption.trim();
        if (cap.isNotEmpty) {
          h +=
              articleCaptionSpacing() +
              measureArticleTextHeight(
                cap,
                bodyStyle.copyWith(
                  fontSize: AppTypography.sm,
                  height: articleCaptionLineHeight(),
                ),
                contentWidth,
              );
        }
        return h;
      case ArticleLayoutFragmentKind.wrapContent:
        final asset = fragment.asset;
        if (asset == null || !asset.hasImage) {
          return 0;
        }
        final wrap = resolveArticleWrapLayout(
          ArticleWrapLayoutInput(
            body: fragment.text,
            leadingText:
                fragment.leadingText.isEmpty ? null : fragment.leadingText,
            trailingText:
                fragment.trailingText.isEmpty ? null : fragment.trailingText,
            rowContentWidth: contentWidth,
            bodyStyle: bodyStyle,
            captionText: asset.caption,
            captionStyle: bodyStyle.copyWith(
              fontSize: AppTypography.sm,
              height: articleCaptionLineHeight(),
            ),
            captionPlaceholderWhenEmpty: false,
            imageLayout: asset.imageLayout,
            metrics: metrics,
          ),
        );
        final layout = wrap.layout;
        final leadH = measureArticleTextHeight(
          wrap.leadingText,
          bodyStyle,
          layout.besideWidth,
        );
        final trailH = measureArticleTextHeight(
          wrap.trailingText,
          bodyStyle,
          contentWidth,
        );
        final rowHeight = math.max(
          math.max(layout.figureHeight, layout.besideHeight),
          leadH,
        );
        return rowHeight + layout.trailingSpacing + trailH;
      case ArticleLayoutFragmentKind.body:
        if (!fragment.hasText) {
          return _emptyLineHeight(bodyStyle);
        }
        return measureArticleTextHeight(
          fragment.text.trim(),
          bodyStyle,
          contentWidth,
        );
    }
  }

  static double _emptyLineHeight(TextStyle style) {
    final fs = style.fontSize ?? AppTypography.base;
    return fs * (style.height ?? 1.2);
  }
}

class _SemanticBlockSpec {
  const _SemanticBlockSpec({required this.style});

  final TextStyle style;
}

_SemanticBlockSpec _semanticBlockSpec({
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
    ),
    ArticleDocumentBlockType.heading3 => _SemanticBlockSpec(
      style: bodyStyle.copyWith(
        fontSize: math.max(bodyFont * 1.14, 18),
        fontWeight: FontWeight.w600,
      ),
    ),
    ArticleDocumentBlockType.sectionTitle => _SemanticBlockSpec(
      style: titleStyle.copyWith(
        fontSize: math.max(bodyFont * 1.28, 20),
        fontWeight: FontWeight.w700,
        letterSpacing: 0.18,
      ),
    ),
    _ => _SemanticBlockSpec(style: bodyStyle),
  };
}
