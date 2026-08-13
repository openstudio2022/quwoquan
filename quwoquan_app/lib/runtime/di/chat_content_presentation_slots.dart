import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart';

/// 聊天会话的 content participant 插槽绑定：视频消息全屏播放器。
///
/// 与 [chat_circle_presentation_slots] 同范式：跨域 participant Widget 只在
/// runtime/di 组合根绑定，chat presentation 不直接依赖 content presentation。
Widget buildChatVideoMessagePlayerSlot({
  required MediaDeliveryReference deliveryReference,
  required VoidCallback onExit,
}) => VideoPlayerWidget(
  deliveryReference: deliveryReference,
  autoPlay: true,
  showControls: true,
  onExit: onExit,
);
