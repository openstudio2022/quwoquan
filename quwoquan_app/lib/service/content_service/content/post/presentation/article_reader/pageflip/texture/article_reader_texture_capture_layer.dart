import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// 独立于父级动画 tick 的纹理截图层。
///
/// 父级每帧 `setState` 驱动翻页动画时，如果截图层在同一个 build 树里，
/// [RepaintBoundary] 会被反复标脏，`toImage()` 可能持续失败。
class ArticleReaderStableTextureCaptureLayer extends StatefulWidget {
  const ArticleReaderStableTextureCaptureLayer({
    super.key,
    required this.capturePages,
    required this.pageSize,
    required this.useOffscreenPaint,
    required this.boundaryKeys,
    required this.buildPage,
  });

  final List<int> capturePages;
  final Size pageSize;
  final bool useOffscreenPaint;
  final Map<int, GlobalKey> boundaryKeys;
  final Widget Function(int index) buildPage;

  @override
  State<ArticleReaderStableTextureCaptureLayer> createState() =>
      _ArticleReaderStableTextureCaptureLayerState();
}

class _ArticleReaderStableTextureCaptureLayerState
    extends State<ArticleReaderStableTextureCaptureLayer> {
  late List<int> _capturePages;
  late Map<int, Widget> _cachedWidgets;

  @override
  void initState() {
    super.initState();
    _capturePages = List<int>.of(widget.capturePages);
    _rebuildCache();
  }

  @override
  void didUpdateWidget(
    covariant ArticleReaderStableTextureCaptureLayer oldWidget,
  ) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(widget.capturePages, _capturePages) ||
        widget.pageSize != oldWidget.pageSize ||
        widget.useOffscreenPaint != oldWidget.useOffscreenPaint) {
      _capturePages = List<int>.of(widget.capturePages);
      _rebuildCache();
    }
    // 不调用 setState，让 RepaintBoundary 子树在动画 tick 期间保持稳定。
  }

  void _rebuildCache() {
    _cachedWidgets = {
      for (final index in _capturePages) index: widget.buildPage(index),
    };
  }

  @override
  Widget build(BuildContext context) {
    final column = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _capturePages
          .map((index) {
            return RepaintBoundary(
              key: widget.boundaryKeys[index],
              child: SizedBox(
                width: widget.pageSize.width,
                height: widget.pageSize.height,
                child: _cachedWidgets[index] ?? const SizedBox.shrink(),
              ),
            );
          })
          .toList(growable: false),
    );
    final content = Align(
      alignment: Alignment.topLeft,
      child: OverflowBox(
        alignment: Alignment.topLeft,
        minWidth: widget.pageSize.width,
        maxWidth: widget.pageSize.width,
        minHeight: widget.pageSize.height,
        maxHeight: widget.pageSize.height * _capturePages.length,
        child: column,
      ),
    );
    return IgnorePointer(
      child: ExcludeSemantics(
        child: widget.useOffscreenPaint
            ? ClipRect(
                child: Transform.translate(
                  offset: Offset(-(widget.pageSize.width * 4), 0),
                  child: content,
                ),
              )
            : Opacity(opacity: 0.001, child: content),
      ),
    );
  }
}
