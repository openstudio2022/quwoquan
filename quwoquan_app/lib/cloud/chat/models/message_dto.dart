import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';

export 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart'
    show ChatMessageDto;

/// 历史别名；wire 模型为 metadata 投影 [ChatMessageDto]（`chat_message_client.yaml`）。
typedef MessageDto = ChatMessageDto;

/// 气泡与长按菜单使用的展示向 Map（仅 UI；契约字段仍以 [ChatMessageDto] 为准）。
extension ChatMessageDtoDisplay on ChatMessageDto {
  Map<String, dynamic> toDisplayMap({required String currentUserId}) {
    final isSelf =
        senderId == currentUserId ||
        (senderId == 'current_user' && currentUserId.isNotEmpty);
    final timeStr = timestamp != null
        ? ChatTimeFormatter.format(timestamp!)
        : '';
    final mediaMap = media;
    final imageFromMedia = mediaMap != null
        ? (mediaMap['url'] as String? ?? mediaMap['thumbnailUrl'] as String?)
        : null;
    return <String, dynamic>{
      'id': id,
      '_id': id,
      'conversationId': conversationId,
      'seq': seq,
      'clientMsgId': clientMsgId,
      'senderId': senderId,
      'senderProfileSubjectId': senderId,
      if (senderName != null) 'senderName': senderName,
      if (senderAvatar != null) 'senderAvatar': senderAvatar,
      if (senderPersonaId != null) 'senderPersonaId': senderPersonaId,
      'type': type,
      'content': content ?? '',
      if (mediaUrl != null) 'mediaUrl': mediaUrl,
      if (media != null) 'media': media,
      if (imageFromMedia != null && imageFromMedia.isNotEmpty)
        'imageUrl': imageFromMedia,
      if (imageFromMedia != null && imageFromMedia.isNotEmpty)
        'thumbnailUrl': imageFromMedia,
      if (cardPayload != null) 'cardPayload': cardPayload,
      if (replyToMessageId != null) 'replyToMessageId': replyToMessageId,
      if (mentions != null) 'mentions': mentions,
      'status': status,
      'messageStatus': status,
      'timestamp': timeStr,
      if (timestamp != null) 'sentAtIso': timestamp!.toIso8601String(),
      if (metadata != null) 'metadata': metadata,
      'isSelf': isSelf,
      'isRead': true,
      if (metadata != null && metadata!['tasks'] != null) 'tasks': metadata!['tasks'],
    };
  }
}
