import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_user_state_dto.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 管理单个会话的用户设置（免打扰、置顶、已读）。
class ChatSettingsNotifier extends StateNotifier<ConversationUserStateDto?> {
  ChatSettingsNotifier(this._repo, this.conversationId) : super(null);

  final ChatRepository _repo;
  final String conversationId;

  /// 从会话详情中初始化用户设置。
  void initialize(ConversationUserStateDto userState) {
    state = userState;
  }

  /// 切换免打扰状态。
  Future<void> toggleMute() async {
    final current = state;
    if (current == null) return;
    final newMuted = !current.muted;
    state = ConversationUserStateDto(
      id: current.id,
      userId: current.userId,
      conversationId: current.conversationId,
      readSeq: current.readSeq,
      unreadCount: current.unreadCount,
      muted: newMuted,
      pinned: current.pinned,
      lastReadAt: current.lastReadAt,
      updatedAt: DateTime.now(),
    );
    try {
      await _repo.updateConversationSettings(
        conversationId: conversationId,
        muted: newMuted,
      );
    } catch (_) {
      state = current;
    }
  }

  /// 切换置顶状态。
  Future<void> togglePin() async {
    final current = state;
    if (current == null) return;
    final newPinned = !current.pinned;
    state = ConversationUserStateDto(
      id: current.id,
      userId: current.userId,
      conversationId: current.conversationId,
      readSeq: current.readSeq,
      unreadCount: current.unreadCount,
      muted: current.muted,
      pinned: newPinned,
      lastReadAt: current.lastReadAt,
      updatedAt: DateTime.now(),
    );
    try {
      await _repo.updateConversationSettings(
        conversationId: conversationId,
        pinned: newPinned,
      );
    } catch (_) {
      state = current;
    }
  }

  /// 标记消息已读，同时更新本地 unreadCount。
  Future<void> markAsRead(String messageId) async {
    try {
      await _repo.markAsRead(
        conversationId: conversationId,
        messageId: messageId,
      );
      final current = state;
      if (current != null) {
        state = ConversationUserStateDto(
          id: current.id,
          userId: current.userId,
          conversationId: current.conversationId,
          readSeq: current.readSeq,
          unreadCount: 0,
          muted: current.muted,
          pinned: current.pinned,
          lastReadAt: DateTime.now(),
          updatedAt: DateTime.now(),
        );
      }
    } catch (_) {
      // 静默失败，下次打开会话时再同步
    }
  }
}

/// 按 conversationId 创建独立的会话设置管理器。
final chatSettingsProvider = StateNotifierProvider.family<
    ChatSettingsNotifier, ConversationUserStateDto?, String>(
  (ref, conversationId) {
    final repo = ref.watch(chatRepositoryProvider);
    return ChatSettingsNotifier(repo, conversationId);
  },
);
