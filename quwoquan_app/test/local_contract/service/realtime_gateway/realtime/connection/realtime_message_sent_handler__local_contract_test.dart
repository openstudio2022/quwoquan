import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_cache_record.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';

void main() {
  // 会话/离线缓存清理会落到本地 sqflite 索引，VM 测试需先装配 ffi factory。
  setUpAll(ensureSqfliteFfiInitialized);

  testWidgets('MessageSent 只接受 canonical event 并生成 typed card', (tester) async {
    late ProviderContainer container;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...chatTestRepositoryOverrides(),
          activePersonaContextLoaderProvider.overrideWithValue(
            _activePersonaContext,
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );
    await tester.pump();

    RealtimeMessageHandler(container.read).handle(<String, dynamic>{
      'type': 'MessageSent',
      'conversationId': 'conv_card',
      'payload': <String, dynamic>{
        'messageId': 'msg_card',
        'conversationId': 'conv_card',
        'seq': 8,
        'clientMsgId': 'client_card',
        'senderId': 'persona_sender',
        'type': 'card',
        'content': '查看分享',
        'card': <String, dynamic>{
          'kind': 'content_post',
          'title': '城市漫步',
          'attributes': <Map<String, String>>[
            <String, String>{'name': 'postId', 'value': 'post_001'},
          ],
        },
        'personaContextVersion': 2,
        'timestamp': '2026-07-15T08:00:00Z',
      },
    });
    await tester.pump();

    final messages = container
        .read(chatMessageTimelineProvider('conv_card'))
        .messages;
    final message = messages.singleWhere((item) => item.id == 'msg_card');
    expect(message.card?.kind.wireName, 'content_post');
    expect(message.card?.attributes.single.value, 'post_001');
  });

  testWidgets('已移除字段 event 与 media event 均通过 Reader 恢复而非动态解码', (tester) async {
    final repository = _CountingMessageRepository(ChatTestFacets().message);
    late ProviderContainer container;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...chatTestRepositoryOverrides(message: repository),
          activePersonaContextLoaderProvider.overrideWithValue(
            _activePersonaContext,
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );
    await tester.pump();
    final handler = RealtimeMessageHandler(container.read);

    handler.handle(<String, dynamic>{
      'type': 'MessageSent',
      'conversationId': 'conv_recovery',
      'payload': <String, dynamic>{
        'messageId': 'removed_msg',
        'conversationId': 'conv_recovery',
        'seq': 9,
        'clientMsgId': 'removed_client',
        'senderId': 'persona_sender',
        'senderPersonaId': 'removed_alias',
        'type': 'text',
        'content': 'removed',
        'timestamp': '2026-07-15T08:00:01Z',
      },
    });
    await tester.pump();
    expect(repository.listMessagesCallCount, 1);
    expect(
      container
          .read(chatMessageTimelineProvider('conv_recovery'))
          .messages
          .any((item) => item.id == 'removed_msg'),
      isFalse,
    );

    handler.handle(<String, dynamic>{
      'type': 'MessageSent',
      'conversationId': 'conv_recovery',
      'payload': <String, dynamic>{
        'messageId': 'media_msg',
        'conversationId': 'conv_recovery',
        'seq': 10,
        'clientMsgId': 'media_client',
        'senderId': 'persona_sender',
        'type': 'image',
        'content': '',
        'mediaAssetId': 'asset_image',
        'timestamp': '2026-07-15T08:00:02Z',
      },
    });
    await tester.pump();
    expect(repository.listMessagesCallCount, 2);
    expect(
      container
          .read(chatMessageTimelineProvider('conv_recovery'))
          .messages
          .any((item) => item.id == 'media_msg'),
      isFalse,
    );
  });

  testWidgets('成员被移出时只清当事人的会话与离线缓存', (tester) async {
    late ProviderContainer container;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...chatTestRepositoryOverrides(),
          activePersonaContextLoaderProvider.overrideWithValue(
            _activePersonaContext,
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );
    await tester.pump();

    final cache = container.read(conversationCacheProvider);
    cache.put(
      const ConversationCacheRecord(id: 'conv_removed', title: '待移出的群聊'),
    );
    final handler = RealtimeMessageHandler(
      container.read,
      currentUserIdResolver: () => 'persona_removed',
    );

    handler.handle(<String, dynamic>{
      'type': 'ConversationMemberRemoved',
      'conversationId': 'conv_removed',
      'payload': <String, dynamic>{'userId': 'persona_removed'},
    });
    await tester.pump();

    expect(cache.get('conv_removed'), isNull, reason: '终态成员事件必须立即清除当事人的本地会话行');
  });
}

Future<ActivePersonaContextViewData> _activePersonaContext() async =>
    ActivePersonaContextViewData(
      personaId: 'persona_test',
      ownerUserId: 'account_test',
      subjectType: 'persona',
      displayName: '测试分身',
      avatarUrl: '',
    );

class _CountingMessageRepository implements ChatMessageRepository {
  _CountingMessageRepository(this._delegate);

  final ChatMessageRepository _delegate;
  int listMessagesCallCount = 0;

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    listMessagesCallCount += 1;
    return const <ChatMessageViewData>[];
  }

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) => _delegate.recallMessage(
    conversationId: conversationId,
    messageId: messageId,
  );

  @override
  Future<ChatMessageSyncViewData> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = ChatSyncMessagesQuery.defaultLimit,
  }) => _delegate.syncMessages(
    conversationId: conversationId,
    lastSeq: lastSeq,
    limit: limit,
  );

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) => _delegate.markAsRead(
    conversationId: conversationId,
    messageId: messageId,
  );

  @override
  Future<List<ChatMessageReceipt>> getReceipts({
    required String conversationId,
    required String messageId,
  }) => _delegate.getReceipts(
    conversationId: conversationId,
    messageId: messageId,
  );
}
