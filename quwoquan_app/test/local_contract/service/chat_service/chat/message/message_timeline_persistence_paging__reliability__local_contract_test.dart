/// 消息时间线本地落盘与历史分页的可靠性契约。
///
/// 覆盖：冷启动/离线打开会话由本地副本水合（离线只读来源可区分）、
/// 本地为空且远端失败呈现可重试失败态、远端结果写入本地副本、
/// keyset 游标向上翻页有序无重复且终止判定明确、翻页失败保留已加载内容。
///
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-timeline-local-persistence/spec.md#gwt-001
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-timeline-local-persistence/spec.md#gwt-002
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-001.t1
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-001.t2
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-002.t2
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-002.t2
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-001
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-002
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-002.t2
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_sync_service.dart';
import 'package:quwoquan_app/runtime/di/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/longpoll_transport.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/remote_realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/websocket_transport.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/realtime_contracts.dart'
    as realtime;
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';

const _conversationId = 'fixture_conv_persistence';

ChatMessageViewData _message(int seq) => ChatMessageViewData(
  id: 'msg_$seq',
  conversationId: _conversationId,
  seq: seq,
  clientMsgId: 'client_$seq',
  senderId: 'fixture_user_peer',
  senderName: '对方',
  senderAvatar: 'https://avatar.example.test/media/avatar/peer.png',
  type: 'text',
  content: '第 $seq 条消息',
  status: 'sent',
);

final class _ChatPersonaQuery extends Fake implements PersonaQuery {
  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData(
      personaId: 'fixture_user_current',
      ownerUserId: 'fixture_user_current',
      subjectType: 'persona',
      displayName: '可靠性测试用户',
      avatarUrl: '',
      contextVersion: 1,
    );
  }
}

/// 可配置的本地时间线副本 double：按 keyset（beforeSeq）读取并记录写入。
final class _SeededTimelineCache implements ChatMessageTimelineCache {
  _SeededTimelineCache({List<ChatMessageViewData>? rows})
    : rows = List<ChatMessageViewData>.from(rows ?? const []);

  final List<ChatMessageViewData> rows;
  final List<List<ChatMessageViewData>> writes = <List<ChatMessageViewData>>[];

  @override
  Future<List<ChatMessageViewData>> readMessages({
    required ChatMessageTimelineScope scope,
    required String conversationId,
    int beforeSeq = 0,
    int limit = 50,
  }) async {
    final filtered =
        rows
            .where(
              (row) =>
                  row.conversationId == conversationId &&
                  (beforeSeq <= 0 || row.seq < beforeSeq),
            )
            .toList()
          ..sort((a, b) => b.seq.compareTo(a.seq));
    return filtered.take(limit).toList(growable: false);
  }

  @override
  Future<void> writeMessages({
    required ChatMessageTimelineScope scope,
    required List<ChatMessageViewData> messages,
  }) async {
    writes.add(List<ChatMessageViewData>.from(messages));
  }

  @override
  Future<void> removeCachedMessage({
    required ChatMessageTimelineScope scope,
    required String messageId,
  }) async {}
}

/// keyset 分页的消息读 double：`before` 之前最近 limit 条；可切换失败态。
final class _PagedMessageRepository extends Fake
    implements ChatMessageRepository {
  _PagedMessageRepository(this.totalSeq);

  final int totalSeq;
  bool failNextCalls = false;
  int listCallCount = 0;
  Completer<void>? listGate;
  final Completer<void> firstListCallObserved = Completer<void>();
  Completer<void>? syncGate;
  final Completer<void> firstSyncCallObserved = Completer<void>();
  List<ChatMessageViewData> syncRows = const <ChatMessageViewData>[];

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    listCallCount += 1;
    if (!firstListCallObserved.isCompleted) {
      firstListCallObserved.complete();
    }
    final gate = listGate;
    if (gate != null) {
      await gate.future;
    }
    if (failNextCalls) {
      throw StateError('remote unavailable');
    }
    final beforeSeq = int.tryParse(before ?? '') ?? (totalSeq + 1);
    final page = <ChatMessageViewData>[];
    for (var seq = beforeSeq - 1; seq >= 1 && page.length < limit; seq--) {
      page.add(_message(seq));
    }
    return page;
  }

  @override
  Future<ChatMessageSyncViewData> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = 500,
  }) async {
    if (!firstSyncCallObserved.isCompleted) {
      firstSyncCallObserved.complete();
    }
    final gate = syncGate;
    if (gate != null) {
      await gate.future;
    }
    if (failNextCalls) {
      throw StateError('remote unavailable');
    }
    return ChatMessageSyncViewData(messages: syncRows, hasMore: false);
  }
}

final class _BlockingMemberRepository extends Fake
    implements ChatMemberRepository {
  final Completer<void> listEntered = Completer<void>();
  final Completer<void> releaseList = Completer<void>();

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    required int limit,
    String? role,
    MemberListSort? sort,
  }) async {
    if (!listEntered.isCompleted) listEntered.complete();
    await releaseList.future;
    return const <ConversationMemberListRow>[
      ConversationMemberListRow(
        userId: 'fixture_user_peer',
        userHandle: 'peer',
        displayName: '对方',
        avatarUrl: '/media/avatar/peer.png',
        role: 'member',
        memberType: 'human',
        isCurrentUser: false,
      ),
    ];
  }
}

final class _RealtimeTokenProvider implements CloudAuthTokenProvider {
  const _RealtimeTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'realtime-token';
}

final class _NoopConversationSync extends Fake
    implements ConversationSyncService {
  @override
  Future<bool> sync({bool force = false}) async => false;

  @override
  Future<bool> syncAvatarPatches({
    int? hintedLatestSyncSeq,
    bool force = false,
  }) async => false;
}

final class _NoopLocalChatSearchSync extends Fake
    implements LocalChatSearchSyncService {
  @override
  Future<bool> sync({bool force = false}) async => false;
}

final class _TrackingCursorStore implements LongPollCursorStore {
  _TrackingCursorStore({required this.partition, required this.cursor});

  final String partition;
  String cursor;
  final Completer<void> writeObserved = Completer<void>();

  @override
  Future<String?> read(String candidate) async =>
      candidate == partition ? cursor : null;

  @override
  Future<void> write(String candidate, String cursor) async {
    if (candidate != partition) {
      throw StateError('unexpected cursor partition');
    }
    this.cursor = cursor;
    if (!writeObserved.isCompleted) writeObserved.complete();
  }
}

final class _ResumeOperations implements RealtimeConnectionOperationGateway {
  const _ResumeOperations();

  @override
  Future<realtime.ConnectionTicket> issueConnectionTicket() async =>
      realtime.ConnectionTicket(
        ticket: 'one-time-ticket',
        expiresAt: DateTime.utc(2026, 8, 28, 0, 0, 30),
      );

  @override
  Future<realtime.LongPollResponse> longPoll({
    int? timeout,
    String? cursor,
  }) async {
    return const realtime.LongPollResponse(
      events: <realtime.RealtimeEventEnvelope>[],
      nextCursor: '100-0',
      transportResumed: true,
    );
  }
}

final class _DisconnectingWebSocketTransport extends WebSocketTransport {
  _DisconnectingWebSocketTransport({
    required super.config,
    required super.authTokenProvider,
    required super.onEvent,
    required super.onDisconnect,
  });

  final ValueNotifier<bool> _connected = ValueNotifier<bool>(false);

  @override
  ValueListenable<bool> get isConnected => _connected;

  @override
  Future<void> connect({List<String> topics = const <String>[]}) async {
    scheduleMicrotask(onDisconnect);
  }

  @override
  void dispose() {
    _connected.dispose();
  }
}

List<Override> _boundaryOverrides({
  required ChatMessageRepository message,
  required ChatMessageTimelineCache timelineCache,
  ChatMemberRepository? member,
}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    ...chatTestRepositoryOverrides(message: message, member: member),
    chatMessageTimelineCacheProvider.overrideWithValue(timelineCache),
    personaQueryProvider(AppUiSurfaces.appShell)
        .overrideWithValue(_ChatPersonaQuery()),
    mediaEndpointConfigProvider.overrideWithValue(
      MediaEndpointConfig(
        avatarBaseUrl: 'https://avatar.example.test/media/avatar',
        imageBaseUrl: 'https://image.example.test/media/image',
        videoBaseUrl: 'https://video.example.test/media/video',
        attachmentBaseUrl: 'https://image.example.test/media/image',
      ),
    ),
  ];
}

Future<({String outcome, String cursor})> _runProductionReconnect(
  ProviderContainer container,
) async {
  final credential = await RealtimeConnectionCredential.resolveHttp(
    const _RealtimeTokenProvider(),
  );
  final cursorStore = _TrackingCursorStore(
    partition: credential!.cursorPartition,
    cursor: '99-0',
  );
  final longPollFailed = Completer<void>();
  final delegate = RemoteRealtimeConnectionDelegate(
    read: container.read,
    currentUserIdResolver: () => 'fixture_user_current',
    authTokenProvider: const _RealtimeTokenProvider(),
    config: const RealtimeConfig(
      wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
      gatewayBaseUrl: 'http://127.0.0.1:17000',
      longPollHoldSec: 1,
      maxReconnectAttempts: 0,
    ),
    telemetryRecorder:
        ({
          required transport,
          required result,
          required durationMs,
          failReasonCode,
        }) async {
          if (transport == 'long_poll' && result == 'failed') {
            if (!longPollFailed.isCompleted) longPollFailed.complete();
          }
        },
    longPollFactory:
        ({
          required config,
          required authTokenProvider,
          required activeConversationIdResolver,
          required onEvents,
        }) => LongPollTransport(
          config: config,
          authTokenProvider: authTokenProvider,
          operations: const _ResumeOperations(),
          activeConversationIdResolver: activeConversationIdResolver,
          onEvents: onEvents,
          cursorStore: cursorStore,
        ),
    webSocketFactory:
        ({
          required config,
          required authTokenProvider,
          required onEvent,
          required onDisconnect,
        }) => _DisconnectingWebSocketTransport(
          config: config,
          authTokenProvider: authTokenProvider,
          onEvent: onEvent,
          onDisconnect: onDisconnect,
        ),
  );

  try {
    delegate.onEnterConversation(_conversationId);
    final outcome = await Future.any<String>(<Future<String>>[
      cursorStore.writeObserved.future.then((_) => 'cursor_committed'),
      longPollFailed.future.then((_) => 'failure_propagated'),
    ]).timeout(const Duration(seconds: 2));
    return (outcome: outcome, cursor: cursorStore.cursor);
  } finally {
    delegate.dispose();
  }
}

void main() {
  group('消息时间线本地落盘（timeline-local-persistence）', () {
    test('GWT-001 曾同步过的会话在远端失败时由本地副本水合为离线只读', () async {
      final cache = _SeededTimelineCache(
        rows: [_message(3), _message(1), _message(2)],
      );
      final repo = _PagedMessageRepository(3)..failNextCalls = true;
      final container = ProviderContainer(
        overrides: _boundaryOverrides(message: repo, timelineCache: cache),
      );
      addTearDown(container.dispose);

      await container
          .read(chatMessageProvider(_conversationId).notifier)
          .loadMessages();

      final state = container.read(chatMessageProvider(_conversationId));
      expect(state.messages.map((m) => m.seq).toList(), [
        1,
        2,
        3,
      ], reason: '时间线必须由本地副本水合并按 seq 有序展示');
      expect(
        state.source,
        ChatTimelineContentSource.offlineReadOnly,
        reason: '本地命中且远端失败必须表达为离线只读，而非刷新失败',
      );
      expect(state.error, isNull, reason: '离线只读不得与远端失败混为同一错误态');
      expect(state.isLoading, isFalse);
      expect(state.isRefreshing, isFalse);
    });

    // spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/spec.md#sit-002.t2
    test('SIT-002 断连补齐失败呈现可重试失败态且不静默截断已有序列', () async {
      final cache = _SeededTimelineCache();
      final repo = _PagedMessageRepository(3);
      final container = ProviderContainer(
        overrides: _boundaryOverrides(message: repo, timelineCache: cache),
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        chatMessageProvider(_conversationId).notifier,
      );
      await notifier.loadMessages();
      expect(
        container.read(chatMessageProvider(_conversationId)).messages,
        hasLength(3),
      );

      // 重连后补洞请求失败：必须呈现失败态，且已有序列原样保留。
      repo.failNextCalls = true;
      await expectLater(notifier.syncFromSeq(3), throwsA(isA<StateError>()));

      final state = container.read(chatMessageProvider(_conversationId));
      expect(state.error, isNotNull, reason: '补齐失败必须呈现可重试失败态，不得静默吞掉');
      expect(state.messages.map((m) => m.seq).toList(), [
        1,
        2,
        3,
      ], reason: '补齐失败不得截断或回退已有消息序列');
    });

    test('syncFromSeq 失败返回期间 container dispose 保留原始仓储错误', () async {
      final repo = _PagedMessageRepository(3);
      final container = ProviderContainer(
        overrides: _boundaryOverrides(
          message: repo,
          timelineCache: _SeededTimelineCache(),
        ),
      );
      final notifier = container.read(
        chatMessageProvider(_conversationId).notifier,
      );
      await notifier.loadMessages();
      final gate = Completer<void>();
      repo
        ..syncGate = gate
        ..failNextCalls = true;
      addTearDown(() {
        if (!gate.isCompleted) gate.complete();
      });

      final recovery = notifier.syncFromSeq(3);
      await repo.firstSyncCallObserved.future.timeout(
        const Duration(seconds: 2),
      );
      container.dispose();
      gate.complete();

      await expectLater(
        recovery,
        throwsA(
          isA<StateError>().having(
            (error) => error.message,
            'message',
            'remote unavailable',
          ),
        ),
      );
    });

    test('syncFromSeq 成功返回期间 container dispose 不再水合或写 state', () async {
      final repo = _PagedMessageRepository(3);
      final container = ProviderContainer(
        overrides: _boundaryOverrides(
          message: repo,
          timelineCache: _SeededTimelineCache(),
        ),
      );
      final notifier = container.read(
        chatMessageProvider(_conversationId).notifier,
      );
      await notifier.loadMessages();
      final gate = Completer<void>();
      repo
        ..syncGate = gate
        ..syncRows = <ChatMessageViewData>[_message(4)];
      addTearDown(() {
        if (!gate.isCompleted) gate.complete();
      });

      final recovery = notifier.syncFromSeq(3);
      await repo.firstSyncCallObserved.future.timeout(
        const Duration(seconds: 2),
      );
      container.dispose();
      gate.complete();

      await expectLater(recovery, completes);
    });

    test('syncFromSeq sender hydration await 期间 dispose 不读取 ref', () async {
      final repo = _PagedMessageRepository(3);
      final memberRepo = _BlockingMemberRepository();
      final container = ProviderContainer(
        overrides: _boundaryOverrides(
          message: repo,
          timelineCache: _SeededTimelineCache(),
          member: memberRepo,
        ),
      );
      final notifier = container.read(
        chatMessageProvider(_conversationId).notifier,
      );
      repo.syncRows = <ChatMessageViewData>[
        _message(4).copyWith(senderName: '', senderAvatar: ''),
      ];
      addTearDown(() {
        if (!memberRepo.releaseList.isCompleted) {
          memberRepo.releaseList.complete();
        }
      });

      final recovery = notifier.syncFromSeq(3);
      await memberRepo.listEntered.future.timeout(const Duration(seconds: 2));
      container.dispose();
      memberRepo.releaseList.complete();

      await expectLater(recovery, completes);
    });

    test(
      'GWT-002 repository 补洞失败经 production handler 阻止 LongPoll 游标提交',
      () async {
        final cache = _SeededTimelineCache();
        final repo = _PagedMessageRepository(3);
        final container = ProviderContainer(
          overrides: <Override>[
            ..._boundaryOverrides(message: repo, timelineCache: cache),
            conversationSyncProvider.overrideWithValue(_NoopConversationSync()),
            localChatSearchSyncProvider.overrideWithValue(
              _NoopLocalChatSearchSync(),
            ),
          ],
        );
        addTearDown(container.dispose);
        final notifier = container.read(
          chatMessageProvider(_conversationId).notifier,
        );
        await notifier.loadMessages();
        repo.failNextCalls = true;

        final credential = await RealtimeConnectionCredential.resolveHttp(
          const _RealtimeTokenProvider(),
        );
        final cursorStore = _TrackingCursorStore(
          partition: credential!.cursorPartition,
          cursor: '99-0',
        );
        final longPollFailed = Completer<void>();
        final delegate = RemoteRealtimeConnectionDelegate(
          read: container.read,
          currentUserIdResolver: () => 'fixture_user_current',
          authTokenProvider: const _RealtimeTokenProvider(),
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            gatewayBaseUrl: 'http://127.0.0.1:17000',
            longPollHoldSec: 1,
            maxReconnectAttempts: 0,
          ),
          telemetryRecorder:
              ({
                required transport,
                required result,
                required durationMs,
                failReasonCode,
              }) async {
                if (transport == 'long_poll' && result == 'failed') {
                  if (!longPollFailed.isCompleted) longPollFailed.complete();
                }
              },
          longPollFactory:
              ({
                required config,
                required authTokenProvider,
                required activeConversationIdResolver,
                required onEvents,
              }) => LongPollTransport(
                config: config,
                authTokenProvider: authTokenProvider,
                operations: const _ResumeOperations(),
                activeConversationIdResolver: activeConversationIdResolver,
                onEvents: onEvents,
                cursorStore: cursorStore,
              ),
          webSocketFactory:
              ({
                required config,
                required authTokenProvider,
                required onEvent,
                required onDisconnect,
              }) => _DisconnectingWebSocketTransport(
                config: config,
                authTokenProvider: authTokenProvider,
                onEvent: onEvent,
                onDisconnect: onDisconnect,
              ),
        );
        addTearDown(delegate.dispose);

        delegate.onEnterConversation(_conversationId);
        final outcome = await Future.any<String>(<Future<String>>[
          cursorStore.writeObserved.future.then((_) => 'cursor_committed'),
          longPollFailed.future.then((_) => 'failure_propagated'),
        ]).timeout(const Duration(seconds: 2));
        delegate.dispose();

        expect(outcome, 'failure_propagated');
        expect(cursorStore.cursor, '99-0');
        final state = container.read(chatMessageProvider(_conversationId));
        expect(state.error, isNotNull);
        expect(state.messages.map((message) => message.seq), <int>[1, 2, 3]);
      },
    );

    test('GWT-002 空时间线首次恢复失败经 production handler 阻止 LongPoll 游标提交', () async {
      final cache = _SeededTimelineCache();
      final repo = _PagedMessageRepository(0)..failNextCalls = true;
      final container = ProviderContainer(
        overrides: <Override>[
          ..._boundaryOverrides(message: repo, timelineCache: cache),
          conversationSyncProvider.overrideWithValue(_NoopConversationSync()),
          localChatSearchSyncProvider.overrideWithValue(
            _NoopLocalChatSearchSync(),
          ),
        ],
      );
      addTearDown(container.dispose);

      final credential = await RealtimeConnectionCredential.resolveHttp(
        const _RealtimeTokenProvider(),
      );
      final cursorStore = _TrackingCursorStore(
        partition: credential!.cursorPartition,
        cursor: '99-0',
      );
      final longPollFailed = Completer<void>();
      final delegate = RemoteRealtimeConnectionDelegate(
        read: container.read,
        currentUserIdResolver: () => 'fixture_user_current',
        authTokenProvider: const _RealtimeTokenProvider(),
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          gatewayBaseUrl: 'http://127.0.0.1:17000',
          longPollHoldSec: 1,
          maxReconnectAttempts: 0,
        ),
        telemetryRecorder:
            ({
              required transport,
              required result,
              required durationMs,
              failReasonCode,
            }) async {
              if (transport == 'long_poll' && result == 'failed') {
                if (!longPollFailed.isCompleted) longPollFailed.complete();
              }
            },
        longPollFactory:
            ({
              required config,
              required authTokenProvider,
              required activeConversationIdResolver,
              required onEvents,
            }) => LongPollTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              operations: const _ResumeOperations(),
              activeConversationIdResolver: activeConversationIdResolver,
              onEvents: onEvents,
              cursorStore: cursorStore,
            ),
        webSocketFactory:
            ({
              required config,
              required authTokenProvider,
              required onEvent,
              required onDisconnect,
            }) => _DisconnectingWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
            ),
      );
      addTearDown(delegate.dispose);

      delegate.onEnterConversation(_conversationId);
      final outcome = await Future.any<String>(<Future<String>>[
        cursorStore.writeObserved.future.then((_) => 'cursor_committed'),
        longPollFailed.future.then((_) => 'failure_propagated'),
      ]).timeout(const Duration(seconds: 2));
      delegate.dispose();

      expect(outcome, 'failure_propagated');
      expect(cursorStore.cursor, '99-0');
      final state = container.read(chatMessageProvider(_conversationId));
      expect(state.messages, isEmpty);
      expect(state.error, isNotNull);
    });

    test('GWT-002 disk cache 水合但远端恢复失败仍阻止 LongPoll 游标提交', () async {
      final cache = _SeededTimelineCache(
        rows: [_message(1), _message(2), _message(3)],
      );
      final repo = _PagedMessageRepository(3)..failNextCalls = true;
      final container = ProviderContainer(
        overrides: <Override>[
          ..._boundaryOverrides(message: repo, timelineCache: cache),
          conversationSyncProvider.overrideWithValue(_NoopConversationSync()),
          localChatSearchSyncProvider.overrideWithValue(
            _NoopLocalChatSearchSync(),
          ),
        ],
      );
      addTearDown(container.dispose);

      final result = await _runProductionReconnect(container);

      expect(result.outcome, 'failure_propagated');
      expect(result.cursor, '99-0');
      final state = container.read(chatMessageProvider(_conversationId));
      expect(state.messages.map((message) => message.seq), <int>[1, 2, 3]);
      expect(state.source, ChatTimelineContentSource.offlineReadOnly);
      expect(state.error, isNull, reason: 'UI 离线只读态不靠 error 表达远端恢复失败');
    });

    test('GWT-002 已有 loadMessages in-flight 时恢复不得伪成功提交 cursor', () async {
      final cache = _SeededTimelineCache();
      final repo = _PagedMessageRepository(0);
      final listGate = Completer<void>();
      repo.listGate = listGate;
      addTearDown(() {
        if (!listGate.isCompleted) listGate.complete();
      });
      final container = ProviderContainer(
        overrides: <Override>[
          ..._boundaryOverrides(message: repo, timelineCache: cache),
          conversationSyncProvider.overrideWithValue(_NoopConversationSync()),
          localChatSearchSyncProvider.overrideWithValue(
            _NoopLocalChatSearchSync(),
          ),
        ],
      );
      addTearDown(container.dispose);
      final initialLoad = container
          .read(chatMessageProvider(_conversationId).notifier)
          .loadMessages();
      await repo.firstListCallObserved.future.timeout(
        const Duration(seconds: 2),
      );
      expect(
        container.read(chatMessageProvider(_conversationId)).isLoading,
        isTrue,
      );

      final result = await _runProductionReconnect(container);

      expect(result.outcome, 'failure_propagated');
      expect(result.cursor, '99-0');
      listGate.complete();
      await initialLoad;
    });

    test('GWT-002 本地为空且远端失败必须呈现可重试失败态', () async {
      final cache = _SeededTimelineCache();
      final repo = _PagedMessageRepository(0)..failNextCalls = true;
      final container = ProviderContainer(
        overrides: _boundaryOverrides(message: repo, timelineCache: cache),
      );
      addTearDown(container.dispose);

      await container
          .read(chatMessageProvider(_conversationId).notifier)
          .loadMessages();

      final state = container.read(chatMessageProvider(_conversationId));
      expect(state.messages, isEmpty);
      expect(state.error, isNotNull, reason: '本地为空且远端失败必须呈现失败态，不得以空列表冒充没有消息');
      expect(state.source, ChatTimelineContentSource.none);
      expect(cache.writes, isEmpty, reason: '失败不得写入任何本地成功事实');
    });

    test('REQ-001 本地水合先于远端刷新且刷新结果写回本地副本', () async {
      final cache = _SeededTimelineCache(rows: [_message(1), _message(2)]);
      final repo = _PagedMessageRepository(4);
      final container = ProviderContainer(
        overrides: _boundaryOverrides(message: repo, timelineCache: cache),
      );
      addTearDown(container.dispose);

      await container
          .read(chatMessageProvider(_conversationId).notifier)
          .loadMessages();
      // 远端结果落盘为 fire-and-forget，推进一帧事件队列。
      await Future<void>.delayed(Duration.zero);

      final state = container.read(chatMessageProvider(_conversationId));
      expect(state.messages.map((m) => m.seq).toList(), [1, 2, 3, 4]);
      expect(
        state.messages.map((m) => m.id).toSet().length,
        state.messages.length,
        reason: '本地与远端合并不得产生重复条目',
      );
      expect(state.source, ChatTimelineContentSource.remoteSynced);
      expect(cache.writes, isNotEmpty, reason: '远端拉取结果必须写入本地副本（写入时机契约）');
    });
  });

  group('历史分页与排序（message-paging-and-ordering）', () {
    test('GWT-001 keyset 游标连续翻页有序无重复且终止判定明确', () async {
      final cache = _SeededTimelineCache();
      final repo = _PagedMessageRepository(120);
      final container = ProviderContainer(
        overrides: _boundaryOverrides(message: repo, timelineCache: cache),
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        chatMessageProvider(_conversationId).notifier,
      );

      await notifier.loadMessages();
      var state = container.read(chatMessageProvider(_conversationId));
      expect(state.messages.length, 50);
      expect(state.hasMore, isTrue);

      final firstAdded = await notifier.loadOlderMessages();
      expect(firstAdded, 50);
      final secondAdded = await notifier.loadOlderMessages();
      expect(secondAdded, 20, reason: '最后一页只剩 20 条历史');

      state = container.read(chatMessageProvider(_conversationId));
      expect(
        state.messages.map((m) => m.seq).toList(),
        List<int>.generate(120, (index) => index + 1),
        reason: '合并结果必须按 seq 严格有序且无缺号、无重复',
      );
      expect(state.hasMore, isFalse, reason: '到达最早一条后必须给出明确终止态');

      final callsBefore = repo.listCallCount;
      final extraAdded = await notifier.loadOlderMessages();
      expect(extraAdded, 0);
      expect(repo.listCallCount, callsBefore, reason: '终止态下不得以空结果反复触发加载');
    });

    test('GWT-002 翻页失败返回失败态且保留已加载内容', () async {
      final cache = _SeededTimelineCache();
      final repo = _PagedMessageRepository(120);
      final container = ProviderContainer(
        overrides: _boundaryOverrides(message: repo, timelineCache: cache),
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        chatMessageProvider(_conversationId).notifier,
      );

      await notifier.loadMessages();
      final loadedSeqs = container
          .read(chatMessageProvider(_conversationId))
          .messages
          .map((m) => m.seq)
          .toList();

      repo.failNextCalls = true;
      await notifier.loadOlderMessages();

      final state = container.read(chatMessageProvider(_conversationId));
      expect(state.error, isNotNull, reason: '翻页失败必须返回失败态而非静默截断');
      expect(
        state.messages.map((m) => m.seq).toList(),
        loadedSeqs,
        reason: '失败时必须保留已加载内容',
      );
      expect(state.isLoadingOlder, isFalse);
    });
  });
}
