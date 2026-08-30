import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:riverpod/misc.dart' show ProviderListenable, ProviderOrFamily;
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/group_home_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/feed_realtime_patch_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 与 [Ref.read] / [WidgetRef.read] 兼容，避免 `Ref` 与 `WidgetRef` 类型分裂。
typedef ChatProviderRead = T Function<T>(ProviderListenable<T> listenable);

/// 与 [Ref.invalidate] 兼容，用于 roster / avatar 事件后刷新 group home。
typedef ChatProviderInvalidate = void Function(
  ProviderOrFamily provider, {
  bool asReload,
});

/// Routes incoming realtime events to the appropriate domain handlers.
/// Called by realtime connection delegates when a WebSocket, long-poll,
/// or mock catalog event arrives.
class RealtimeMessageHandler {
  RealtimeMessageHandler(
    ChatProviderRead read, {
    this.invalidate,
    String Function()? currentUserIdResolver,
  }) : _read = read,
       _currentUserIdResolver = currentUserIdResolver ?? _emptyCurrentUserId;

  final ChatProviderRead _read;
  final ChatProviderInvalidate? invalidate;
  final String Function() _currentUserIdResolver;
  final Set<String> _pendingConversationRefreshes = <String>{};
  Timer? _conversationRefreshTimer;
  Timer? _avatarPatchTimer;
  bool _disposed = false;

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _conversationRefreshTimer?.cancel();
    _conversationRefreshTimer = null;
    _avatarPatchTimer?.cancel();
    _avatarPatchTimer = null;
    _pendingConversationRefreshes.clear();
  }

  Future<void> handleAndWait(Map<String, dynamic> event) async {
    _requireActive();
    final eventType = event['type'] as String? ?? '';
    if (eventType == 'Reconnected') {
      final conversationId = event['conversationId'] as String? ?? '';
      await _onReconnected(conversationId);
      return;
    }
    handle(event);
  }

  void handle(Map<String, dynamic> event) {
    if (_disposed) return;
    final eventType = event['type'] as String? ?? '';
    final conversationId = event['conversationId'] as String? ?? '';
    final payload = event['payload'] as Map<String, dynamic>? ?? event;

    // 推荐实时 patch 以 canonical envelope 字段识别，解析失败直接拒绝。
    if (_routeFeedRealtimePatch(event, payload)) {
      return;
    }

    // rtc 通话信令（rt:rtc:user 通道，wire type call.* / participant.* /
    // screen_share.*）分发给通话事件总线，由来电协调器与通话页订阅。
    if (isRtcSignalWireType(eventType)) {
      _read(rtcSignalEventBusProvider)
          .emit(RealtimeEventEnvelope.fromWire(event));
      return;
    }

    switch (eventType) {
      case 'MessageSent':
        if (conversationId.isEmpty) return;
        late final ChatMessageViewData msg;
        try {
          msg = _decodeMessageSentEvent(conversationId, payload);
        } on FormatException catch (error, stackTrace) {
          developer.log(
            'rejected malformed MessageSent event',
            name: 'RealtimeMessageHandler',
            error: error,
            stackTrace: stackTrace,
          );
          unawaited(
            _read(chatMessageTimelineControllerProvider(conversationId))
                .loadMessages(),
          );
          return;
        }
        _updateConversationCacheForNewMessage(conversationId, payload);
        if (msg.mediaAssetId?.isNotEmpty ?? false) {
          // MediaAsset delivery fields belong to the named Reader, not the
          // MessageSent event. Refresh through the typed query before render.
          unawaited(
            _read(chatMessageTimelineControllerProvider(conversationId))
                .loadMessages(),
          );
          return;
        }
        _read(chatMessageTimelineControllerProvider(conversationId))
            .addMessage(msg);
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
          _read(chatMessageTimelineControllerProvider(conversationId))
              .markRecalled(messageId);
          unawaited(
            _read(localChatSearchSyncProvider).markMessageRecalled(
              conversationId: conversationId,
              messageId: messageId,
            ),
          );
        }
        return;

      case 'ConversationReadWatermarkAdvanced':
        if (conversationId.isEmpty) return;
        final readerUserId = (payload['userId'] as String? ?? '').trim();
        final readSeqRaw = payload['readSeq'];
        final readSeq = readSeqRaw is int
            ? readSeqRaw
            : int.tryParse(readSeqRaw?.toString() ?? '') ?? 0;
        if (readerUserId.isEmpty || readSeq <= 0) return;
        final currentUserId = _currentUserIdResolver().trim();
        if (currentUserId.isNotEmpty && readerUserId == currentUserId) {
          // 自己在其它设备读了：本地未读角标以服务端投影为准，刷新缓存。
          _refreshConversationCache(conversationId);
          return;
        }
        // 对端读位推进 → 1v1 双勾实时翻转（群聊指示器按 memberCount 保持单勾）。
        _read(chatMessageTimelineControllerProvider(conversationId))
            .advancePeerReadSeq(readSeq);
        return;

      case 'ConversationMemberAdded':
        if (conversationId.isEmpty) return;
        _reloadGroupRosterProviders(conversationId);
        return;

      case 'ConversationRosterUpdated':
        if (conversationId.isEmpty) return;
        _reloadGroupRosterProviders(conversationId);
        return;

      case 'UserAvatarUpdated':
        _scheduleAvatarPatchSync();
        if (conversationId.isNotEmpty) {
          unawaited(
            _read(conversationMembersProvider(conversationId).notifier).load(),
          );
          invalidate?.call(groupHomeProvider(conversationId));
          _refreshConversationCache(conversationId);
        }
        return;

      case 'ConversationAvatarUpdated':
        _scheduleAvatarPatchSync();
        if (conversationId.isNotEmpty) {
          invalidate?.call(groupHomeProvider(conversationId));
          _refreshConversationCache(conversationId);
        }
        return;

      case 'ConversationMemberRemoved':
      case 'ConversationMemberLeft':
        if (conversationId.isEmpty) return;
        _handleTerminalMembershipEvent(conversationId, payload);
        return;

      case 'ConversationUserSettingsChanged':
        if (conversationId.isEmpty) return;
        _refreshConversationCache(conversationId);
        return;

      case 'sync_hint':
        _scheduleAvatarPatchSync();
        return;

      case 'Reconnected':
        unawaited(_ignoreRecoveryFailure(_onReconnected(conversationId)));
        return;

      default:
        return;
    }
  }

  static String _emptyCurrentUserId() => '';

  void _requireActive() {
    if (_disposed) {
      throw StateError('realtime message handler is disposed');
    }
  }

  // Removal/leave events are delivered to the affected user in addition to the
  // post-mutation roster. That user must purge all local copies immediately:
  // the server has deleted ConversationUserState, so retaining cached messages
  // or an inbox card would expose an inaccessible conversation until a later
  // full sync.
  void _handleTerminalMembershipEvent(
    String conversationId,
    Map<String, dynamic> payload,
  ) {
    final affectedUserId = (payload['userId'] as String? ?? '').trim();
    final currentUserId = _currentUserIdResolver().trim();
    if (affectedUserId.isEmpty ||
        currentUserId.isEmpty ||
        affectedUserId != currentUserId) {
      _reloadGroupRosterProviders(conversationId);
      return;
    }
    _read(chatInboxCacheProvider).removeInbox(conversationId);
    _read(chatMessageTimelineControllerProvider(conversationId))
        .clearLocalTimeline();
    invalidate?.call(conversationMembersProvider(conversationId));
    invalidate?.call(groupHomeProvider(conversationId));
    unawaited(
      _read(localChatSearchSyncProvider).removeConversation(conversationId),
    );
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
    _read(feedRealtimePatchProvider.notifier).applyPatch(patch);
    return true;
  }

  /// feed patch 候选载荷：顶层或 payload 内带 canonical patch 标识。
  Map<String, dynamic>? _feedPatchCandidate(
    Map<String, dynamic> event,
    Map<String, dynamic> payload,
  ) {
    if (event['patchId'] is String && event['patchType'] is String) {
      return event;
    }
    if (payload['patchId'] is String && payload['patchType'] is String) {
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
      final cache = _read(chatInboxCacheProvider);
      final preview = payload['content'] as String? ?? '';
      final timestamp = payload['timestamp'] as String? ?? '';
      final existing = cache.readInboxEntry(conversationId);
      final currentUnread = existing?.unreadCount ?? 0;

      // 展示性提示：+1 只用于即时角标；未读真相源是服务端 inbox 投影，
      // 下一次 sync/ListInbox 会以服务端值覆盖本地提示值。
      cache.applyOptimisticInboxHint(
        conversationId,
        ChatInboxOptimisticHint(
          lastMessagePreview: preview,
          lastMessageAt: DateTime.tryParse(timestamp),
          unreadCount: currentUnread + 1,
        ),
      );
    } catch (error, stackTrace) {
      // best-effort：补丁失败仅影响列表预览即时性，下次同步拉最新态；仍上报观测。
      unawaited(
        _read(exceptionTelemetryPortProvider).recordGlobalException(
          source: 'chat.realtime.conversation_list_patch',
          exceptionText: error.toString(),
          stackText: stackTrace.toString(),
        ),
      );
    }
  }

  /// 成员 / roster 变更 → 刷新成员 provider、group home 与缓存。
  void _reloadGroupRosterProviders(String conversationId) {
    unawaited(
      _read(conversationMembersProvider(conversationId).notifier).load(),
    );
    invalidate?.call(groupHomeProvider(conversationId));
    _refreshConversationCache(conversationId);
  }

  /// 设置/成员变更 → 强制刷新该会话的缓存（下次读取时从云端拉取最新）
  void _refreshConversationCache(String conversationId) {
    if (_disposed) return;
    _pendingConversationRefreshes.add(conversationId);
    _conversationRefreshTimer?.cancel();
    _conversationRefreshTimer = Timer(const Duration(milliseconds: 160), () {
      _conversationRefreshTimer = null;
      if (_disposed) return;
      try {
        final syncService = _read(conversationSyncProvider);
        unawaited(syncService.sync(force: true));
        final pending = _pendingConversationRefreshes.toList(growable: false);
        _pendingConversationRefreshes.clear();
        for (final id in pending) {
          unawaited(
            _read(localChatSearchSyncProvider)
                .syncConversation(conversationId: id, forceFull: true),
          );
        }
      } catch (error, stackTrace) {
        // best-effort：维持现有缓存，下次读取从云端补齐；上报以免静默退化。
        unawaited(
          _read(exceptionTelemetryPortProvider).recordGlobalException(
            source: 'chat.realtime.conversation_cache_refresh',
            exceptionText: error.toString(),
            stackText: stackTrace.toString(),
          ),
        );
      }
    });
  }

  Future<void> _ignoreRecoveryFailure(Future<void> recovery) async {
    try {
      await recovery;
    } on Object {
      // Detached WebSocket recovery has no transport cursor to hold. The
      // awaited path records telemetry before propagating the failure.
    }
  }

  /// 传输重连成功 → 等待消息 seq gap 补全完成后才确认事件消费。
  Future<void> _onReconnected(String conversationId) async {
    _requireActive();
    try {
      await _read(conversationSyncProvider).sync(force: true);
      _requireActive();
      _scheduleAvatarPatchSync();
      await _read(localChatSearchSyncProvider).sync(force: true);
      _requireActive();
      await _recoverConversationSeqGap(conversationId);
      _requireActive();
    } catch (error, stackTrace) {
      if (_disposed) {
        // Delegate/container teardown may race any awaited recovery step.
        // Preserve the lifecycle failure for the awaiting transport without
        // touching telemetry providers owned by the disposed container.
        Error.throwWithStackTrace(error, stackTrace);
      }
      // 重连补全失败若静默即丢消息不可观测：记录后向 awaited transport
      // 边界传播，使 LongPoll 保留已提交 cursor 并从同一点重试。
      unawaited(
        _read(exceptionTelemetryPortProvider).recordGlobalException(
          source: 'chat.realtime.reconnect_gap_recovery',
          exceptionText: error.toString(),
          stackText: stackTrace.toString(),
        ),
      );
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  /// 恢复事件携带活跃会话时，以端侧已持有的最大 seq 为起点向服务端补齐缺口；
  /// 补齐结果与实时推送经同一去重链路合并（reliability REQ-003/REQ-008）。
  Future<void> _recoverConversationSeqGap(String conversationId) async {
    if (conversationId.isEmpty) {
      return;
    }
    final controller = _read(
      chatMessageTimelineControllerProvider(conversationId),
    );
    var localMaxSeq = 0;
    for (final message in _read(
      chatMessageTimelineProvider(conversationId),
    ).messages) {
      if (message.seq > localMaxSeq) {
        localMaxSeq = message.seq;
      }
    }
    if (localMaxSeq > 0) {
      await controller.syncFromSeq(localMaxSeq);
    } else {
      await controller.loadMessages();
      _requireActive();
      final recovered = _read(chatMessageTimelineProvider(conversationId));
      if (recovered.isLoading ||
          recovered.isRefreshing ||
          recovered.source != ChatTimelineContentSource.remoteSynced) {
        throw StateError('initial timeline recovery did not reach remote sync');
      }
    }
  }

  void _scheduleAvatarPatchSync() {
    if (_disposed) return;
    _avatarPatchTimer?.cancel();
    _avatarPatchTimer = Timer(const Duration(milliseconds: 120), () {
      _avatarPatchTimer = null;
      if (_disposed) return;
      try {
        unawaited(
          _read(conversationSyncProvider).syncAvatarPatches(force: true),
        );
      } catch (error, stackTrace) {
        // best-effort：仅影响头像即时刷新，后续同步补齐；上报保留观测面。
        unawaited(
          _read(exceptionTelemetryPortProvider).recordGlobalException(
            source: 'chat.realtime.avatar_patch_sync',
            exceptionText: error.toString(),
            stackText: stackTrace.toString(),
          ),
        );
      }
    });
  }
}

ChatMessageViewData _decodeMessageSentEvent(
  String conversationId,
  Map<String, dynamic> payload,
) {
  const allowed = <String>{
    'messageId',
    'conversationId',
    'seq',
    'clientMsgId',
    'senderId',
    'type',
    'content',
    'mediaAssetId',
    'card',
    'replyToMessageId',
    'mentions',
    'personaContextVersion',
    'senderDisplayNameSnapshot',
    'senderAvatarUrlSnapshot',
    'timestamp',
  };
  final unknown = payload.keys
      .where((key) => !allowed.contains(key))
      .toList(growable: false);
  if (unknown.isNotEmpty) {
    throw FormatException(
      'MessageSent contains unknown fields: ${unknown.join(',')}',
    );
  }

  final messageId = _requiredEventText(payload, 'messageId');
  final payloadConversationId = _requiredEventText(payload, 'conversationId');
  if (payloadConversationId != conversationId) {
    throw const FormatException(
      'MessageSent.conversationId does not match event envelope',
    );
  }
  final clientMsgId = _requiredEventText(payload, 'clientMsgId');
  final senderId = _requiredEventText(payload, 'senderId');
  final type = _requiredEventText(payload, 'type');
  const allowedTypes = <String>{
    'text',
    'audio',
    'image',
    'video',
    'file',
    'card',
  };
  if (!allowedTypes.contains(type)) {
    throw const FormatException('MessageSent.type is unsupported');
  }
  final seq = payload['seq'];
  if (seq is! int || seq <= 0) {
    throw const FormatException('MessageSent.seq must be a positive integer');
  }
  final timestampText = _requiredEventText(payload, 'timestamp');
  final timestamp = DateTime.tryParse(timestampText);
  if (timestamp == null) {
    throw const FormatException('MessageSent.timestamp must be ISO-8601');
  }
  final mentionsRaw = payload['mentions'];
  if (mentionsRaw != null &&
      (mentionsRaw is! List || mentionsRaw.any((value) => value is! String))) {
    throw const FormatException('MessageSent.mentions must be string[]');
  }
  final personaContextVersion = payload['personaContextVersion'];
  if (personaContextVersion != null &&
      (personaContextVersion is! int || personaContextVersion <= 0)) {
    throw const FormatException(
      'MessageSent.personaContextVersion must be a positive integer',
    );
  }
  final mediaAssetId = _optionalEventText(payload, 'mediaAssetId');
  const mediaTypes = <String>{'audio', 'image', 'video', 'file'};
  if (mediaTypes.contains(type) != (mediaAssetId != null)) {
    throw const FormatException(
      'MessageSent media type and mediaAssetId must match',
    );
  }
  final cardRaw = payload['card'];
  if (cardRaw != null &&
      (cardRaw is! Map || cardRaw.keys.any((key) => key is! String))) {
    throw const FormatException('MessageSent.card must be an object');
  }
  if ((type == 'card') != (cardRaw != null)) {
    throw const FormatException('MessageSent card type and card must match');
  }

  return ChatMessageViewData.fromWire(
    ChatMessageView(
      id: messageId,
      conversationId: conversationId,
      seq: seq,
      clientMsgId: clientMsgId,
      senderId: senderId,
      senderName: _optionalEventText(payload, 'senderDisplayNameSnapshot'),
      senderAvatar: _optionalEventText(payload, 'senderAvatarUrlSnapshot'),
      type: MessageType.fromWire(type, 'MessageSent.type'),
      content: _optionalEventText(payload, 'content'),
      mediaAssetId: mediaAssetId,
      card: cardRaw == null
          ? null
          : MessageCard.fromWire(
              Map<String, Object?>.from(cardRaw),
              'MessageSent.card',
            ),
      replyToMessageId: _optionalEventText(payload, 'replyToMessageId'),
      mentions: mentionsRaw == null
          ? null
          : List<String>.unmodifiable(List<String>.from(mentionsRaw)),
      status: MessageStatus.sent,
      timestamp: timestamp,
    ),
  );
}

String _requiredEventText(Map<String, dynamic> payload, String field) {
  final value = payload[field];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('MessageSent.$field must be a non-empty string');
  }
  return value.trim();
}

String? _optionalEventText(Map<String, dynamic> payload, String field) {
  final value = payload[field];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('MessageSent.$field must be a string');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}
