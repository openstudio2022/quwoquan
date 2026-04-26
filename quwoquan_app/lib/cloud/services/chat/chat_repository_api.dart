import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_search_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

/// 与云侧 ListMembers `sort` 枚举对齐；非法值回退 `joined_asc`。
List<ChatConversationMemberDto> sortChatMemberDtos(
  List<ChatConversationMemberDto> members,
  String? sort,
) {
  final normalized = switch (sort?.trim()) {
    'display_name_asc' => 'display_name_asc',
    _ => 'joined_asc',
  };
  final copy = List<ChatConversationMemberDto>.from(members);
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

/// Chat 域 Repository：会话、消息、成员、联系人等业务对象入口。
/// 接口与 contracts/metadata/messages/conversation/service.yaml 17 个 API 一一对应。
abstract class ChatRepository {
  // ── 会话 ────────────────────────────────────────────────────────────────────
  /// 收件箱会话列表（强类型，优先用于新代码）。
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 历史 wire 形态会话列表；新实现应优先 [listInbox]。
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<ConversationSearchItemView>> searchConversations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<ChatConversationCreatedDto> createConversation({
    required String type,
    String? title,
    String? circleId,
    String? circleGroupId,
    int? maxGroupSize,
    List<String>? initialMemberIds,
  });

  Future<ConversationDto> getConversation(String conversationId);

  /// 更新会话展示标题（群名等）。Remote 侧按资源 PATCH；无独立 operation 元数据时用 GetConversation 上下文。
  Future<void> updateConversationTitle(String conversationId, String title);

  // ── 消息 ────────────────────────────────────────────────────────────────────
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<MessageSearchItemView>> searchMessages({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    CloudJsonMap? media,
    CloudJsonMap? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderPersonaId,
    String? senderProfileSubjectId,
    String? personaContextVersion,
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    required String clientMsgId,
  });

  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  });

  Future<SyncResponse> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  });

  // ── 已读回执 ──────────────────────────────────────────────────────────────
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  });

  Future<List<ChatMessageReceiptDto>> getReceipts({
    required String conversationId,
    required String messageId,
  });

  // ── 成员管理 ──────────────────────────────────────────────────────────────
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,

    /// 与 metadata 一致：`joined_asc`（默认）、`display_name_asc`；`null` 时 Remote 传 `joined_asc`。
    String? sort,
  });

  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  });

  Future<void> removeMember({
    required String conversationId,
    required String userId,
  });

  // ── 助手参与 ──────────────────────────────────────────────────────────────
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  });

  Future<void> removeAssistant({required String conversationId});

  // ── 用户设置 ──────────────────────────────────────────────────────────────
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  });

  // ── 联系人 ──────────────────────────────────────────────────────────────
  Future<List<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 联系人 Tab「圈子」行（Mock：canonical；Remote：空列表）。
  Future<List<ChatContactTabCircleRowDto>> listContactTabCircles({
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 联系人 Tab「趣群」行（Mock：canonical；Remote：空列表）。
  Future<List<ChatContactTabFunGroupRowDto>> listContactTabFunGroups({
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 搜索联想等：会话成员 userId 列表（Mock：内存成员表；Remote：listMembers）。
  Future<List<String>> listMemberUserIds(String conversationId);

  Future<List<ChatContactSearchItemDto>> searchContacts({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  });

  // ── 会话时间戳索引（端云同步） ─────────────────────────────────────────────
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps();

  Future<List<ConversationDto>> batchGetConversations(List<String> ids);

  // ── 群管理 ──────────────────────────────────────────────────────────────────
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId);

  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsDto settings,
  );

  Future<void> transferOwnership(String conversationId, String newOwnerId);

  Future<void> updateGroupAdmins(String conversationId, List<String> adminIds);

  Future<void> dissolveConversation(String conversationId);
}
