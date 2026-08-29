import 'package:flutter/material.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_video.dart';

export 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart'
    show SignedVideoDelivery;
export 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart'
    show SignedVideoDelivery;

/// typed 媒体交付分流入口的跨对象组合位（DEC-033）。
///
/// 分流判据本身仍只在 [MediaDeliveryImage] 一处实现，那是 original_access_quota
/// 对象的表现件。但消费 release 媒体的渲染点分布在 content post、entity homepage、
/// search、circle、persona 等多个对象上，各自直接 import 另一个对象的私有表现件
/// 会形成跨对象私有边。组合根是允许跨对象取用的唯一位置，因此这里只做参数转发，
/// 不新增任何判据，也不定义 Widget 类型。
Widget mediaDeliveryImage({
  Key? key,
  required MediaDeliveryBinding binding,
  required MediaDeliveryKind kind,
  required Widget Function(BuildContext context, String publicUrl) publicBuilder,
  double? width,
  double? height,
  BoxFit? fit,
  Widget? placeholder,
  Widget? errorWidget,
  Widget? absentWidget,
  Widget Function(BuildContext context, String deliveryUrl, String cacheIdentity)?
  signedReadyBuilder,
  VoidCallback? onLoadSucceeded,
  void Function(Object error)? onLoadFailed,
}) {
  return MediaDeliveryImage(
    key: key,
    binding: binding,
    kind: kind,
    publicBuilder: publicBuilder,
    width: width,
    height: height,
    fit: fit,
    placeholder: placeholder,
    errorWidget: errorWidget,
    absentWidget: absentWidget,
    signedReadyBuilder: signedReadyBuilder,
    onLoadSucceeded: onLoadSucceeded,
    onLoadFailed: onLoadFailed,
  );
}

/// 私有视频分流入口的同一组合位；语义与 [mediaDeliveryImage] 一致。
Widget mediaDeliveryVideo({
  Key? key,
  required MediaDeliveryBinding binding,
  required Widget Function(BuildContext context, String publicUrl) publicBuilder,
  required Widget Function(BuildContext context, SignedVideoDelivery delivery)
  signedBuilder,
  Widget? placeholder,
  Widget? errorWidget,
  Widget? absentWidget,
}) {
  return MediaDeliveryVideo(
    key: key,
    binding: binding,
    publicBuilder: publicBuilder,
    signedBuilder: signedBuilder,
    placeholder: placeholder,
    errorWidget: errorWidget,
    absentWidget: absentWidget,
  );
}
