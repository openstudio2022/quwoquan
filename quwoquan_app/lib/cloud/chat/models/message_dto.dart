import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_card_dto.g.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';

export 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart'
    show ChatMessageDto;
export 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_card_dto.g.dart'
    show ChatMessageCardDto;

/// 记录别名；wire 模型为 metadata 投影 [ChatMessageDto]（`chat_message_client.yaml`）。
typedef MessageDto = ChatMessageDto;

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
  final ChatMessageCardDto? card;
}

/// 气泡与长按菜单使用的展示模型（仅 UI；契约字段仍以 [ChatMessageDto] 为准）。
extension ChatMessageDtoDisplay on ChatMessageDto {
  ChatMessageDisplayItem toDisplayItem({
    required String currentUserId,
    MediaEndpointConfig? mediaEndpointConfig,
  }) {
    final isSelf =
        senderId == currentUserId ||
        (senderId == 'current_user' && currentUserId.isNotEmpty);
    final timeStr = timestamp != null
        ? ChatTimeFormatter.format(timestamp!)
        : '';
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
