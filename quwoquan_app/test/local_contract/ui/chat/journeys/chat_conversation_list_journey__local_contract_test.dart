import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/chat_fixture.dart';

import '../../../../support/cloud_services/user_typed_facet_test_support.dart';

Widget _scopedApp({
  AlphaChatStateEngine? engine,
  ChatConversationRepository? conversationFacet,
  ChatContactRepository? contactFacet,
  ChatMemberRepository? memberFacet,
}) {
  final stateEngine = engine ?? AlphaChatStateEngine();
  final appMessages = _EmptyAppMessageFacet();
  return ProviderScope(
    retry: (_, _) => null,
    overrides: [
      chatConversationRepositoryProvider.overrideWithValue(
        conversationFacet ?? _AlphaChatConversationJourneyFacet(stateEngine),
      ),
      chatContactRepositoryProvider.overrideWithValue(
        contactFacet ?? _AlphaChatContactJourneyFacet(stateEngine),
      ),
      chatMemberRepositoryProvider.overrideWithValue(
        memberFacet ?? _AlphaChatMemberJourneyFacet(stateEngine),
      ),
      greetingRepositoryProvider.overrideWithValue(alphaGreetingRepository()),
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
            builder: (_, _) => const Scaffold(body: ChatPage()),
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
    return const AppMessageUnreadCountSlice(unreadCount: 0);
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
      final engine = AlphaChatStateEngine();
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
      final engine = AlphaChatStateEngine();
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
      final engine = AlphaChatStateEngine();
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
      final engine = AlphaChatStateEngine();
      await _pumpJourneyApp(
        tester,
        _scopedApp(
          engine: engine,
          conversationFacet: _AlphaChatConversationJourneyFacet(
            engine,
            listMessageHomeFailure: StateError('消息首页加载失败'),
          ),
        ),
      );

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.byType(AppPageErrorState), findsOneWidget);
      expect(find.text(ChatText.chatListLoadFailedTitle), findsOneWidget);
    });

    testWidgets('会话 Facet 异常不导致页面崩溃', (tester) async {
      final engine = AlphaChatStateEngine();
      await _pumpJourneyApp(
        tester,
        _scopedApp(
          engine: engine,
          conversationFacet: _AlphaChatConversationJourneyFacet(
            engine,
            listMessageHomeFailure: StateError('消息首页加载失败'),
          ),
        ),
      );

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.byType(AppPageErrorState), findsOneWidget);
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('空列表安全渲染', (tester) async {
      final engine = AlphaChatStateEngine(
        seedConversations: const <Map<String, Object?>>[],
      );
      await _pumpJourneyApp(tester, _scopedApp(engine: engine));

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.text(ChatText.noConversations), findsOneWidget);
    });

    testWidgets('多次切换 Tab 不导致状态异常', (tester) async {
      final engine = AlphaChatStateEngine();
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

final class _AlphaChatConversationJourneyFacet extends Fake
    implements ChatConversationRepository {
  _AlphaChatConversationJourneyFacet(
    this._engine, {
    this.listMessageHomeFailure,
  });

  final AlphaChatStateEngine _engine;
  final Object? listMessageHomeFailure;

  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    final failure = listMessageHomeFailure;
    if (failure != null) {
      throw failure;
    }
    return _messageHomeRows(_engine, filter: filter, limit: limit);
  }
}

final class _AlphaChatContactJourneyFacet extends Fake
    implements ChatContactRepository {
  _AlphaChatContactJourneyFacet(this._engine);

  final AlphaChatStateEngine _engine;

  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    return _contactHomeRows(_engine, filter: filter, limit: limit);
  }
}

final class _AlphaChatMemberJourneyFacet extends Fake
    implements ChatMemberRepository {
  _AlphaChatMemberJourneyFacet(this._engine);

  final AlphaChatStateEngine _engine;

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
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
          (row) => ChatConversationMemberDto.fromMap(
            Map<String, dynamic>.from(row),
          ).copyWith(avatarUrl: ''),
        )
        .toList(growable: false);
  }
}

List<MessageHomeRowDto> _messageHomeRows(
  AlphaChatStateEngine engine, {
  String filter = 'all',
  int limit = 100,
}) {
  return engine
      .listMessageHome(filter: filter, limit: limit)
      .map(
        (row) => MessageHomeRowDto.fromMap(
          Map<String, dynamic>.from(row),
        ).copyWith(avatarUrl: ''),
      )
      .toList(growable: false);
}

List<ContactHomeRowDto> _contactHomeRows(
  AlphaChatStateEngine engine, {
  String filter = 'all',
  int limit = 500,
}) {
  return engine
      .listContactHome(filter: filter, limit: limit)
      .map(
        (row) => ContactHomeRowDto.fromMap(
          Map<String, dynamic>.from(row),
        ).copyWith(avatarUrl: ''),
      )
      .toList(growable: false);
}
