import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/group_home_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/selectable_group_conversation_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';

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

/// Chat 会话读写（收件箱 / 检索 / 创建 / 标题 / 设置 / 时间戳 / 批量）。
///
/// R02：单接口 ≤10 方法。
abstract class ChatConversationRepository {
  // ── 会话 ────────────────────────────────────────────────────────────────────
  /// 收件箱会话列表（强类型，优先用于新代码）。
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 记录 wire 形态会话列表；新实现应优先 [listInbox]。
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<ChatConversationCreatedDto> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  });

  Future<ConversationDto> getConversation(String conversationId);

  /// 更新会话展示标题（群名等），对齐 UpdateConversationTitle operation。
  Future<void> updateConversationTitle(String conversationId, String title);

  // ── 用户设置 ──────────────────────────────────────────────────────────────
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  });

  // ── 会话时间戳索引（端云同步） ─────────────────────────────────────────────
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps();

  Future<List<ConversationDto>> batchGetConversations(List<String> ids);
}

/// Chat 消息收发 / 同步 / 已读回执。
///
/// R02：单接口 ≤10 方法。
abstract class ChatMessageRepository {
  // ── 消息 ────────────────────────────────────────────────────────────────────
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
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
}

/// Chat 会话成员管理 / 助手参与。
///
/// R02：单接口 ≤10 方法。
abstract class ChatMemberRepository {
  // ── 成员管理 ──────────────────────────────────────────────────────────────
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,

    /// 与 metadata 一致：`joined_asc`（默认）、`display_name_asc`；`null` 时 Remote 传 `joined_asc`。
    String? sort,
  });

  /// `ListMembers(query)` 的服务端字面量搜索；@选择器不得只过滤端侧已加载子集。
  Future<List<ChatConversationMemberDto>> searchMembers({
    required String conversationId,
    required String query,
    int limit = CloudApiDefaults.chatMemberSearchLimit,
  });

  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  });

  /// 移出成员（群治理动作，仅 owner/admin；对齐 metadata RemoveMember）。
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  });

  /// 主动退出群聊（自愿离开语义；owner 须先转让，对齐 metadata LeaveConversation）。
  Future<void> leaveConversation(String conversationId);

  /// 搜索联想等：会话成员 userId 列表（Mock：内存成员表；Remote：listMembers）。
  Future<List<String>> listMemberUserIds(String conversationId);

  // ── 助手参与 ──────────────────────────────────────────────────────────────
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  });

  Future<void> removeAssistant({required String conversationId});
}

/// Chat 联系人列表 / 联系人 Tab / 检索。
///
/// R02：单接口 ≤10 方法。
abstract class ChatContactRepository {
  // ── 联系人 ──────────────────────────────────────────────────────────────
  Future<CursorPage<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<ChatContactRowDto>> listGroupCandidates({
    String? conversationId,
    int limit = CloudApiDefaults.pageLimit,
  });
}

enum ChatSelectableGroupSource {
  all,
  group,
  circle;

  String? get wireValue => this == ChatSelectableGroupSource.all ? null : name;
}

/// Chat「从群聊/圈子中选择联系人」二级流程（图四来源列表 / 图五群成员多选）。
///
/// 与 quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml 的
/// `ListSelectableGroupConversations` / `ListSelectableGroupContactMembers`
/// 一一对应。互关好友判定与计数在云侧完成，端侧不再逐群多次拉成员求交集。
///
/// R02：单接口 ≤10 方法。
abstract class ChatGroupSelectionRepository {
  /// 图四：当前用户所在、且含互关联系人的群会话列表，附 `friendMemberCount`。
  /// 云侧已过滤 `friendMemberCount == 0` 的群。
  Future<CursorPage<SelectableGroupConversationRowDto>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 图五：指定群成员中与当前用户互关的联系人（排除当前用户与非 user 成员）。
  Future<CursorPage<ChatContactRowDto>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
}

/// Chat 群管理（治理开关 / 公告 / 转让 / 管理员 / 解散）。
///
/// R02：单接口 ≤10 方法。
abstract class ChatGroupAdminRepository {
  // ── 群管理 ──────────────────────────────────────────────────────────────────
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId);

  Future<GroupHomeDto> getGroupHome(String conversationId);

  /// 更新群治理开关（对齐 metadata UpdateGroupGovernanceSettings；owner/admin）。
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsDto settings,
  );

  Future<void> updateAnnouncement(String conversationId, String announcement);

  Future<void> transferOwnership(String conversationId, String newOwnerId);

  Future<void> updateGroupAdmins(String conversationId, List<String> adminIds);

  Future<void> dissolveConversation(String conversationId);
}

/// Chat 域 Repository：会话、消息、成员、联系人等业务对象入口。
/// 接口与 quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml 17 个 API 一一对应。
///
/// 由 5 个 ≤10 方法子接口组合（R02）。既有消费方继续依赖 `ChatRepository`
/// 不变；新消费方可只依赖所需子接口。
abstract class ChatRepository
    implements
        ChatConversationRepository,
        ChatMessageRepository,
        ChatMemberRepository,
        ChatContactRepository,
        ChatGroupSelectionRepository,
        ChatGroupAdminRepository {}
