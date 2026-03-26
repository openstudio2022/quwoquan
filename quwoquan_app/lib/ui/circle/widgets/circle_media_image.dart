import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

String normalizeCircleImageSource(String? source) {
  return (source ?? '').trim();
}

bool isCircleRemoteImageSource(String source) {
  final normalized = normalizeCircleImageSource(source).toLowerCase();
  return normalized.startsWith('http://') || normalized.startsWith('https://');
}

String circleLocalImagePath(String source) {
  final normalized = normalizeCircleImageSource(source);
  if (normalized.startsWith('file://')) {
    return Uri.parse(normalized).toFilePath();
  }
  return normalized;
}

ImageProvider<Object>? circleImageProvider(String? source) {
  final normalized = normalizeCircleImageSource(source);
  if (normalized.isEmpty) {
    return null;
  }
  if (isCircleRemoteImageSource(normalized)) {
    return NetworkImage(normalized);
  }
  return FileImage(File(circleLocalImagePath(normalized)));
}

class CircleMediaImage extends StatelessWidget {
  const CircleMediaImage({
    super.key,
    required this.imageSource,
    this.fit,
    this.width,
    this.height,
    this.placeholder,
    this.errorWidget,
  });

  final String imageSource;
  final BoxFit? fit;
  final double? width;
  final double? height;
  final Widget? placeholder;
  final Widget? errorWidget;

  @override
  Widget build(BuildContext context) {
    final normalized = normalizeCircleImageSource(imageSource);
    if (normalized.isEmpty) {
      return _fallback(placeholder);
    }
    if (isCircleRemoteImageSource(normalized)) {
      return Image.network(
        normalized,
        fit: fit,
        width: width,
        height: height,
        errorBuilder: (context, error, stackTrace) =>
            _fallback(errorWidget ?? placeholder),
      );
    }
    return Image.file(
      File(circleLocalImagePath(normalized)),
      fit: fit,
      width: width,
      height: height,
      errorBuilder: (context, error, stackTrace) =>
          _fallback(errorWidget ?? placeholder),
    );
  }

  Widget _fallback(Widget? widget) {
    return widget ??
        ColoredBox(
          color: AppColors.black.withValues(alpha: 0.08),
          child: Center(child: Icon(CupertinoIcons.photo)),
        );
  }
}
