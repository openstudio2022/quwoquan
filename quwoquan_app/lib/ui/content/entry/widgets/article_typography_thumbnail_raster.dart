import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

/// 与创作页排版工具栏 tab 对齐。
enum ArticleTypographyThumbnailTab { paper, font }

/// 排版工具栏纸张/字体缩略图：当前页真图栅格化，**共用队列、并发 1**（对齐图片编辑器滤镜条策略）。
///
/// 宽高比与当前阅读页一致，使用 [ArticleCanvasMetrics.aspectRatio]（`宽/高`）。
///
/// **与上书对齐**：每个缩略任务内对 [resolvePaginatedArticlePages] 使用 **该格的** [ArticlePaperTexture] +
/// [ArticleFontPreset]，与主 [ArticleReadOnlyBookDeck] 使用同一 [BoxConstraints] 与 [ArticleCanvasVariant.preview]。
/// 当前页下标：优先 `activeArticlePageId` 命中；否则用 **当前编辑器纸张/字体下的基准分页** 的序下标对齐。
///
/// **仍可能偏差**：`resolvePaginatedArticlePages` 走结构化 fallback 时与主预览同源 fallback；基准分页与任务分页
/// 页数不一致时序下标回退到 0；栅格逻辑宽度为 [AppSpacing.oneHundred]，与条上单元宽度不同，仅纵横比一致。
class ArticleTypographyThumbnailStrip extends StatefulWidget {
  const ArticleTypographyThumbnailStrip({
    super.key,
    required this.editorState,
    required this.layoutConstraints,
    required this.metrics,
    required this.coverUrl,
    required this.activeTab,
    required this.child,
  });

  final CreateEditorState editorState;
  /// 与上书 [ArticleReadOnlyBookDeck] 同一 [LayoutBuilder] 约束，保证分页宽度与主预览一致。
  final BoxConstraints layoutConstraints;
  final ArticleCanvasMetrics metrics;
  final String coverUrl;
  final ArticleTypographyThumbnailTab activeTab;
  final Widget child;

  @override
  State<ArticleTypographyThumbnailStrip> createState() =>
      _ArticleTypographyThumbnailStripState();
}

class _ArticleTypographyThumbnailStripState
    extends State<ArticleTypographyThumbnailStrip> {
  static const double _rasterLogicalWidth = AppSpacing.oneHundred;

  final GlobalKey _repaintKey = GlobalKey();
  final Map<String, Uint8List> _bytes = <String, Uint8List>{};
  final Set<String> _loading = <String>{};
  final List<_QueuedRasterJob> _queue = <_QueuedRasterJob>[];
  bool _busy = false;
  _QueuedRasterJob? _captureJob;

  int get _layoutSignature => Object.hash(
    widget.editorState.articleDocument.title,
    widget.editorState.articleDocument.body,
    widget.editorState.articleDocument.assets.length,
    widget.editorState.activeArticlePageId,
    widget.editorState.articleTemplate,
    widget.editorState.articleFontPreset,
    widget.editorState.articlePaperTexture,
    widget.layoutConstraints.maxWidth.floor(),
    widget.layoutConstraints.maxHeight.floor(),
    widget.metrics.aspectRatio,
  );

  late int _lastLayoutSignature;

  @override
  void initState() {
    super.initState();
    _lastLayoutSignature = _layoutSignature;
    WidgetsBinding.instance.addPostFrameCallback((_) => _scheduleAllForCurrentTab());
  }

  @override
  void didUpdateWidget(covariant ArticleTypographyThumbnailStrip oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_layoutSignature != _lastLayoutSignature) {
      _lastLayoutSignature = _layoutSignature;
      _bytes.clear();
      _loading.clear();
      _queue.clear();
      _captureJob = null;
      WidgetsBinding.instance
          .addPostFrameCallback((_) => _scheduleAllForCurrentTab());
      return;
    }
    if (oldWidget.activeTab != widget.activeTab ||
        oldWidget.metrics.aspectRatio != widget.metrics.aspectRatio ||
        oldWidget.layoutConstraints != widget.layoutConstraints) {
      WidgetsBinding.instance
          .addPostFrameCallback((_) => _scheduleAllForCurrentTab());
    }
  }

  String _jobKey(ArticlePaperTexture paper, ArticleFontPreset font) {
    return '${_layoutSignature}_pt:${paper.name}_fp:${font.name}_'
        'pid:${widget.editorState.activeArticlePageId}';
  }

  void requestRaster(ArticlePaperTexture paper, ArticleFontPreset font) {
    final key = _jobKey(paper, font);
    if (_bytes.containsKey(key)) {
      return;
    }
    if (_queue.any((j) => j.key == key) || _captureJob?.key == key) {
      return;
    }
    setState(() {
      _loading.add(key);
      _queue.add(
        _QueuedRasterJob(
          key: key,
          paper: paper,
          font: font,
        ),
      );
    });
    _pumpQueue();
  }

  void _scheduleAllForCurrentTab() {
    if (!mounted) {
      return;
    }
    switch (widget.activeTab) {
      case ArticleTypographyThumbnailTab.paper:
        for (final t in ArticlePaperTexture.values) {
          requestRaster(t, widget.editorState.articleFontPreset);
        }
      case ArticleTypographyThumbnailTab.font:
        for (final f in ArticleFontPreset.values) {
          requestRaster(widget.editorState.articlePaperTexture, f);
        }
    }
  }

  Future<void> _pumpQueue() async {
    if (_busy) {
      return;
    }
    _busy = true;
    try {
    while (_queue.isNotEmpty && mounted) {
      final job = _queue.removeAt(0);
      if (_bytes.containsKey(job.key)) {
        setState(() => _loading.remove(job.key));
        continue;
      }
      setState(() => _captureJob = job);
      final dpr = MediaQuery.devicePixelRatioOf(context).clamp(1.0, 2.0);
      await WidgetsBinding.instance.endOfFrame;
      await Future<void>.delayed(Duration.zero);
      if (!mounted) {
        break;
      }
      RenderRepaintBoundary? boundary;
      for (var attempt = 0; attempt < 3; attempt += 1) {
        final ro = _repaintKey.currentContext?.findRenderObject();
        if (ro is RenderRepaintBoundary) {
          boundary = ro;
          break;
        }
        await WidgetsBinding.instance.endOfFrame;
        if (!mounted) {
          break;
        }
      }
      if (!mounted) {
        break;
      }
      if (boundary == null) {
        setState(() {
          _loading.remove(job.key);
          _captureJob = null;
        });
        continue;
      }
      try {
        final image = await boundary.toImage(pixelRatio: dpr);
        final bd = await image.toByteData(format: ui.ImageByteFormat.png);
        image.dispose();
        if (!mounted) {
          break;
        }
        if (bd != null) {
          setState(() {
            _bytes[job.key] = bd.buffer.asUint8List();
            _loading.remove(job.key);
            _captureJob = null;
          });
        } else {
          setState(() {
            _loading.remove(job.key);
            _captureJob = null;
          });
        }
      } catch (_) {
        if (mounted) {
          setState(() {
            _loading.remove(job.key);
            _captureJob = null;
          });
        }
      }
    }
    } finally {
      _busy = false;
      if (mounted && _captureJob != null) {
        setState(() => _captureJob = null);
      }
      if (_queue.isNotEmpty && mounted) {
        _pumpQueue();
      }
    }
  }

  Uint8List? bytesFor(ArticlePaperTexture paper, ArticleFontPreset font) =>
      _bytes[_jobKey(paper, font)];

  bool loadingFor(ArticlePaperTexture paper, ArticleFontPreset font) =>
      _loading.contains(_jobKey(paper, font));

  @override
  Widget build(BuildContext context) {
    final aspect = widget.metrics.aspectRatio;
    final captureH = _rasterLogicalWidth / aspect;
    final job = _captureJob;

    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        // 禁止用 [Offstage]：其子树会跳过 paint，[RenderRepaintBoundary.toImage] 得不到像素，
        // 捕获失败后列表长期落在「无 bytes、非 loading」分支，只显示 doc 占位图标。
        IgnorePointer(
          child: Transform.translate(
            offset: Offset(-AppSpacing.oneHundred * 200, 0),
            child: RepaintBoundary(
              key: _repaintKey,
              child: SizedBox(
                width: _rasterLogicalWidth,
                height: captureH,
                child: job == null
                    ? const SizedBox.shrink()
                    : _TypographyCapturePage(
                        editorState: widget.editorState,
                        layoutConstraints: widget.layoutConstraints,
                        metrics: widget.metrics,
                        coverUrl: widget.coverUrl,
                        paper: job.paper,
                        font: job.font,
                      ),
              ),
            ),
          ),
        ),
        _TypographyRasterInherited(
          bytesFor: bytesFor,
          loadingFor: loadingFor,
          requestRaster: requestRaster,
          child: widget.child,
        ),
      ],
    );
  }
}

class _QueuedRasterJob {
  const _QueuedRasterJob({
    required this.key,
    required this.paper,
    required this.font,
  });

  final String key;
  final ArticlePaperTexture paper;
  final ArticleFontPreset font;
}

class _TypographyRasterInherited extends InheritedWidget {
  const _TypographyRasterInherited({
    required this.bytesFor,
    required this.loadingFor,
    required this.requestRaster,
    required super.child,
  });

  final Uint8List? Function(ArticlePaperTexture paper, ArticleFontPreset font)
  bytesFor;
  final bool Function(ArticlePaperTexture paper, ArticleFontPreset font)
  loadingFor;
  final void Function(ArticlePaperTexture paper, ArticleFontPreset font)
  requestRaster;

  static _TypographyRasterInherited? maybeOf(BuildContext context) {
    return context
        .dependOnInheritedWidgetOfExactType<_TypographyRasterInherited>();
  }

  @override
  bool updateShouldNotify(covariant _TypographyRasterInherited oldWidget) {
    return true;
  }
}

class ArticleTypographyRasterCell extends StatelessWidget {
  const ArticleTypographyRasterCell({
    super.key,
    required this.paper,
    required this.font,
    required this.width,
    required this.height,
    required this.isSelected,
  });

  final ArticlePaperTexture paper;
  final ArticleFontPreset font;
  final double width;
  final double height;
  final bool isSelected;

  @override
  Widget build(BuildContext context) {
    final inh = _TypographyRasterInherited.maybeOf(context);
    if (inh == null) {
      return SizedBox(width: width, height: height);
    }
    final bytes = inh.bytesFor(paper, font);
    final loading = inh.loadingFor(paper, font);
    return SizedBox(
      width: width,
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(
            color: isSelected
                ? CupertinoColors.activeBlue.resolveFrom(context)
                : AppColors.white.withValues(alpha: 0.22),
            width: isSelected ? 2.5 : 0.5,
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(
            AppSpacing.borderRadius - AppSpacing.hairline,
          ),
          child: bytes != null
              ? ColoredBox(
                  color: AppColors.black,
                  child: Image.memory(
                    bytes,
                    fit: BoxFit.contain,
                    width: width,
                    height: height,
                    filterQuality: FilterQuality.low,
                    gaplessPlayback: true,
                  ),
                )
              : loading
              ? Center(
                  child: SizedBox(
                    width: AppSpacing.iconSmall,
                    height: AppSpacing.iconSmall,
                    child: const CupertinoActivityIndicator(),
                  ),
                )
              : Center(
                  child: Icon(
                    CupertinoIcons.doc_text,
                    size: AppSpacing.iconMedium,
                    color: AppColorsFunctional.getColor(
                      true,
                      ColorType.foregroundSecondary,
                    ).withValues(alpha: 0.5),
                  ),
                ),
        ),
      ),
    );
  }
}

class _TypographyCapturePage extends StatelessWidget {
  const _TypographyCapturePage({
    required this.editorState,
    required this.layoutConstraints,
    required this.metrics,
    required this.coverUrl,
    required this.paper,
    required this.font,
  });

  final CreateEditorState editorState;
  final BoxConstraints layoutConstraints;
  final ArticleCanvasMetrics metrics;
  final String coverUrl;
  final ArticlePaperTexture paper;
  final ArticleFontPreset font;

  @override
  Widget build(BuildContext context) {
    final resolvedPages = resolvePaginatedArticlePages(
      context: context,
      constraints: layoutConstraints,
      document: editorState.articleDocument,
      template: editorState.articleTemplate,
      fontPreset: font,
      fallbackPages: editorState.articlePages,
      variant: ArticleCanvasVariant.preview,
      paperTexture: paper,
    );
    if (resolvedPages.isEmpty) {
      return const ColoredBox(color: AppColors.black);
    }
    final byId = resolvedPages.indexWhere(
      (p) => p.id == editorState.activeArticlePageId,
    );
    final baselinePages = resolvePaginatedArticlePages(
      context: context,
      constraints: layoutConstraints,
      document: editorState.articleDocument,
      template: editorState.articleTemplate,
      fontPreset: editorState.articleFontPreset,
      fallbackPages: editorState.articlePages,
      variant: ArticleCanvasVariant.preview,
      paperTexture: editorState.articlePaperTexture,
    );
    final baselineIdx = baselinePages.indexWhere(
      (p) => p.id == editorState.activeArticlePageId,
    );
    final safeIdx = byId >= 0
        ? byId
        : (baselineIdx >= 0 && baselineIdx < resolvedPages.length
            ? baselineIdx
            : 0);
    final page = resolvedPages[safeIdx];
    final useCover = safeIdx == 0 && coverUrl.trim().isNotEmpty;
    final total = resolvedPages.length;
    return ArticlePageShell(
      template: editorState.articleTemplate,
      fontPreset: font,
      pageIndex: safeIdx,
      totalPages: total,
      aspectRatio: metrics.aspectRatio,
      outerPadding: metrics.outerPadding,
      contentPadding: metrics.contentPadding,
      headerReservedHeight: metrics.headerReservedHeight,
      footerReservedHeight: metrics.footerReservedHeight,
      variant: ArticlePageShellVariant.readerSheet,
      showIndicator: false,
      footerLabel: null,
      paperTexture: paper,
      child: useCover
          ? ArticleFrontispieceView(
              page: page,
              template: editorState.articleTemplate,
              fontPreset: font,
              coverUrl: coverUrl.trim(),
              paperTexture: paper,
            )
          : ArticlePageReadOnlyView(
              page: page,
              template: editorState.articleTemplate,
              fontPreset: font,
              metrics: metrics,
              paperTexture: paper,
            ),
    );
  }
}
