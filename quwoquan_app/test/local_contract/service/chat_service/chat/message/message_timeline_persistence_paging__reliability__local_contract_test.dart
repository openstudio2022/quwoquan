/// 消息时间线本地落盘与历史分页的可靠性契约。
///
/// 覆盖：冷启动/离线打开会话由本地副本水合（离线只读来源可区分）、
/// 本地为空且远端失败呈现可重试失败态、远端结果写入本地副本、
/// keyset 游标向上翻页有序无重复且终止判定明确、翻页失败保留已加载内容。
///
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-timeline-local-persistence/spec.md#gwt-001
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-timeline-local-persistence/spec.md#gwt-002
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-001
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-002
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

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

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    listCallCount += 1;
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
}

List<Override> _boundaryOverrides({
  required ChatMessageRepository message,
  required ChatMessageTimelineCache timelineCache,
}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    ...chatTestRepositoryOverrides(message: message),
    chatMessageTimelineCacheProvider.overrideWithValue(timelineCache),
    personaQueryProvider(
      AppUiSurfaces.appShell,
    ).overrideWithValue(_ChatPersonaQuery()),
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
      expect(
        state.messages.map((m) => m.seq).toList(),
        [1, 2, 3],
        reason: '时间线必须由本地副本水合并按 seq 有序展示',
      );
      expect(
        state.source,
        ChatTimelineContentSource.offlineReadOnly,
        reason: '本地命中且远端失败必须表达为离线只读，而非刷新失败',
      );
      expect(
        state.error,
        isNull,
        reason: '离线只读不得与远端失败混为同一错误态',
      );
      expect(state.isLoading, isFalse);
      expect(state.isRefreshing, isFalse);
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
      expect(
        state.error,
        isNotNull,
        reason: '本地为空且远端失败必须呈现失败态，不得以空列表冒充没有消息',
      );
      expect(state.source, ChatTimelineContentSource.none);
      expect(
        cache.writes,
        isEmpty,
        reason: '失败不得写入任何本地成功事实',
      );
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
      expect(
        cache.writes,
        isNotEmpty,
        reason: '远端拉取结果必须写入本地副本（写入时机契约）',
      );
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
      expect(
        state.hasMore,
        isFalse,
        reason: '到达最早一条后必须给出明确终止态',
      );

      final callsBefore = repo.listCallCount;
      final extraAdded = await notifier.loadOlderMessages();
      expect(extraAdded, 0);
      expect(
        repo.listCallCount,
        callsBefore,
        reason: '终止态下不得以空结果反复触发加载',
      );
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
      expect(
        state.error,
        isNotNull,
        reason: '翻页失败必须返回失败态而非静默截断',
      );
      expect(
        state.messages.map((m) => m.seq).toList(),
        loadedSeqs,
        reason: '失败时必须保留已加载内容',
      );
      expect(state.isLoadingOlder, isFalse);
    });
  });
}
