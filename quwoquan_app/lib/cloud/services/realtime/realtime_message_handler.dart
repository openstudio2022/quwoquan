import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:riverpod/misc.dart' show ProviderListenable;
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

/// 与 [Ref.read] / [WidgetRef.read] 兼容，避免 `Ref` 与 `WidgetRef` 类型分裂。
typedef ChatProviderRead = T Function<T>(ProviderListenable<T> listenable);

/// Routes incoming realtime events to the appropriate domain handlers.
/// Called by [RealtimeConnectionManager] when a WebSocket or long-poll
/// event arrives.
class RealtimeMessageHandler {
  RealtimeMessageHandler(ChatProviderRead read) : _read = read;

  final ChatProviderRead _read;
  final Set<String> _pendingConversationRefreshes = <String>{};
  Timer? _conversationRefreshTimer;
  Timer? _avatarPatchTimer;
  Timer? _reconnectRecoveryTimer;
  int? _latestHintedSyncSeq;

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
        _read(chatMessageProvider(conversationId).notifier).addMessage(msg);

        _updateConversationCacheForNewMessage(conversationId, payload);
        unawaited(
          _read(localChatSearchSyncProvider).ingestRealtimeMessage(
            conversationId: conversationId,
            payload: payload,
          ),
        );
        return;

      case 'MessageRecalled':
        if (conversationId.isEmpty) return;
        final messageId = payload['messageId'] as String? ?? '';
        if (messageId.isNotEmpty) {
          _read(
            chatMessageProvider(conversationId).notifier,
          ).markRecalled(messageId);
          unawaited(
            _read(localChatSearchSyncProvider).markMessageRecalled(
              conversationId: conversationId,
              messageId: messageId,
            ),
          );
        }
        return;

      case 'ReadReceiptSent':
        return;

      case 'MemberJoined':
        if (conversationId.isEmpty) return;
        _insertSystemMessage(conversationId, payload, '加入了群聊');
        _refreshConversationCache(conversationId);
        return;

      case 'ConversationRosterUpdated':
        if (conversationId.isEmpty) return;
        unawaited(
          _read(conversationMembersProvider(conversationId).notifier).load(),
        );
        _refreshConversationCache(conversationId);
        return;

      case 'ConversationAvatarUpdated':
      case 'UserAvatarUpdated':
        final latestSeq =
            (event['latestSyncSeq'] as num?)?.toInt() ??
            (payload['latestSyncSeq'] as num?)?.toInt();
        _scheduleAvatarPatchSync(latestSeq);
        return;

      case 'MemberLeft':
        if (conversationId.isEmpty) return;
        _insertSystemMessage(conversationId, payload, '离开了群聊');
        _refreshConversationCache(conversationId);
        return;

      case 'ConversationSettingsUpdated':
        if (conversationId.isEmpty) return;
        _refreshConversationCache(conversationId);
        return;

      case 'sync_hint':
        final latestSeq =
            (event['latestSyncSeq'] as num?)?.toInt() ??
            (payload['latestSyncSeq'] as num?)?.toInt();
        _scheduleAvatarPatchSync(latestSeq);
        return;

      case 'Reconnected':
        _onReconnected();
        return;

      default:
        return;
    }
  }

  /// WS 新消息 → 同步更新会话列表缓存的 lastMessage / unreadCount
  void _updateConversationCacheForNewMessage(
    String conversationId,
    Map<String, dynamic> payload,
  ) {
    try {
      final cache = _read(conversationCacheProvider);
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
    _read(chatMessageProvider(conversationId).notifier).addMessage(msg);
  }

  /// 设置/成员变更 → 强制刷新该会话的缓存（下次读取时从云端拉取最新）
  void _refreshConversationCache(String conversationId) {
    _pendingConversationRefreshes.add(conversationId);
    _conversationRefreshTimer?.cancel();
    _conversationRefreshTimer = Timer(const Duration(milliseconds: 160), () {
      try {
        final syncService = _read(conversationSyncProvider);
        unawaited(syncService.sync(force: true));
        final pending = _pendingConversationRefreshes.toList(growable: false);
        _pendingConversationRefreshes.clear();
        for (final id in pending) {
          unawaited(
            _read(
              localChatSearchSyncProvider,
            ).syncConversation(conversationId: id, forceFull: true),
          );
        }
      } catch (_) {}
    });
  }

  /// WS 重连成功 → 触发消息 seq gap 补全 + 会话列表同步
  void _onReconnected() {
    _reconnectRecoveryTimer?.cancel();
    _reconnectRecoveryTimer = Timer(const Duration(milliseconds: 200), () {
      try {
        final syncService = _read(conversationSyncProvider);
        unawaited(syncService.sync(force: true));
        _scheduleAvatarPatchSync(_latestHintedSyncSeq);
        unawaited(_read(localChatSearchSyncProvider).sync(force: true));
      } catch (_) {}
    });
  }

  void _scheduleAvatarPatchSync(int? latestSeq) {
    if (latestSeq != null &&
        latestSeq > 0 &&
        (_latestHintedSyncSeq == null || latestSeq > _latestHintedSyncSeq!)) {
      _latestHintedSyncSeq = latestSeq;
    }
    _avatarPatchTimer?.cancel();
    _avatarPatchTimer = Timer(const Duration(milliseconds: 120), () {
      try {
        final hintedLatestSyncSeq = _latestHintedSyncSeq;
        _latestHintedSyncSeq = null;
        unawaited(
          _read(conversationSyncProvider).syncAvatarPatches(
            hintedLatestSyncSeq: hintedLatestSyncSeq,
            force: true,
          ),
        );
      } catch (_) {}
    });
  }
}
