import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/ui/chat/models/start_group_pickable_member.dart';

String readStartGroupWireString(Map<String, dynamic> source, List<String> keys) {
  for (final key in keys) {
    final value = source[key];
    if (value == null) {
      continue;
    }
    final text = value.toString().trim();
    if (text.isNotEmpty) {
      return text;
    }
  }
  return '';
}

List<StartGroupPickableMember> selectableFromCircleWireMaps(
  List<Map<String, dynamic>> members, {
  required Set<String> existingMemberIds,
  required Set<String> mutualContactIds,
  bool mutualOnly = false,
}) {
  final normalized = <StartGroupPickableMember>[];
  final seen = <String>{};
  for (final member in members) {
    final userId = readStartGroupWireString(member, const [
      'userId',
      'profileSubjectId',
      'contactId',
    ]);
    if (userId.isEmpty ||
        existingMemberIds.contains(userId) ||
        seen.contains(userId)) {
      continue;
    }
    if (mutualOnly && !mutualContactIds.contains(userId)) {
      continue;
    }
    seen.add(userId);
    final displayName = readStartGroupWireString(member, const [
      'displayName',
      'nickname',
      'name',
      'username',
    ]);
    normalized.add(
      StartGroupPickableMember(
        userId: userId,
        displayName: displayName.isNotEmpty ? displayName : userId,
        avatarUrl: readStartGroupWireString(member, const [
          'avatarUrl',
          'avatar',
          'coverUrl',
        ]),
      ),
    );
  }
  return normalized;
}

List<StartGroupPickableMember> selectableFromChatMembers(
  List<ChatConversationMemberDto> members, {
  required Set<String> existingMemberIds,
  required Set<String> mutualContactIds,
  bool mutualOnly = false,
}) {
  final normalized = <StartGroupPickableMember>[];
  final seen = <String>{};
  for (final m in members) {
    final userId = m.userId;
    if (userId.isEmpty ||
        existingMemberIds.contains(userId) ||
        seen.contains(userId)) {
      continue;
    }
    if (mutualOnly && !mutualContactIds.contains(userId)) {
      continue;
    }
    seen.add(userId);
    final displayName =
        m.displayName.isNotEmpty ? m.displayName : userId;
    normalized.add(
      StartGroupPickableMember(
        userId: userId,
        displayName: displayName,
        avatarUrl: m.avatarUrl,
      ),
    );
  }
  return normalized;
}
