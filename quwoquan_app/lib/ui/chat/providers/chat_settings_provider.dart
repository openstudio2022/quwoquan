import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_user_state_dto.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 管理单个会话的用户设置（免打扰、置顶、已读）。
class ChatSettingsNotifier extends Notifier<ConversationUserStateDto?> {
  ChatSettingsNotifier(this.conversationId);

  final String conversationId;

  ChatMessageRepository get _messageRepo =>
      ref.read(chatMessageRepositoryProvider);
  ChatConversationRepository get _conversationRepo =>
      ref.read(chatConversationRepositoryProvider);

  @override
  ConversationUserStateDto? build() => null;

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
      await _conversationRepo.updateConversationSettings(
        conversationId: conversationId,
        muted: newMuted,
      );
    } catch (error, stackTrace) {
      // 乐观切换失败回滚，并结构化上报。
      state = current;
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'chat.settings.toggle_mute',
          error: error,
          stackTrace: stackTrace,
        ),
      );
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
      await _conversationRepo.updateConversationSettings(
        conversationId: conversationId,
        pinned: newPinned,
      );
    } catch (error, stackTrace) {
      // 乐观切换失败回滚，并结构化上报。
      state = current;
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'chat.settings.toggle_pin',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  /// 标记消息已读，同时更新本地 unreadCount。
  Future<void> markAsRead(String messageId) async {
    try {
      await _messageRepo.markAsRead(
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
    } catch (error, stackTrace) {
      // 已读失败允许下次打开会话再同步，但必须上报（静默即未读角标漂移不可查）。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'chat.settings.mark_as_read',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }
}

/// 按 conversationId 创建独立的会话设置管理器。
final chatSettingsProvider =
    NotifierProvider.family<
      ChatSettingsNotifier,
      ConversationUserStateDto?,
      String
    >(ChatSettingsNotifier.new);
