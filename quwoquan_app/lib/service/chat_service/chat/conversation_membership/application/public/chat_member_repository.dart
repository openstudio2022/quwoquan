import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

List<ConversationMemberListRow> sortChatMemberRows(
  List<ConversationMemberListRow> members,
  String? sort,
) {
  final normalized = switch (sort?.trim()) {
    'display_name_asc' => 'display_name_asc',
    _ => 'joined_asc',
  };
  final copy = List<ConversationMemberListRow>.from(members);
  if (normalized == 'display_name_asc') {
    copy.sort((a, b) {
      final da = a.displayName.isNotEmpty ? a.displayName : a.userId;
      final db = b.displayName.isNotEmpty ? b.displayName : b.userId;
      final c = da.compareTo(db);
      if (c != 0) return c;
      return a.userId.compareTo(b.userId);
    });
  } else {
    copy.sort((a, b) {
      final ta = a.joinedAt?.millisecondsSinceEpoch ?? 0;
      final tb = b.joinedAt?.millisecondsSinceEpoch ?? 0;
      if (ta != tb) return ta.compareTo(tb);
      return a.userId.compareTo(b.userId);
    });
  }
  return copy;
}

abstract interface class ChatMemberRepository {
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    required int limit,
    String? role,
    String? sort,
  });

  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    required int limit,
  });

  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  });

  Future<void> removeMember({
    required String conversationId,
    required String userId,
  });

  Future<void> leaveConversation(String conversationId);

  Future<List<String>> listMemberUserIds(String conversationId);

  Future<void> inviteAssistant({required String conversationId});

  Future<void> removeAssistant({required String conversationId});
}
