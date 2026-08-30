import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart';

/// 预览骨架封面的已分流渲染件（DEC-033）。
///
/// `design_system` 的预览骨架是被各服务对象复用的壳层，不能反向依赖 service
/// 对象，因此壳层不做交付分流：消费 release 媒体的调用方用本函数把**已分流**
/// 的渲染件交给骨架的媒体插槽。分流判据仍只在 [MediaDeliveryImage] 一处，
/// 这里只负责统一封面位的占位、失败与 CDN 预设，避免同一形状在各消费面复制。
Widget mediaDeliveryCoverSlot({
  required MediaDeliveryBinding binding,
  required Color placeholderColor,
  CdnImagePreset cdnPreset = CdnImagePreset.cover,
  BoxFit fit = BoxFit.cover,
  Widget? errorWidget,
  Widget? absentWidget,
}) {
  final placeholder = ColoredBox(color: placeholderColor);
  final failure = errorWidget ?? placeholder;
  return MediaDeliveryImage(
    binding: binding,
    kind: MediaDeliveryKind.image,
    fit: fit,
    placeholder: placeholder,
    errorWidget: failure,
    absentWidget: absentWidget ?? placeholder,
    publicBuilder: (context, publicUrl) => AppCachedNetworkImage(
      imageUrl: publicUrl,
      fit: fit,
      cdnPreset: cdnPreset,
      placeholder: placeholder,
      errorWidget: failure,
    ),
  );
}
