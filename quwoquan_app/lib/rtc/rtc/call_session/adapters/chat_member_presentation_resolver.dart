import 'package:quwoquan_app/rtc/rtc/call_session/application/call_participant_presentation.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';

/// 以 chat.ConversationMember 具名 Reader 组合 RTC 参与者展示资料。
///
/// 不写 chat/rtc 聚合，不把展示字段复制回 CallSession wire。
final class ChatMemberCallParticipantPresentationResolver
    implements CallParticipantPresentationResolver {
  const ChatMemberCallParticipantPresentationResolver(this.members);

  final ChatMemberRepository members;

  @override
  Future<Map<String, CallParticipantPresentation>> resolve({
    required String conversationId,
    required Set<String> userIds,
  }) async {
    if (conversationId.trim().isEmpty || userIds.isEmpty) {
      return const <String, CallParticipantPresentation>{};
    }
    final rows = await members.listMembers(
      conversationId: conversationId,
      limit: 200,
      sort: 'joined_asc',
    );
    return <String, CallParticipantPresentation>{
      for (final row in rows)
        if (userIds.contains(row.userId))
          row.userId: CallParticipantPresentation(
            userId: row.userId,
            displayName: row.displayName.trim().isEmpty
                ? row.userId
                : row.displayName.trim(),
            avatarUrl: row.avatarUrl.trim().isEmpty ? null : row.avatarUrl,
            knownInCurrentContext: true,
          ),
    };
  }
}
