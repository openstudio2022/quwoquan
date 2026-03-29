import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

/// Routes incoming realtime events to the appropriate domain handlers.
/// Called by [RealtimeConnectionManager] when a WebSocket or long-poll
/// event arrives.
class RealtimeMessageHandler {
  RealtimeMessageHandler(this._ref);

  final Ref _ref;

  void handle(Map<String, dynamic> event) {
    final eventType = event['type'] as String? ?? '';
    final conversationId = event['conversationId'] as String? ?? '';
    final payload = event['payload'] as Map<String, dynamic>? ?? event;

    switch (eventType) {
      case 'MessageSent':
        if (conversationId.isEmpty) return;
        final msg = MessageDto.fromMap({
          ...payload,
          'conversationId': conversationId,
        });
        _ref.read(chatMessageProvider(conversationId).notifier).addMessage(msg);

        _updateConversationCacheForNewMessage(conversationId, payload);
        unawaited(
          _ref
              .read(localChatSearchSyncProvider)
              .ingestRealtimeMessage(
                conversationId: conversationId,
                payload: payload,
              ),
        );

      case 'MessageRecalled':
        if (conversationId.isEmpty) return;
        final messageId = payload['messageId'] as String? ?? '';
        if (messageId.isNotEmpty) {
          _ref
              .read(chatMessageProvider(conversationId).notifier)
              .markRecalled(messageId);
          unawaited(
            _ref
                .read(localChatSearchSyncProvider)
                .markMessageRecalled(
                  conversationId: conversationId,
                  messageId: messageId,
                ),
          );
        }

      case 'ReadReceiptSent':
        break;

      case 'MemberJoined':
        if (conversationId.isEmpty) return;
        _insertSystemMessage(conversationId, payload, '加入了群聊');
        _refreshConversationCache(conversationId);

      case 'MemberLeft':
        if (conversationId.isEmpty) return;
        _insertSystemMessage(conversationId, payload, '离开了群聊');
        _refreshConversationCache(conversationId);

      case 'ConversationSettingsUpdated':
        if (conversationId.isEmpty) return;
        _refreshConversationCache(conversationId);

      case 'Reconnected':
        _onReconnected();

      default:
        break;
    }
  }

  /// WS 新消息 → 同步更新会话列表缓存的 lastMessage / unreadCount
  void _updateConversationCacheForNewMessage(
    String conversationId,
    Map<String, dynamic> payload,
  ) {
    try {
      final cache = _ref.read(conversationCacheProvider);
      final preview = payload['content'] as String? ?? '';
      final timestamp = payload['timestamp'] as String? ?? '';
      final existing = cache.get(conversationId);
      final currentUnread = existing?['unreadCount'] as int? ?? 0;

      cache.updateListFields(
        conversationId,
        lastMessagePreview: preview,
        lastMessageAt: timestamp,
        unreadCount: currentUnread + 1,
      );
    } catch (_) {}
  }

  /// 成员变更 → 插入系统消息到对话
  void _insertSystemMessage(
    String conversationId,
    Map<String, dynamic> payload,
    String action,
  ) {
    final userName =
        payload['userName'] as String? ??
        payload['displayName'] as String? ??
        '';
    final msg = MessageDto(
      id: 'sys_${DateTime.now().millisecondsSinceEpoch}',
      conversationId: conversationId,
      seq: 0,
      clientMsgId: '',
      senderId: 'system',
      type: 'system',
      content: '$userName$action',
      status: 'sent',
      timestamp: DateTime.tryParse(payload['timestamp'] as String? ?? ''),
    );
    _ref.read(chatMessageProvider(conversationId).notifier).addMessage(msg);
  }

  /// 设置/成员变更 → 强制刷新该会话的缓存（下次读取时从云端拉取最新）
  void _refreshConversationCache(String conversationId) {
    try {
      final syncService = _ref.read(conversationSyncProvider);
      syncService.sync(force: true);
      unawaited(
        _ref
            .read(localChatSearchSyncProvider)
            .syncConversation(conversationId: conversationId, forceFull: true),
      );
    } catch (_) {}
  }

  /// WS 重连成功 → 触发消息 seq gap 补全 + 会话列表同步
  void _onReconnected() {
    try {
      final syncService = _ref.read(conversationSyncProvider);
      syncService.sync(force: true);
      unawaited(_ref.read(localChatSearchSyncProvider).sync(force: true));
    } catch (_) {}
  }
}
