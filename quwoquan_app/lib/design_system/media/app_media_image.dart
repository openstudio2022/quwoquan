import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/media/app_draft_image.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';

/// 根据来源构造 [ImageProvider]：远端走统一 CDN/cache 解析，本地走平台防腐层。
ImageProvider<Object>? mediaImageProvider(String? source) {
  if (source == null || source.isEmpty) return null;
  return publicMediaDelivery.imageProvider(
    source,
    profile: CdnImagePreset.inline,
  );
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
  }) : draft = null;

  const AppMediaImage.draft({
    super.key,
    required DraftImageFile source,
    this.fit,
    this.width,
    this.height,
    this.placeholder,
    this.errorWidget,
  }) : draft = source,
       imageSource = '';

  final String imageSource;
  final DraftImageFile? draft;
  final BoxFit? fit;
  final double? width;
  final double? height;
  final Widget? placeholder;
  final Widget? errorWidget;

  @override
  Widget build(BuildContext context) {
    final file = draft;
    if (file != null) {
      return AppDraftImage(
        source: file,
        fit: fit,
        width: width,
        height: height,
        errorWidget: _fallback(errorWidget),
      );
    }
    if (imageSource.isEmpty) return _fallback(placeholder);
    return AppCachedNetworkImage(
      imageUrl: imageSource,
      fit: fit,
      width: width,
      height: height,
      cdnPreset: CdnImagePreset.inline,
      placeholder: _fallback(placeholder),
      errorWidget: _fallback(errorWidget ?? placeholder),
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
