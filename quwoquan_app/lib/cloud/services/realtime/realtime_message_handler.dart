import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:riverpod/misc.dart' show ProviderListenable, ProviderOrFamily;
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/group_home_provider.dart';
import 'package:quwoquan_app/ui/discovery/providers/feed_realtime_patch_provider.dart';

/// 与 [Ref.read] / [WidgetRef.read] 兼容，避免 `Ref` 与 `WidgetRef` 类型分裂。
typedef ChatProviderRead = T Function<T>(ProviderListenable<T> listenable);

/// 与 [Ref.invalidate] 兼容，用于 roster / avatar 事件后刷新 group home。
typedef ChatProviderInvalidate =
    void Function(ProviderOrFamily provider, {bool asReload});

/// Routes incoming realtime events to the appropriate domain handlers.
/// Called by realtime connection delegates when a WebSocket, long-poll,
/// or mock catalog event arrives.
class RealtimeMessageHandler {
  RealtimeMessageHandler(ChatProviderRead read, {this._invalidate})
    : _read = read;

  final ChatProviderRead _read;
  final ChatProviderInvalidate? _invalidate;
  final Set<String> _pendingConversationRefreshes = <String>{};
  Timer? _conversationRefreshTimer;
  Timer? _avatarPatchTimer;
  Timer? _reconnectRecoveryTimer;
  int? _latestHintedSyncSeq;

  void handle(Map<String, dynamic> event) {
    final eventType = event['type'] as String? ?? '';
    final conversationId = event['conversationId'] as String? ?? '';
    final payload = event['payload'] as Map<String, dynamic>? ?? event;

    // 推荐实时 patch（以 schema_version 标识，与 chat 事件的 `type` 分流）：
    // 解析为强类型后交给 discovery patch 安全消费者；schema 不符则前向兼容忽略。
    if (_routeFeedRealtimePatch(event, payload)) {
      return;
    }

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
          _read(
            localChatSearchSyncProvider,
          ).ingestRealtimeMessage(conversationId: conversationId, message: msg),
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
        _insertSystemMessage(conversationId, payload, '加入了讨论');
        _reloadGroupRosterProviders(conversationId);
        return;

      case 'ConversationRosterUpdated':
        if (conversationId.isEmpty) return;
        _reloadGroupRosterProviders(conversationId);
        return;

      case 'UserAvatarUpdated':
        final userLatestSeq =
            (event['latestSyncSeq'] as num?)?.toInt() ??
            (payload['latestSyncSeq'] as num?)?.toInt();
        _scheduleAvatarPatchSync(userLatestSeq);
        if (conversationId.isNotEmpty) {
          unawaited(
            _read(conversationMembersProvider(conversationId).notifier).load(),
          );
          _invalidate?.call(groupHomeProvider(conversationId));
          _refreshConversationCache(conversationId);
        }
        return;

      case 'ConversationAvatarUpdated':
        final conversationLatestSeq =
            (event['latestSyncSeq'] as num?)?.toInt() ??
            (payload['latestSyncSeq'] as num?)?.toInt();
        _scheduleAvatarPatchSync(conversationLatestSeq);
        if (conversationId.isNotEmpty) {
          _invalidate?.call(groupHomeProvider(conversationId));
          _refreshConversationCache(conversationId);
        }
        return;

      case 'MemberLeft':
        if (conversationId.isEmpty) return;
        _insertSystemMessage(conversationId, payload, '离开了讨论');
        _reloadGroupRosterProviders(conversationId);
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

  /// 识别并路由推荐实时 patch。返回 true 表示该事件已被识别为 feed patch
  /// （命中后不再落入 chat 事件 switch），无论是否成功解析。
  bool _routeFeedRealtimePatch(
    Map<String, dynamic> event,
    Map<String, dynamic> payload,
  ) {
    final candidate = _feedPatchCandidate(event, payload);
    if (candidate == null) {
      return false;
    }
    final patch = parseFeedRealtimePatch(candidate);
    if (patch == null) {
      // schema 不符 / 未来版本：结构化记录后忽略（不解析未知 schema）。
      developer.log(
        'ignored feed realtime patch with unsupported schema_version',
        name: 'RealtimeMessageHandler',
      );
      return true;
    }
    _read(feedRealtimePatchProvider.notifier).applyPatch(patch);
    return true;
  }

  /// feed patch 候选载荷：顶层或 payload 内带 `feed_patch*` schema 标识。
  Map<String, dynamic>? _feedPatchCandidate(
    Map<String, dynamic> event,
    Map<String, dynamic> payload,
  ) {
    final topSchema = event['schemaVersion'];
    if (topSchema is String && topSchema.startsWith('feed_patch')) {
      return event;
    }
    final payloadSchema = payload['schemaVersion'];
    if (payloadSchema is String && payloadSchema.startsWith('feed_patch')) {
      return payload;
    }
    return null;
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
      final currentUnread = existing?.unreadCount ?? 0;

      cache.applyListPatch(
        conversationId,
        ConversationListPatch(
          lastMessagePreview: preview,
          lastMessageAt: timestamp,
          unreadCount: currentUnread + 1,
        ),
      );
    } catch (_) {
      /* best-effort: 应用会话列表补丁失败仅影响列表预览即时性，下次同步会拉到最新态 */
    }
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

  /// 成员 / roster 变更 → 刷新成员 provider、group home 与缓存。
  void _reloadGroupRosterProviders(String conversationId) {
    unawaited(
      _read(conversationMembersProvider(conversationId).notifier).load(),
    );
    _invalidate?.call(groupHomeProvider(conversationId));
    _refreshConversationCache(conversationId);
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
      } catch (_) {
        /* best-effort: 强制刷新会话缓存失败时维持现有缓存，下次读取会从云端补齐 */
      }
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
      } catch (_) {
        /* best-effort: 重连后触发的补全同步失败由下一次心跳/重连或主动刷新再次兜底 */
      }
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
      } catch (_) {
        /* best-effort: 头像补丁同步失败仅影响头像即时刷新，后续同步会补齐 */
      }
    });
  }
}
