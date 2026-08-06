import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/design_system/formatters/chat_time_formatter.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show ChatMessageView, MessageCard;

class ChatMessageDisplayItem {
  const ChatMessageDisplayItem({
    required this.id,
    required this.conversationId,
    required this.seq,
    required this.clientMsgId,
    required this.senderId,
    required this.senderName,
    required this.senderAvatar,
    required this.senderPersonaId,
    required this.type,
    required this.content,
    required this.status,
    required this.timestampLabel,
    required this.sentAtIso,
    required this.isSelf,
    required this.isRead,
    required this.mediaUrl,
    required this.imageUrl,
    required this.thumbnailUrl,
    required this.audioDurationMs,
    required this.audioWaveform,
    this.mentions = const <String>[],
    this.card,
  });

  final String id;
  final String conversationId;
  final int seq;
  final String clientMsgId;
  final String senderId;
  final String senderName;
  final String senderAvatar;
  final String senderPersonaId;
  final String type;
  final String content;
  final String status;
  final String timestampLabel;
  final String sentAtIso;
  final bool isSelf;
  final bool isRead;
  final String mediaUrl;
  final String imageUrl;
  final String thumbnailUrl;
  final int audioDurationMs;
  final List<double> audioWaveform;
  final List<String> mentions;
  final MessageCard? card;
}

/// Conversation 物理页的气泡与长按菜单展示模型。
///
/// 契约字段仍以 [ChatMessageView] 为准。
extension ChatMessageViewDataDisplay on ChatMessageViewData {
  ChatMessageDisplayItem toDisplayItem({
    required String currentUserId,
    MediaEndpointConfig? mediaEndpointConfig,
  }) {
    final isSelf =
        senderId == currentUserId ||
        (senderId == 'current_user' && currentUserId.isNotEmpty);
    final timeStr = timestamp == null
        ? ''
        : ChatTimeFormatter.format(timestamp!);
    final deliveryUrl = mediaDeliveryUrl?.trim() ?? '';
    final imageUrl = type == 'image' || type == 'video' ? deliveryUrl : '';
    return ChatMessageDisplayItem(
      id: id,
      conversationId: conversationId,
      seq: seq,
      clientMsgId: clientMsgId,
      senderId: senderId,
      senderName: senderName?.trim() ?? '',
      senderAvatar: resolveAvatarImageUrl(
        senderAvatar,
        endpointConfig: mediaEndpointConfig,
      ),
      senderPersonaId: senderId,
      type: type,
      content: content?.trim() ?? '',
      status: status,
      timestampLabel: timeStr,
      sentAtIso: timestamp?.toIso8601String() ?? '',
      isSelf: isSelf,
      isRead: true,
      mediaUrl: deliveryUrl,
      imageUrl: imageUrl,
      thumbnailUrl: imageUrl,
      audioDurationMs: 0,
      audioWaveform: const <double>[],
      mentions: List<String>.unmodifiable(mentions ?? const <String>[]),
      card: card,
    );
  }
}
