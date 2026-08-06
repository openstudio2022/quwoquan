import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';

/// 领域无关的图片来源归一化：去除首尾空白。
String normalizeMediaImageSource(String? source) {
  return (source ?? '').trim();
}

/// 是否为远端（http/https）图片来源。
bool isRemoteMediaImageSource(String source) {
  final normalized = normalizeMediaImageSource(source).toLowerCase();
  return normalized.startsWith('http://') || normalized.startsWith('https://');
}

bool isRemoteResolvableMediaImageSource(String source) {
  final normalized = normalizeMediaImageSource(
    source,
  ).replaceFirst(RegExp(r'^/+'), '').toLowerCase();
  return isRemoteMediaImageSource(source) ||
      normalized.startsWith('media/') ||
      normalized.startsWith('avatar/');
}

/// 将本地来源（含 `file://`）归一化为平台图片 provider 可读取的路径。
String localMediaImagePath(String source) {
  final normalized = normalizeMediaImageSource(source);
  if (normalized.startsWith('file://')) {
    return Uri.parse(normalized).toFilePath();
  }
  return normalized;
}

/// 根据来源构造 [ImageProvider]：远端走统一 CDN/cache 解析，本地走平台防腐层。
ImageProvider<Object>? mediaImageProvider(String? source) {
  final normalized = normalizeMediaImageSource(source);
  if (normalized.isEmpty) {
    return null;
  }
  if (isRemoteResolvableMediaImageSource(normalized)) {
    final candidates = _mediaImageUrlCandidates(normalized);
    if (candidates.isEmpty) {
      return null;
    }
    return CachedNetworkImageProvider(candidates.first);
  }
  return localFileImageProvider(localMediaImagePath(normalized));
}

List<String> _mediaImageUrlCandidates(String source) {
  final normalized = normalizeMediaImageSource(source);
  final objectKey = normalized.replaceFirst(RegExp(r'^/+'), '').toLowerCase();
  if (objectKey.startsWith('media/avatar/') ||
      objectKey.startsWith('avatar/') ||
      objectKey.contains('/media/avatar/')) {
    return resolveAvatarImageUrlCandidates(normalized);
  }
  return resolveContentMediaUrlCandidates(normalized);
}

/// 领域无关的「本地路径 / 网络 URL」图片渲染组件。
///
/// 圈子、用户资料、实体主页等需要在「本地选图预览」与「远端已上传图」之间
/// 透明切换场景统一复用，避免出现第二套图片加载语义。
class AppMediaImage extends StatelessWidget {
  const AppMediaImage({
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
    final normalized = normalizeMediaImageSource(imageSource);
    if (normalized.isEmpty) {
      return _fallback(placeholder);
    }
    if (isRemoteResolvableMediaImageSource(normalized)) {
      final candidates = _mediaImageUrlCandidates(normalized);
      if (candidates.isEmpty) {
        return _fallback(errorWidget ?? placeholder);
      }
      return AppCachedNetworkImage(
        imageUrl: candidates.first,
        imageUrlCandidates: candidates,
        fit: fit,
        width: width,
        height: height,
        cdnPreset: CdnImagePreset.inline,
        placeholder: _fallback(placeholder),
        errorWidget: _fallback(errorWidget ?? placeholder),
      );
    }
    return Image(
      image: localFileImageProvider(localMediaImagePath(normalized)),
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
          child: const Center(child: Icon(CupertinoIcons.photo)),
        );
  }
}
