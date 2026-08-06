import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/chat/chat/message/domain/message_dto.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_message_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/chat/chat/message/domain/chat_message_media_view_data.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_send_outbox.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const _uuid = Uuid();

/// 消息列表状态：含加载态、错误信息和已排序消息列表。
class ChatMessageState {
  final List<ChatMessageViewData> messages;
  final bool isLoading;
  final bool isRefreshing;
  final bool isLoadingOlder;
  final bool hasMore;
  final int nextBeforeSeq;
  final String? error;

  const ChatMessageState({
    this.messages = const [],
    this.isLoading = false,
    this.isRefreshing = false,
    this.isLoadingOlder = false,
    this.hasMore = true,
    this.nextBeforeSeq = 0,
    this.error,
  });

  ChatMessageState copyWith({
    List<ChatMessageViewData>? messages,
    bool? isLoading,
    bool? isRefreshing,
    bool? isLoadingOlder,
    bool? hasMore,
    int? nextBeforeSeq,
    String? error,
  }) {
    return ChatMessageState(
      messages: messages ?? this.messages,
      isLoading: isLoading ?? this.isLoading,
      isRefreshing: isRefreshing ?? this.isRefreshing,
      isLoadingOlder: isLoadingOlder ?? this.isLoadingOlder,
      hasMore: hasMore ?? this.hasMore,
      nextBeforeSeq: nextBeforeSeq ?? this.nextBeforeSeq,
      error: error,
    );
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        other is ChatMessageState &&
            other.messages == messages &&
            other.isLoading == isLoading &&
            other.isRefreshing == isRefreshing &&
            other.isLoadingOlder == isLoadingOlder &&
            other.hasMore == hasMore &&
            other.nextBeforeSeq == nextBeforeSeq &&
            other.error == error;
  }

  @override
  int get hashCode => Object.hash(
    messages,
    isLoading,
    isRefreshing,
    isLoadingOlder,
    hasMore,
    nextBeforeSeq,
    error,
  );
}

/// 管理单个会话的消息列表、发送、撤回、seq gap 补全。
class ChatMessageNotifier extends Notifier<ChatMessageState> {
  ChatMessageNotifier(this.conversationId);

  final String conversationId;

  ChatMessageRepository get _repo => ref.read(chatMessageRepositoryProvider);
  ChatMemberRepository get _memberRepo =>
      ref.read(chatMemberRepositoryProvider);
  ChatMessageCommandWriter get _writer =>
      ref.read(chatMessageCommandWriterProvider);

  @override
  ChatMessageState build() {
    return const ChatMessageState();
  }

  // seq=0 表示消息尚未被服务端确认（发送中/发送失败）
  static const int _unconfirmedSeq = 0;
  static const int _pageSize = 50;

  Future<ActivePersonaContextViewData> _resolveActivePersonaContext() async {
    final activeContext = await ref.read(activePersonaContextProvider.future);
    if (ref
            .read(contentConfigRepositoryProvider)
            .requiresResolvedPersonaForMutations &&
        activeContext.isFallback) {
      throw StateError('active persona context unavailable');
    }
    return activeContext;
  }

  /// 加载消息并按 seq 排序，之后检测 gap。
  Future<void> loadMessages({int? maxSeq}) async {
    if (state.isLoading || state.isRefreshing) return;
    final hadVisibleMessages = state.messages.isNotEmpty;
    state = state.copyWith(
      isLoading: !hadVisibleMessages,
      isRefreshing: hadVisibleMessages,
      error: null,
    );
    final namespace = await _resolveLocalNamespace();
    if (!hadVisibleMessages && namespace != null) {
      try {
        final cached = await ref
            .read(localChatSearchStoreProvider)
            .readTimeline(
              namespace: namespace,
              conversationId: conversationId,
              limit: _pageSize,
            );
        if (!ref.mounted) return;
        if (cached.value.isNotEmpty) {
          state = state.copyWith(
            messages: _sorted(cached.value),
            isLoading: false,
            isRefreshing: true,
            nextBeforeSeq: _oldestConfirmedSeq(cached.value),
          );
        }
      } catch (error, stackTrace) {
        _recordLocalTimelineFailure(
          operation: 'read_latest',
          error: error,
          stackTrace: stackTrace,
        );
      }
    }
    try {
      final loaded = await _repo.listMessages(
        conversationId: conversationId,
        limit: _pageSize,
      );
      final hydrated = await _hydrateSenderSnapshots(
        loaded.map(_normalizeSenderAvatar).toList(growable: false),
      );
      if (!ref.mounted) return;
      final merged = _mergeMessages(state.messages, hydrated);
      state = state.copyWith(
        messages: _sorted(merged),
        isLoading: false,
        isRefreshing: false,
        hasMore: loaded.length >= _pageSize,
        nextBeforeSeq: _oldestConfirmedSeq(merged),
      );
      unawaited(_persistMessages(hydrated, namespace: namespace));
      if (maxSeq != null && maxSeq > 0) {
        await _detectAndFillGap(maxSeq);
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        isLoading: false,
        isRefreshing: false,
        error: runtimeErrorDisplayMessage(e),
      );
    }
  }

  /// 读取更早一页；本地命中先展示，远端 beforeSeq 校准后合并。
  Future<int> loadOlderMessages() async {
    if (state.isLoadingOlder || !state.hasMore) return 0;
    final beforeSeq = _oldestConfirmedSeq(state.messages);
    if (beforeSeq <= 0) return 0;
    final previousCount = state.messages.length;
    state = state.copyWith(isLoadingOlder: true, error: null);
    final namespace = await _resolveLocalNamespace();
    if (namespace != null) {
      try {
        final cached = await ref
            .read(localChatSearchStoreProvider)
            .readTimeline(
              namespace: namespace,
              conversationId: conversationId,
              beforeSeq: beforeSeq,
              limit: _pageSize,
            );
        if (!ref.mounted) return 0;
        if (cached.value.isNotEmpty) {
          final merged = _mergeMessages(state.messages, cached.value);
          state = state.copyWith(
            messages: _sorted(merged),
            nextBeforeSeq: _oldestConfirmedSeq(merged),
          );
        }
      } catch (error, stackTrace) {
        _recordLocalTimelineFailure(
          operation: 'read_older',
          error: error,
          stackTrace: stackTrace,
        );
      }
    }
    try {
      final loaded = await _repo.listMessages(
        conversationId: conversationId,
        before: beforeSeq.toString(),
        limit: _pageSize,
      );
      final hydrated = await _hydrateSenderSnapshots(
        loaded.map(_normalizeSenderAvatar).toList(growable: false),
      );
      if (!ref.mounted) return 0;
      final merged = _mergeMessages(state.messages, hydrated);
      state = state.copyWith(
        messages: _sorted(merged),
        isLoadingOlder: false,
        hasMore: loaded.length >= _pageSize,
        nextBeforeSeq: _oldestConfirmedSeq(merged),
      );
      unawaited(_persistMessages(hydrated, namespace: namespace));
      return merged.length - previousCount;
    } catch (error) {
      if (!ref.mounted) return 0;
      state = state.copyWith(
        isLoadingOlder: false,
        error: runtimeErrorDisplayMessage(error),
      );
      return state.messages.length - previousCount;
    }
  }

  /// 进入详情后用当前已加载的最后一条消息触发已读回执。
  Future<bool> markConversationRead() async {
    if (!ref.mounted) {
      return false;
    }
    final latest = state.messages.reversed.firstWhere(
      (message) => message.id.isNotEmpty,
      orElse: () => ChatMessageViewData(
        id: '',
        conversationId: '',
        seq: 0,
        clientMsgId: '',
        senderId: '',
        type: 'text',
        status: 'sent',
      ),
    );
    if (latest.id.isEmpty) {
      return false;
    }
    try {
      await _repo.markAsRead(
        conversationId: conversationId,
        messageId: latest.id,
      );
      if (!ref.mounted) {
        return false;
      }
      return true;
    } catch (e) {
      if (!ref.mounted) {
        return false;
      }
      state = state.copyWith(error: runtimeErrorDisplayMessage(e));
      return false;
    }
  }

  /// 乐观插入 → 远程发送 → 更新/标记失败。
  Future<bool> sendMessage(
    String type,
    String content, {
    ChatMessageMediaViewData? media,
    String? senderName,
    String? senderAvatar,
    List<String>? mentions,
  }) async {
    final activeContext = await _resolveActivePersonaContext();
    final clientMsgId = _uuid.v4();
    final resolvedSenderPersonaId = activeContext.personaId.isNotEmpty
        ? activeContext.personaId
        : activeContext.ownerUserId;
    final optimistic = ChatMessageViewData(
      id: clientMsgId,
      conversationId: conversationId,
      seq: _unconfirmedSeq,
      clientMsgId: clientMsgId,
      senderId: resolvedSenderPersonaId,
      senderName: senderName ?? activeContext.displayName,
      senderAvatar: _resolveAvatar(senderAvatar ?? activeContext.avatarUrl),
      type: type,
      content: content,
      mediaAssetId: media?.assetId,
      mediaDeliveryUrl: media?.deliveryUrl,
      mediaType: media?.mediaType,
      mediaContentType: media?.mimeType,
      mediaFileSizeBytes: media?.fileSizeBytes,
      status: 'sending',
    );
    final command = ChatSendMessageCommand(
      conversationId: conversationId,
      type: type,
      content: content,
      clientMsgId: clientMsgId,
      mediaAssetId: media?.assetId,
      mentions: mentions ?? const <String>[],
      senderDisplayNameSnapshot: senderName ?? activeContext.displayName,
      senderAvatarUrlSnapshot: senderAvatar ?? activeContext.avatarUrl,
      personaContextVersion: activeContext.contextVersion > 0
          ? activeContext.contextVersion
          : null,
    );
    state = state.copyWith(messages: _sorted([...state.messages, optimistic]));
    final sendStartedAt = DateTime.now();
    try {
      final resp = await _writer.sendMessage(command);
      final confirmed = optimistic.copyWith(
        id: resp.messageId,
        seq: resp.seq,
        status: 'sent',
        timestamp: resp.timestamp,
      );
      final updated = state.messages.map((m) {
        return m.clientMsgId == clientMsgId ? confirmed : m;
      }).toList();
      state = state.copyWith(messages: _sorted(updated));
      _recordSendOperationResult(result: 'success', startedAt: sendStartedAt);
      return true;
    } catch (e) {
      // 发送失败：命令进持久化 outbox（断网/杀进程后按原 clientMsgId 自动重发），
      // 气泡标记 failed 供手动立即重试。
      final failed = state.messages.map((m) {
        return m.clientMsgId == clientMsgId ? m.copyWith(status: 'failed') : m;
      }).toList();
      state = state.copyWith(messages: _sorted(failed));
      _recordSendOperationResult(
        result: 'failure',
        startedAt: sendStartedAt,
        failReasonCode: e is CloudException ? e.code : e.runtimeType.toString(),
      );
      await ref.read(chatSendOutboxProvider.notifier).enqueueCommand(command);
      return false;
    }
  }

  /// 消息发送 operation_result 遥测：观测失败不得影响发送语义。
  void _recordSendOperationResult({
    required String result,
    required DateTime startedAt,
    String? failReasonCode,
  }) {
    unawaited(() async {
      try {
        await ref
            .read(appTelemetryReporterProvider)
            .record(
              AppTelemetryPayload.operationResult(
                operationId: ChatApiMetadata.sendMessageOperation,
                result: result,
                durationMs: DateTime.now().difference(startedAt).inMilliseconds,
                failReasonCode: failReasonCode,
              ),
            );
      } catch (error, stackTrace) {
        // 产品遥测通道不可用不影响发送语义，但必须进入独立 runtime 错误面。
        unawaited(
          AppExceptionTelemetryService.instance.recordHandledException(
            source: 'chat.send_message.operation_result',
            error: error,
            stackTrace: stackTrace,
            operationId: ChatApiMetadata.sendMessageOperation,
          ),
        );
      }
    }());
  }

  /// 重试发送失败的消息：触发持久化 outbox 按原 clientMsgId 顺序重放，
  /// 服务端唯一约束保证不产生第二条消息。
  Future<void> retrySendMessage(String clientMsgId) async {
    final hasFailed = state.messages.any(
      (m) => m.clientMsgId == clientMsgId && m.status == 'failed',
    );
    if (!hasFailed) {
      throw StateError('Message not found or not failed');
    }
    await _resolveActivePersonaContext();
    final retrying = state.messages.map((m) {
      return m.clientMsgId == clientMsgId ? m.copyWith(status: 'sending') : m;
    }).toList();
    state = state.copyWith(messages: _sorted(retrying));
    try {
      await ref.read(chatSendOutboxProvider.notifier).drain();
      // drain 成功后从服务端确认视角刷新该会话消息（重放结果含 seq）。
      await loadMessages();
    } catch (error, stackTrace) {
      // 重试失败回落 failed 气泡供再次手动重试，并结构化上报。
      final failed = state.messages.map((m) {
        return m.clientMsgId == clientMsgId ? m.copyWith(status: 'failed') : m;
      }).toList();
      state = state.copyWith(messages: _sorted(failed));
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'chat.message.retry_send',
          error: error,
          stackTrace: stackTrace,
          operationId: ChatApiMetadata.sendMessageOperation,
        ),
      );
    }
  }

  /// 撤回消息。
  Future<void> recallMessage(String messageId) async {
    try {
      await _repo.recallMessage(
        conversationId: conversationId,
        messageId: messageId,
      );
      final updated = state.messages.map((m) {
        return m.id == messageId
            ? m.copyWith(status: 'recalled', recalledAt: DateTime.now())
            : m;
      }).toList();
      state = state.copyWith(messages: _sorted(updated));
    } catch (e) {
      state = state.copyWith(error: runtimeErrorDisplayMessage(e));
    }
  }

  /// 手动触发 sync 补全缺失消息。
  Future<void> syncFromSeq(int lastSeq) async {
    try {
      final syncResp = await _repo.syncMessages(
        conversationId: conversationId,
        lastSeq: lastSeq,
      );
      if (syncResp.messages.isNotEmpty) {
        final hydrated = await _hydrateSenderSnapshots(
          syncResp.messages.map(_normalizeSenderAvatar).toList(growable: false),
        );
        final merged = _mergeMessages(state.messages, hydrated);
        state = state.copyWith(messages: _sorted(merged));
        unawaited(_persistMessages(hydrated));
      }
    } catch (e) {
      state = state.copyWith(error: runtimeErrorDisplayMessage(e));
    }
  }

  /// 外部实时事件推送消息到列表（WebSocket/Long-poll 收到的新消息）。
  void addMessage(ChatMessageViewData msg) {
    final existing = state.messages.any(
      (m) =>
          m.id == msg.id ||
          (msg.clientMsgId.isNotEmpty && m.clientMsgId == msg.clientMsgId),
    );
    if (existing) return;
    state = state.copyWith(
      messages: _sorted([...state.messages, _normalizeSenderAvatar(msg)]),
    );
    unawaited(_persistMessages(<ChatMessageViewData>[msg]));
  }

  /// 实时事件：标记某消息已撤回。
  void markRecalled(String messageId) {
    final updated = state.messages.map((m) {
      return m.id == messageId
          ? m.copyWith(status: 'recalled', recalledAt: DateTime.now())
          : m;
    }).toList();
    state = state.copyWith(messages: _sorted(updated));
    unawaited(_removePersistedMessage(messageId));
  }

  Future<List<ChatMessageViewData>> _hydrateSenderSnapshots(
    List<ChatMessageViewData> messages,
  ) async {
    final needsHydration = messages.any(
      (message) =>
          (message.senderName == null || message.senderName!.trim().isEmpty) ||
          (message.senderAvatar == null ||
              message.senderAvatar!.trim().isEmpty),
    );
    if (!needsHydration) {
      return messages;
    }
    try {
      final members = await _memberRepo.listMembers(
        conversationId: conversationId,
        limit: 200,
        sort: 'joined_asc',
      );
      final memberByUserId = {
        for (final member in members)
          if (member.userId.isNotEmpty) member.userId: member,
      };
      return messages
          .map((message) {
            final member = memberByUserId[message.senderId];
            if (member == null) {
              return message;
            }
            final senderName = message.senderName?.trim() ?? '';
            final senderAvatar = message.senderAvatar?.trim() ?? '';
            if (senderName.isNotEmpty && senderAvatar.isNotEmpty) {
              return message;
            }
            return message.copyWith(
              senderName: senderName.isEmpty ? member.displayName : senderName,
              senderAvatar: senderAvatar.isEmpty
                  ? _resolveAvatar(member.avatarUrl)
                  : _resolveAvatar(senderAvatar),
            );
          })
          .toList(growable: false);
    } catch (error, stackTrace) {
      // best-effort：快照水合失败降级为原始消息，上报保留观测面。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'chat.message.hydrate_sender_snapshots',
          error: error,
          stackTrace: stackTrace,
        ),
      );
      return messages;
    }
  }

  ChatMessageViewData _normalizeSenderAvatar(ChatMessageViewData message) {
    final avatar = _resolveAvatar(message.senderAvatar);
    if ((message.senderAvatar ?? '') == avatar) {
      return message;
    }
    return message.copyWith(senderAvatar: avatar);
  }

  String _resolveAvatar(String? raw) {
    return resolveAvatarImageUrl(
      raw,
      endpointConfig: ref.read(mediaEndpointConfigProvider),
    );
  }

  // ── 排序：seq > 0 升序，seq == 0（未确认）排最后按 timestamp ──────────

  List<ChatMessageViewData> _sorted(List<ChatMessageViewData> list) {
    final confirmed = <ChatMessageViewData>[];
    final pending = <ChatMessageViewData>[];
    for (final m in list) {
      if (m.seq > _unconfirmedSeq) {
        confirmed.add(m);
      } else {
        pending.add(m);
      }
    }
    confirmed.sort((a, b) => a.seq.compareTo(b.seq));
    pending.sort((a, b) {
      final at = a.timestamp;
      final bt = b.timestamp;
      if (at == null && bt == null) return 0;
      if (at == null) return 1;
      if (bt == null) return -1;
      return at.compareTo(bt);
    });
    return [...confirmed, ...pending];
  }

  // ── seq gap 检测 + 自动补全 ──────────────────────────────────────

  Future<void> _detectAndFillGap(int maxSeq) async {
    final confirmedSeqs =
        state.messages
            .where((m) => m.seq > _unconfirmedSeq)
            .map((m) => m.seq)
            .toList()
          ..sort();
    if (confirmedSeqs.isEmpty) {
      await syncFromSeq(0);
      return;
    }
    final localMaxSeq = confirmedSeqs.last;
    if (localMaxSeq < maxSeq) {
      await syncFromSeq(localMaxSeq);
    }
  }

  int _oldestConfirmedSeq(List<ChatMessageViewData> messages) {
    var oldest = 0;
    for (final message in messages) {
      if (message.seq <= _unconfirmedSeq) continue;
      if (oldest == 0 || message.seq < oldest) oldest = message.seq;
    }
    return oldest;
  }

  Future<LocalSearchNamespace?> _resolveLocalNamespace() async {
    try {
      final context = await ref.read(activePersonaContextProvider.future);
      return LocalSearchNamespace.fromActivePersonaContext(context);
    } catch (error, stackTrace) {
      _recordLocalTimelineFailure(
        operation: 'resolve_namespace',
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  Future<void> _persistMessages(
    List<ChatMessageViewData> messages, {
    LocalSearchNamespace? namespace,
  }) async {
    if (messages.isEmpty) return;
    try {
      final resolvedNamespace = namespace ?? await _resolveLocalNamespace();
      if (resolvedNamespace == null) return;
      await ref
          .read(localChatSearchStoreProvider)
          .upsertMessages(
            namespace: resolvedNamespace,
            messages: messages
                .map(LocalChatSearchMessageRecord.fromMessageViewData)
                .toList(growable: false),
          );
    } catch (error, stackTrace) {
      _recordLocalTimelineFailure(
        operation: 'persist',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  Future<void> _removePersistedMessage(String messageId) async {
    try {
      final namespace = await _resolveLocalNamespace();
      if (namespace == null) return;
      await ref
          .read(localChatSearchStoreProvider)
          .removeMessage(namespace: namespace, messageId: messageId);
    } catch (error, stackTrace) {
      _recordLocalTimelineFailure(
        operation: 'remove',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  void _recordLocalTimelineFailure({
    required String operation,
    required Object error,
    required StackTrace stackTrace,
  }) {
    unawaited(
      AppExceptionTelemetryService.instance.recordHandledException(
        source: 'chat.message.local_timeline.$operation',
        error: error,
        stackTrace: stackTrace,
        operationId: ChatApiMetadata.listMessagesOperation,
      ),
    );
  }

  // ── 合并去重（按 id / clientMsgId）──────────────────────────────

  List<ChatMessageViewData> _mergeMessages(
    List<ChatMessageViewData> existing,
    List<ChatMessageViewData> incoming,
  ) {
    final byId = <String, ChatMessageViewData>{};
    for (final m in existing) {
      byId[m.id] = m;
    }
    for (final m in incoming) {
      final existingMsg = byId[m.id] ?? byId[m.clientMsgId];
      if (existingMsg != null && existingMsg.status == 'sending') {
        byId[m.id] = m;
        byId.remove(existingMsg.clientMsgId);
      } else {
        byId[m.id] = m;
      }
    }
    return byId.values.toList();
  }
}

/// 按 conversationId 创建独立的消息状态管理器。
final chatMessageProvider =
    NotifierProvider.family<ChatMessageNotifier, ChatMessageState, String>(
      ChatMessageNotifier.new,
    );
