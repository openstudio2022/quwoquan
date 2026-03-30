import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';

/// 通话选人列表行（由 Chat 域 DTO 映射，避免 UI 持有 `Map<String, dynamic>`）。
class CallPickerParticipantRow {
  const CallPickerParticipantRow({
    required this.userId,
    required this.displayName,
    this.avatarUrl,
  });

  final String userId;
  final String displayName;
  final String? avatarUrl;

  factory CallPickerParticipantRow.fromContact(ChatContactRowDto c) {
    return CallPickerParticipantRow(
      userId: c.userId,
      displayName: c.displayName,
      avatarUrl: c.avatarUrl.isEmpty ? null : c.avatarUrl,
    );
  }

  factory CallPickerParticipantRow.fromMember(ChatConversationMemberDto m) {
    return CallPickerParticipantRow(
      userId: m.userId,
      displayName: m.displayName,
      avatarUrl: m.avatarUrl.isEmpty ? null : m.avatarUrl,
    );
  }
}
