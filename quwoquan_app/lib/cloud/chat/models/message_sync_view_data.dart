import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';

/// App-owned message synchronization result.
///
/// Cloud decoding is exclusively owned by the generated [ChatMessageSyncSlice];
/// this type carries the mapped local timeline state only.
class ChatMessageSyncViewData {
  final List<ChatMessageViewData> messages;
  final bool hasMore;

  const ChatMessageSyncViewData({
    required this.messages,
    required this.hasMore,
  });
}
