import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';

/// Response payload for message sync.
/// Maps to the POST /chat/conversations/:id/sync response.
class SyncResponse {
  final List<ChatMessageViewData> messages;
  final bool hasMore;

  const SyncResponse({required this.messages, required this.hasMore});
}
