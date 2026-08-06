import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";

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

  factory CallPickerParticipantRow.fromContact(ChatContactRowViewData c) {
    return CallPickerParticipantRow(
      userId: c.userId,
      displayName: c.displayName,
      avatarUrl: c.avatarUrl.isEmpty ? null : c.avatarUrl,
    );
  }

  factory CallPickerParticipantRow.fromMember(ConversationMemberListRow m) {
    return CallPickerParticipantRow(
      userId: m.userId,
      displayName: m.displayName,
      avatarUrl: m.avatarUrl.isEmpty ? null : m.avatarUrl,
    );
  }
}
