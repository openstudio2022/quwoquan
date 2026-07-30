import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/ui/chat/models/start_group_pickable_member.dart';

List<StartGroupPickableMember> selectableFromChatMembers(
  List<ChatConversationMemberDto> members, {
  required Set<String> mutualContactIds,
  bool mutualOnly = false,
}) {
  final normalized = <StartGroupPickableMember>[];
  final seen = <String>{};
  for (final m in members) {
    final userId = m.userId;
    if (userId.isEmpty || seen.contains(userId)) {
      continue;
    }
    if (mutualOnly && !mutualContactIds.contains(userId)) {
      continue;
    }
    seen.add(userId);
    final displayName = m.displayName.isNotEmpty ? m.displayName : userId;
    normalized.add(
      StartGroupPickableMember(
        userId: userId,
        userHandle: m.userHandle,
        displayName: displayName,
        avatarUrl: m.avatarUrl,
      ),
    );
  }
  return normalized;
}
