import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

/// Account/persona identity that isolates one local message timeline.
final class ChatMessageTimelineScope {
  const ChatMessageTimelineScope({
    required this.ownerUserId,
    required this.personaId,
    required this.subjectType,
    required this.contextVersion,
  });

  factory ChatMessageTimelineScope.fromPersonaContext(
    ActivePersonaContextViewData context,
  ) {
    final ownerUserId = context.ownerUserId.trim();
    final personaId = context.personaId.trim();
    return ChatMessageTimelineScope(
      ownerUserId: ownerUserId,
      personaId: personaId.isEmpty ? ownerUserId : personaId,
      subjectType: context.subjectType.trim(),
      contextVersion: context.contextVersion.toString(),
    );
  }

  final String ownerUserId;
  final String personaId;
  final String subjectType;
  final String contextVersion;
}

/// Chat Message 对象公开的本地 timeline cache seam。
///
/// Chat application 不感知 Search 的 SQLite row、namespace 或 adapter；
/// production composition 可用 Search index adapter 实现该能力，测试使用
/// test-tree typed double。
abstract interface class ChatMessageTimelineCache {
  Future<List<ChatMessageViewData>> readMessages({
    required ChatMessageTimelineScope scope,
    required String conversationId,
    int beforeSeq = 0,
    int limit = 50,
  });

  Future<void> writeMessages({
    required ChatMessageTimelineScope scope,
    required List<ChatMessageViewData> messages,
  });

  Future<void> removeCachedMessage({
    required ChatMessageTimelineScope scope,
    required String messageId,
  });
}
