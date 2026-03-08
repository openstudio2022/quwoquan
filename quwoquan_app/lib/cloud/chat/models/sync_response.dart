import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';

/// Response payload for message sync.
/// Maps to the POST /v1/chat/conversations/:id/sync response.
class SyncResponse {
  final List<MessageDto> messages;
  final bool hasMore;

  const SyncResponse({
    required this.messages,
    required this.hasMore,
  });

  factory SyncResponse.fromMap(Map<String, dynamic> map) {
    final rawMessages = map['messages'];
    final List<MessageDto> messages;
    if (rawMessages is List) {
      messages = rawMessages
          .whereType<Map<String, dynamic>>()
          .map(MessageDto.fromMap)
          .toList(growable: false);
    } else {
      messages = const [];
    }

    return SyncResponse(
      messages: messages,
      hasMore: (map['hasMore'] as bool?) ?? false,
    );
  }

  Map<String, dynamic> toMap() => {
        'messages': messages.map((m) => m.toMap()).toList(growable: false),
        'hasMore': hasMore,
      };
}
