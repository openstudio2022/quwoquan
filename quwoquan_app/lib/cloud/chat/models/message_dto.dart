import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';

export 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart'
    show ChatMessageDto;

/// 记录别名；wire 模型为 metadata 投影 [ChatMessageDto]（`chat_message_client.yaml`）。
typedef MessageDto = ChatMessageDto;

class ChatTaskCardEntry {
  const ChatTaskCardEntry({
    required this.title,
    required this.time,
    required this.status,
  });

  final String title;
  final String time;
  final String status;
}

class ChatMessageDisplayItem {
  const ChatMessageDisplayItem({
    required this.id,
    required this.conversationId,
    required this.seq,
    required this.clientMsgId,
    required this.senderId,
    required this.senderName,
    required this.senderAvatar,
    required this.senderSubAccountId,
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
    required this.tasks,
  });

  final String id;
  final String conversationId;
  final int seq;
  final String clientMsgId;
  final String senderId;
  final String senderName;
  final String senderAvatar;
  final String senderSubAccountId;
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
  final List<ChatTaskCardEntry> tasks;
}

/// 气泡与长按菜单使用的展示模型（仅 UI；契约字段仍以 [ChatMessageDto] 为准）。
extension ChatMessageDtoDisplay on ChatMessageDto {
  ChatMessageDisplayItem toDisplayItem({required String currentUserId}) {
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
    final audioUrl =
        (mediaMap?['url'] as String?)?.trim() ??
        (mediaUrl?.trim() ?? '');
    final durationMs = (mediaMap?['durationMs'] as num?)?.toInt() ?? 0;
    final waveformRaw = mediaMap?['waveform'];
    final waveform = waveformRaw is List
        ? waveformRaw
              .whereType<num>()
              .map((value) => value.toDouble())
              .toList(growable: false)
        : const <double>[];
    final taskEntries = _taskEntriesFromMetadata(metadata);
    return ChatMessageDisplayItem(
      id: id,
      conversationId: conversationId,
      seq: seq,
      clientMsgId: clientMsgId,
      senderId: senderId,
      senderName: senderName?.trim() ?? '',
      senderAvatar: resolveAvatarImageUrl(senderAvatar),
      senderSubAccountId: senderSubAccountId?.trim() ?? '',
      type: type,
      content: content?.trim() ?? '',
      status: status,
      timestampLabel: timeStr,
      sentAtIso: timestamp?.toIso8601String() ?? '',
      isSelf: isSelf,
      isRead: true,
      mediaUrl: audioUrl,
      imageUrl: (imageFromMedia ?? '').trim(),
      thumbnailUrl: (imageFromMedia ?? '').trim(),
      audioDurationMs: durationMs,
      audioWaveform: waveform,
      tasks: taskEntries,
    );
  }
}

List<ChatTaskCardEntry> _taskEntriesFromMetadata(Map<String, dynamic>? metadata) {
  final rawTasks = metadata?['tasks'];
  if (rawTasks is! List) {
    return const <ChatTaskCardEntry>[];
  }
  return rawTasks
      .whereType<Map>()
      .map(
        (item) => ChatTaskCardEntry(
          title: item['title']?.toString().trim() ?? '',
          time: item['time']?.toString().trim() ?? '',
          status: item['status']?.toString().trim() ?? 'pending',
        ),
      )
      .toList(growable: false);
}
