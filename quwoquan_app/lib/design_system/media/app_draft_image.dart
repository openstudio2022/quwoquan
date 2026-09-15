import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';

/// 创作侧已由文件选择器给出的本地路径，不接受 Post/CDN 引用。
final class DraftImageFile {
  const DraftImageFile(this.path);
  final String path;
}

class AppDraftImage extends StatelessWidget {
  const AppDraftImage({
    super.key,
    required this.source,
    this.fit,
    this.width,
    this.height,
    this.errorWidget,
  });
  final DraftImageFile source;
  final BoxFit? fit;
  final double? width;
  final double? height;
  final Widget? errorWidget;
  @override
  Widget build(BuildContext context) => Image(
    image: localFileImageProvider(source.path),
    fit: fit,
    width: width,
    height: height,
    errorBuilder: (_, error, stack) => errorWidget ?? const SizedBox.shrink(),
  );
}
