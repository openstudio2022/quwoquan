import 'dart:io';

import 'package:flutter/widgets.dart';

/// 文内图「宽/高」比缓存（宽 ÷ 高），供 [ArticleFlowLayoutEngine] 流式测量与 reflow。
///
/// 由编辑器内联图在首帧解码后上报；键优先使用 assetId，缺省时可用 imageUrl。
class ArticleImageIntrinsicRegistry {
  ArticleImageIntrinsicRegistry._();

  static final Map<String, double> _aspectByKey = <String, double>{};

  /// width / height（>0）
  static void reportAspect(String key, double width, double height) {
    final k = key.trim();
    if (k.isEmpty || width <= 0 || height <= 0) {
      return;
    }
    final aspect = width / height;
    if (_aspectByKey[k] == aspect) {
      return;
    }
    _aspectByKey[k] = aspect;
  }

  static double? aspectRatioFor(String key) {
    final v = _aspectByKey[key.trim()];
    if (v == null || v <= 0) {
      return null;
    }
    return v;
  }

  @visibleForTesting
  static void clearForTest() => _aspectByKey.clear();
}

/// 并行解析图片尺寸并写入 [ArticleImageIntrinsicRegistry]（不替代子组件绘制）。
class ArticleImageIntrinsicListener extends StatefulWidget {
  const ArticleImageIntrinsicListener({
    super.key,
    required this.imageUrl,
    required this.reportKey,
    this.onResolved,
    required this.child,
  });

  final String imageUrl;
  final String reportKey;
  final VoidCallback? onResolved;
  final Widget child;

  @override
  State<ArticleImageIntrinsicListener> createState() =>
      _ArticleImageIntrinsicListenerState();
}

class _ArticleImageIntrinsicListenerState
    extends State<ArticleImageIntrinsicListener> {
  ImageStream? _stream;
  ImageStreamListener? _listener;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _attachIfNeeded());
  }

  @override
  void didUpdateWidget(covariant ArticleImageIntrinsicListener oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.imageUrl != widget.imageUrl ||
        oldWidget.reportKey != widget.reportKey) {
      _detach();
      WidgetsBinding.instance.addPostFrameCallback((_) => _attachIfNeeded());
    }
  }

  void _detach() {
    if (_stream != null && _listener != null) {
      _stream!.removeListener(_listener!);
    }
    _stream = null;
    _listener = null;
  }

  void _attachIfNeeded() {
    final url = widget.imageUrl.trim();
    final key = widget.reportKey.trim();
    if (url.isEmpty || key.isEmpty || !mounted) {
      return;
    }
    if (ArticleImageIntrinsicRegistry.aspectRatioFor(key) != null) {
      return;
    }
    final ImageProvider<Object> provider;
    if (url.startsWith('http://') || url.startsWith('https://')) {
      provider = NetworkImage(url);
    } else {
      provider = FileImage(File(url));
    }
    final stream = provider.resolve(createLocalImageConfiguration(context));
    final listener = ImageStreamListener((ImageInfo info, bool _) {
      ArticleImageIntrinsicRegistry.reportAspect(
        key,
        info.image.width.toDouble(),
        info.image.height.toDouble(),
      );
      _detach();
      widget.onResolved?.call();
    });
    _stream = stream;
    _listener = listener;
    stream.addListener(listener);
  }

  @override
  void dispose() {
    _detach();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
