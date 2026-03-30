import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

const _uuid = Uuid();

/// 消息列表状态：含加载态、错误信息和已排序消息列表。
class ChatMessageState {
  final List<MessageDto> messages;
  final bool isLoading;
  final String? error;

  const ChatMessageState({
    this.messages = const [],
    this.isLoading = false,
    this.error,
  });

  ChatMessageState copyWith({
    List<MessageDto>? messages,
    bool? isLoading,
    String? error,
  }) {
    return ChatMessageState(
      messages: messages ?? this.messages,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

/// 管理单个会话的消息列表、发送、撤回、seq gap 补全。
class ChatMessageNotifier extends StateNotifier<ChatMessageState> {
  ChatMessageNotifier(this._ref, this._repo, this.conversationId)
    : super(const ChatMessageState());

  final Ref _ref;
  final ChatRepository _repo;
  final String conversationId;

  // seq=0 表示消息尚未被服务端确认（发送中/发送失败）
  static const int _unconfirmedSeq = 0;

  Future<ActivePersonaContextViewData> _resolveActivePersonaContext() async {
    final activeContext = await _ref.read(activePersonaContextProvider.future);
    final mode = _ref.read(appDataSourceModeProvider);
    if (mode == AppDataSourceMode.remote && activeContext.isFallback) {
      throw StateError('active persona context unavailable');
    }
    return activeContext;
  }

  /// 加载消息并按 seq 排序，之后检测 gap。
  Future<void> loadMessages({int? maxSeq}) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final loaded = await _repo.listMessages(conversationId: conversationId);
      final merged = _mergeMessages(state.messages, loaded);
      state = state.copyWith(messages: _sorted(merged), isLoading: false);
      if (maxSeq != null && maxSeq > 0) {
        await _detectAndFillGap(maxSeq);
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  /// 进入详情后用当前已加载的最后一条消息触发已读回执。
  Future<bool> markConversationRead() async {
    final latest = state.messages.reversed.firstWhere(
      (message) => message.id.isNotEmpty,
      orElse: () => const MessageDto(
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
      return true;
    } catch (e) {
      state = state.copyWith(error: e.toString());
      return false;
    }
  }

  /// 乐观插入 → 远程发送 → 更新/标记失败。
  Future<void> sendMessage(
    String type,
    String content, {
    String? mediaUrl,
    Map<String, dynamic>? media,
    String? senderName,
    String? senderAvatar,
  }) async {
    final activeContext = await _resolveActivePersonaContext();
    final clientMsgId = _uuid.v4();
    final resolvedSenderId =
        activeContext.profileSubjectId.isNotEmpty
        ? activeContext.profileSubjectId
        : _ref.read(currentUserIdProvider);
    final resolvedSenderPersonaId = activeContext.subAccountId;
    final optimistic = MessageDto(
      id: clientMsgId,
      conversationId: conversationId,
      seq: _unconfirmedSeq,
      clientMsgId: clientMsgId,
      senderId: resolvedSenderId,
      senderName: senderName ?? activeContext.displayName,
      senderAvatar: senderAvatar ?? activeContext.avatarUrl,
      senderPersonaId: resolvedSenderPersonaId.isEmpty
          ? null
          : resolvedSenderPersonaId,
      type: type,
      content: content,
      mediaUrl: mediaUrl,
      media: media,
      status: 'sending',
    );
    state = state.copyWith(messages: _sorted([...state.messages, optimistic]));
    try {
      final raw = await _repo.sendMessage(
        conversationId: conversationId,
        type: type,
        content: content,
        mediaUrl: mediaUrl,
        media: media,
        senderPersonaId: resolvedSenderPersonaId.isEmpty
            ? null
            : resolvedSenderPersonaId,
        senderProfileSubjectId: resolvedSenderId,
        personaContextVersion: activeContext.personaContextVersion,
        clientMsgId: clientMsgId,
      );
      final resp = SendMessageResponse.fromMap(raw);
      final confirmed = optimistic.copyWith(
        id: resp.id,
        seq: resp.seq,
        status: 'sent',
        timestamp: resp.timestamp,
      );
      final updated = state.messages.map((m) {
        return m.clientMsgId == clientMsgId ? confirmed : m;
      }).toList();
      state = state.copyWith(messages: _sorted(updated));
    } catch (e) {
      final failed = state.messages.map((m) {
        return m.clientMsgId == clientMsgId ? m.copyWith(status: 'failed') : m;
      }).toList();
      state = state.copyWith(messages: _sorted(failed));
    }
  }

  /// 重试发送失败的消息。
  Future<void> retrySendMessage(String clientMsgId) async {
    final msg = state.messages.firstWhere(
      (m) => m.clientMsgId == clientMsgId && m.status == 'failed',
      orElse: () => throw StateError('Message not found or not failed'),
    );
    final activeContext = await _resolveActivePersonaContext();
    final retrying = state.messages.map((m) {
      return m.clientMsgId == clientMsgId ? m.copyWith(status: 'sending') : m;
    }).toList();
    state = state.copyWith(messages: _sorted(retrying));
    try {
      final raw = await _repo.sendMessage(
        conversationId: conversationId,
        type: msg.type,
        content: msg.content ?? '',
        mediaUrl: msg.mediaUrl,
        media: msg.media,
        senderPersonaId:
            msg.senderPersonaId ??
            (activeContext.subAccountId.isEmpty
                ? null
                : activeContext.subAccountId),
        senderProfileSubjectId: msg.senderId,
        personaContextVersion: activeContext.personaContextVersion,
        clientMsgId: clientMsgId,
      );
      final resp = SendMessageResponse.fromMap(raw);
      final confirmed = msg.copyWith(
        id: resp.id,
        seq: resp.seq,
        status: 'sent',
        timestamp: resp.timestamp,
      );
      final updated = state.messages.map((m) {
        return m.clientMsgId == clientMsgId ? confirmed : m;
      }).toList();
      state = state.copyWith(messages: _sorted(updated));
    } catch (_) {
      final failed = state.messages.map((m) {
        return m.clientMsgId == clientMsgId ? m.copyWith(status: 'failed') : m;
      }).toList();
      state = state.copyWith(messages: _sorted(failed));
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
      state = state.copyWith(error: e.toString());
    }
  }

  /// 手动触发 sync 补全缺失消息。
  Future<void> syncFromSeq(int lastSeq) async {
    try {
      final raw = await _repo.syncMessages(
        conversationId: conversationId,
        lastSeq: lastSeq,
      );
      final syncResp = SyncResponse.fromMap(raw);
      if (syncResp.messages.isNotEmpty) {
        final merged = _mergeMessages(state.messages, syncResp.messages);
        state = state.copyWith(messages: _sorted(merged));
      }
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  /// 外部实时事件推送消息到列表（WebSocket/Long-poll 收到的新消息）。
  void addMessage(MessageDto msg) {
    final existing = state.messages.any(
      (m) =>
          m.id == msg.id ||
          (msg.clientMsgId.isNotEmpty && m.clientMsgId == msg.clientMsgId),
    );
    if (existing) return;
    state = state.copyWith(messages: _sorted([...state.messages, msg]));
  }

  /// 实时事件：标记某消息已撤回。
  void markRecalled(String messageId) {
    final updated = state.messages.map((m) {
      return m.id == messageId
          ? m.copyWith(status: 'recalled', recalledAt: DateTime.now())
          : m;
    }).toList();
    state = state.copyWith(messages: _sorted(updated));
  }

  // ── 排序：seq > 0 升序，seq == 0（未确认）排最后按 timestamp ──────────

  List<MessageDto> _sorted(List<MessageDto> list) {
    final confirmed = <MessageDto>[];
    final pending = <MessageDto>[];
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

  // ── 合并去重（按 id / clientMsgId）──────────────────────────────

  List<MessageDto> _mergeMessages(
    List<MessageDto> existing,
    List<MessageDto> incoming,
  ) {
    final byId = <String, MessageDto>{};
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
    StateNotifierProvider.family<ChatMessageNotifier, ChatMessageState, String>(
      (ref, conversationId) {
        final repo = ref.watch(chatRepositoryProvider);
        return ChatMessageNotifier(ref, repo, conversationId);
      },
    );
