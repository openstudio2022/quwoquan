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

    // 推荐实时 patch 以 canonical envelope 字段识别，解析失败直接拒绝。
    if (_routeFeedRealtimePatch(event, payload)) {
      return;
    }

    switch (eventType) {
      case 'MessageSent':
        if (conversationId.isEmpty) return;
        late final MessageDto msg;
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
            _read(chatMessageProvider(conversationId).notifier).loadMessages(),
          );
          return;
        }
        _updateConversationCacheForNewMessage(conversationId, payload);
        if (msg.mediaAssetId?.isNotEmpty ?? false) {
          // MediaAsset delivery fields belong to the named Reader, not the
          // MessageSent event. Refresh through the typed query before render.
          unawaited(
            _read(chatMessageProvider(conversationId).notifier).loadMessages(),
          );
          return;
        }
        _read(chatMessageProvider(conversationId).notifier).addMessage(msg);
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

      case 'ConversationReadWatermarkAdvanced':
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

      case 'ConversationMemberRemoved':
        if (conversationId.isEmpty) return;
        _reloadGroupRosterProviders(conversationId);
        return;

      case 'ConversationUserSettingsChanged':
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

MessageDto _decodeMessageSentEvent(
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

  return MessageDto.fromMap(<String, dynamic>{
    'id': messageId,
    'conversationId': conversationId,
    'seq': seq,
    'clientMsgId': clientMsgId,
    'senderId': senderId,
    'senderName': ?_optionalEventText(payload, 'senderDisplayNameSnapshot'),
    'senderAvatar': ?_optionalEventText(payload, 'senderAvatarUrlSnapshot'),
    'type': type,
    'content': ?_optionalEventText(payload, 'content'),
    'mediaAssetId': ?mediaAssetId,
    'card': ?(cardRaw == null ? null : Map<String, dynamic>.from(cardRaw)),
    'replyToMessageId': ?_optionalEventText(payload, 'replyToMessageId'),
    'mentions': ?(mentionsRaw == null
        ? null
        : List<String>.unmodifiable(List<String>.from(mentionsRaw))),
    'status': 'sent',
    'timestamp': timestamp.toIso8601String(),
  });
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
