// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/message-home-commercial-ia/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/application/public/greeting_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/chat_service/chat/conversation/conversation_state_typed_double.dart';

import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

Widget _scopedApp({
  InMemoryChatStateEngine? engine,
  ChatConversationRepository? conversationFacet,
  ChatContactRepository? contactFacet,
  ChatMemberRepository? memberFacet,
  GreetingRepository? greetingRepository,
  ValueNotifier<bool>? chatVisibility,
}) {
  final stateEngine = engine ?? InMemoryChatStateEngine();
  final appMessages = _EmptyAppMessageFacet();
  return ProviderScope(
    retry: (_, _) => null,
    overrides: [
      chatConversationRepositoryProvider.overrideWithValue(
        conversationFacet ?? _InMemoryChatConversationJourneyFacet(stateEngine),
      ),
      chatContactRepositoryProvider.overrideWithValue(
        contactFacet ?? _InMemoryChatContactJourneyFacet(stateEngine),
      ),
      chatMemberRepositoryProvider.overrideWithValue(
        memberFacet ?? _InMemoryChatMemberJourneyFacet(stateEngine),
      ),
      greetingRepositoryProvider.overrideWithValue(
        greetingRepository ?? alphaGreetingRepository(),
      ),
      appMessageQueryProvider.overrideWithValue(appMessages),
      appMessageCommandWriterProvider.overrideWithValue(appMessages),
      visitRecorderServiceProvider.overrideWithValue(
        _NoopVisitRecorderService(),
      ),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: AppRoutePaths.chat,
        routes: [
          GoRoute(
            path: AppRoutePaths.chat,
            builder: (_, _) => Scaffold(
              body: chatVisibility == null
                  ? const ChatPage()
                  : ValueListenableBuilder<bool>(
                      valueListenable: chatVisibility,
                      child: const ChatPage(),
                      builder: (_, enabled, child) =>
                          TickerMode(enabled: enabled, child: child!),
                    ),
            ),
          ),
          GoRoute(
            path: AppRoutePaths.chatDetailPathTemplate.replaceAll(
              '{id}',
              ':id',
            ),
            builder: (_, state) => Scaffold(
              body: Center(
                child: Text('ChatDetail ${state.pathParameters['id']}'),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

final class _NoopVisitRecorderService extends VisitRecorderService {
  _NoopVisitRecorderService() : super();

  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

final class _EmptyAppMessageFacet
    implements AppMessageQuery, AppMessageCommandWriter {
  @override
  Future<AppMessage> acknowledge(AckAppMessageCommand command) async {
    throw StateError('空通知收件箱不存在可确认消息');
  }

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async {
    throw StateError('空通知收件箱不存在消息');
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async {
    return AppMessageUnreadCountSlice(unreadCount: 0);
  }

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
    return AppMessageInboxSlice(items: const <AppMessage>[]);
  }

  @override
  Future<AppMessage> markRead(ReadAppMessageCommand command) async {
    throw StateError('空通知收件箱不存在可读消息');
  }
}

Future<void> _pumpJourneyApp(WidgetTester tester, Widget app) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(390, 844);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(app);
  await tester.pumpAndSettle();
}

void main() {
  group('旅程正常路径', () {
    testWidgets('会话列表正常加载并显示会话', (tester) async {
      final engine = InMemoryChatStateEngine();
      final expected = _messageHomeRows(engine).first;
      await _pumpJourneyApp(tester, _scopedApp(engine: engine));

      expect(find.byType(ChatPage), findsOneWidget);
      expect(
        find.byKey(
          ValueKey<String>('chat-inbox-row-${expected.conversationId}'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('Tab 切换消息/联系人', (tester) async {
      final engine = InMemoryChatStateEngine();
      final expectedMessage = _messageHomeRows(engine).first;
      final expectedContact = _contactHomeRows(engine).first;
      await _pumpJourneyApp(tester, _scopedApp(engine: engine));

      expect(find.byType(ChatPage), findsOneWidget);

      await tester.tap(find.text(ChatText.chatPrimaryContacts));
      await tester.pumpAndSettle();
      expect(
        find.byKey(ValueKey<String>('chat-contact-row-${expectedContact.id}')),
        findsOneWidget,
      );

      await tester.tap(find.text(AppConceptConstants.messages));
      await tester.pumpAndSettle();
      expect(
        find.byKey(
          ValueKey<String>('chat-inbox-row-${expectedMessage.conversationId}'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('会话列表显示会话标题和最后一条消息', (tester) async {
      final engine = InMemoryChatStateEngine();
      final expected = _messageHomeRows(
        engine,
      ).firstWhere((row) => row.title.isNotEmpty && row.summary.isNotEmpty);
      await _pumpJourneyApp(tester, _scopedApp(engine: engine));

      expect(find.text(expected.title), findsOneWidget);
      expect(find.text(expected.summary), findsOneWidget);
    });
  });

  group('旅程错误路径', () {
    testWidgets('加载失败显示错误态', (tester) async {
      final engine = InMemoryChatStateEngine();
      await _pumpJourneyApp(
        tester,
        _scopedApp(
          engine: engine,
          conversationFacet: _InMemoryChatConversationJourneyFacet(
            engine,
            listMessageHomeFailure: StateError('消息首页加载失败'),
          ),
        ),
      );

      expect(find.byType(ChatPage), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('chat-message-home-error-section')),
        findsOneWidget,
      );
    });

    testWidgets('会话 Facet 异常不导致页面崩溃', (tester) async {
      final engine = InMemoryChatStateEngine();
      await _pumpJourneyApp(
        tester,
        _scopedApp(
          engine: engine,
          conversationFacet: _InMemoryChatConversationJourneyFacet(
            engine,
            listMessageHomeFailure: StateError('消息首页加载失败'),
          ),
        ),
      );

      expect(find.byType(ChatPage), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('chat-message-home-error-section')),
        findsOneWidget,
      );
    });

    testWidgets('Greeting 分区失败不覆盖已确认会话且可独立重试', (tester) async {
      final engine = InMemoryChatStateEngine();
      final greeting = _ControllableGreetingRepository()..failInbox = true;
      final expected = _messageHomeRows(engine).first;
      await _pumpJourneyApp(
        tester,
        _scopedApp(engine: engine, greetingRepository: greeting),
      );

      expect(
        find.byKey(
          ValueKey<String>('chat-inbox-row-${expected.conversationId}'),
        ),
        findsOneWidget,
      );
      final errorSection = find.byKey(
        const ValueKey<String>('chat-greeting-inbox-error-section'),
      );
      expect(errorSection, findsOneWidget);
      expect(find.text(ChatText.noConversations), findsNothing);

      greeting.failInbox = false;
      await tester.tap(
        find.descendant(
          of: errorSection,
          matching: find.byType(CupertinoButton),
        ),
      );
      await tester.pumpAndSettle();

      expect(errorSection, findsNothing);
      expect(find.text(ChatText.chatGreetingInboxTitle), findsOneWidget);
    });

    testWidgets('重入与显式重试读取 authoritative 状态并保留 last-confirmed', (tester) async {
      final engine = InMemoryChatStateEngine();
      final conversation = _InMemoryChatConversationJourneyFacet(engine);
      final visibility = ValueNotifier<bool>(true);
      addTearDown(visibility.dispose);
      final original = _messageHomeRows(engine).first;
      await _pumpJourneyApp(
        tester,
        _scopedApp(
          engine: engine,
          conversationFacet: conversation,
          chatVisibility: visibility,
        ),
      );

      conversation.listMessageHomeFailure = StateError('重入刷新失败');
      visibility.value = false;
      await tester.pump();
      visibility.value = true;
      await tester.pumpAndSettle();

      expect(
        find.byKey(
          ValueKey<String>('chat-inbox-row-${original.conversationId}'),
        ),
        findsOneWidget,
      );
      final errorSection = find.byKey(
        const ValueKey<String>('chat-message-home-error-section'),
      );
      expect(errorSection, findsOneWidget);
      expect(find.text(ChatText.noConversations), findsNothing);

      conversation
        ..listMessageHomeFailure = null
        ..messageRowsOverride = <MessageHomeRow>[
          _journeyMessageHomeRow(id: 'conv_authoritative', title: '重入后的权威会话'),
        ];
      await tester.tap(
        find.descendant(
          of: errorSection,
          matching: find.byType(CupertinoButton),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('重入后的权威会话'), findsOneWidget);
      expect(errorSection, findsNothing);
      expect(conversation.listMessageHomeCallCount, greaterThan(2));
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('空列表安全渲染', (tester) async {
      final engine = InMemoryChatStateEngine(
        seedConversations: const <Map<String, Object?>>[],
      );
      await _pumpJourneyApp(tester, _scopedApp(engine: engine));

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.text(ChatText.noConversations), findsOneWidget);
    });

    testWidgets('多次切换 Tab 不导致状态异常', (tester) async {
      final engine = InMemoryChatStateEngine();
      final expectedMessage = _messageHomeRows(engine).first;
      final expectedContact = _contactHomeRows(engine).first;
      await _pumpJourneyApp(tester, _scopedApp(engine: engine));

      for (var i = 0; i < 3; i++) {
        await tester.tap(find.text(ChatText.chatPrimaryContacts));
        await tester.pumpAndSettle();
        expect(
          find.byKey(
            ValueKey<String>('chat-contact-row-${expectedContact.id}'),
          ),
          findsOneWidget,
        );

        await tester.tap(find.text(AppConceptConstants.messages));
        await tester.pumpAndSettle();
        expect(
          find.byKey(
            ValueKey<String>(
              'chat-inbox-row-${expectedMessage.conversationId}',
            ),
          ),
          findsOneWidget,
        );
      }
      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('二级 Tab 切换幂等', (tester) async {
      await _pumpJourneyApp(tester, _scopedApp());

      await tester.tap(find.text(ChatText.unread));
      await tester.pumpAndSettle();
      await tester.tap(find.text(ChatText.contactsTabAll));
      await tester.pumpAndSettle();

      expect(find.byType(ChatPage), findsOneWidget);
    });
  });
}

final class _InMemoryChatConversationJourneyFacet extends Fake
    implements ChatConversationRepository {
  _InMemoryChatConversationJourneyFacet(
    this._engine, {
    this.listMessageHomeFailure,
  });

  final InMemoryChatStateEngine _engine;
  Object? listMessageHomeFailure;
  List<MessageHomeRow>? messageRowsOverride;
  int listMessageHomeCallCount = 0;

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    listMessageHomeCallCount += 1;
    final failure = listMessageHomeFailure;
    if (failure != null) {
      throw failure;
    }
    return messageRowsOverride ??
        _messageHomeRows(_engine, filter: filter, limit: limit);
  }
}

final class _ControllableGreetingRepository implements GreetingRepository {
  bool failInbox = false;

  @override
  Future<List<GreetingRequestViewData>> listInbox({
    String status = 'pending',
    String? cursor,
    required int limit,
  }) async {
    if (failInbox) {
      throw StateError('greeting inbox unavailable');
    }
    final now = DateTime.utc(2026, 8, 8);
    return <GreetingRequestViewData>[
      GreetingRequestViewData(
        id: 'greeting_01',
        requesterPersonaId: 'persona_requester',
        targetPersonaId: 'persona_current',
        requestMessage: '你好，我们有共同兴趣',
        status: 'pending',
        source: 'profile',
        createdAt: now,
        updatedAt: now,
      ),
    ];
  }

  @override
  Future<GreetingRequestViewData> cancelGreeting(String requestId) =>
      throw StateError('not used by chat home');

  @override
  Future<GreetingRequestViewData> ignoreGreeting(String requestId) =>
      throw StateError('not used by chat home');

  @override
  Future<List<GreetingRequestViewData>> listOutbox({
    String status = 'pending',
    String? cursor,
    required int limit,
  }) => throw StateError('not used by chat home');

  @override
  Future<GreetingReplyResultViewData> replyGreeting(String requestId) =>
      throw StateError('not used by chat home');

  @override
  Future<GreetingRequestViewData> sendGreeting({
    required String targetPersonaId,
    String? requestMessage,
    String source = 'profile',
    GreetingIntersectionRef? intersectionRef,
  }) => throw StateError('not used by chat home');
}

MessageHomeRow _journeyMessageHomeRow({
  required String id,
  required String title,
}) => MessageHomeRow(
  id: id,
  kind: 'conversation',
  conversationId: id,
  notificationId: '',
  conversationType: 'direct',
  title: title,
  summary: 'authoritative',
  avatarUrl: '',
  groupAvatarVersion: 0,
  unreadCount: 0,
  mentionUnreadCount: 0,
  muted: false,
  pinned: false,
  notificationType: '',
  read: true,
);

final class _InMemoryChatContactJourneyFacet extends Fake
    implements ChatContactRepository {
  _InMemoryChatContactJourneyFacet(this._engine);

  final InMemoryChatStateEngine _engine;

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    return _contactHomeRows(_engine, filter: filter, limit: limit);
  }
}

final class _InMemoryChatMemberJourneyFacet extends Fake
    implements ChatMemberRepository {
  _InMemoryChatMemberJourneyFacet(this._engine);

  final InMemoryChatStateEngine _engine;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    return _engine
        .listMembers(
          conversationId: conversationId,
          limit: limit,
          role: role,
          sort: sort,
        )
        .map(
          (row) => ConversationMemberListRow.fromWire(<String, Object?>{
            ...row,
            'avatarUrl': '',
          }),
        )
        .toList(growable: false);
  }
}

List<MessageHomeRow> _messageHomeRows(
  InMemoryChatStateEngine engine, {
  String filter = 'all',
  int limit = 100,
}) {
  return engine
      .listMessageHome(filter: filter, limit: limit)
      .map(
        (row) =>
            MessageHomeRow.fromWire(<String, Object?>{...row, 'avatarUrl': ''}),
      )
      .toList(growable: false);
}

List<ContactHomeRow> _contactHomeRows(
  InMemoryChatStateEngine engine, {
  String filter = 'all',
  int limit = 500,
}) {
  return engine
      .listContactHome(filter: filter, limit: limit)
      .map((row) {
        final lastActiveAt = row['lastActiveAt'];
        return ContactHomeRow.fromWire(<String, Object?>{
          ...row,
          'avatarUrl': '',
          if (lastActiveAt is String && lastActiveAt.trim().isEmpty)
            'lastActiveAt': null,
        });
      })
      .toList(growable: false);
}
