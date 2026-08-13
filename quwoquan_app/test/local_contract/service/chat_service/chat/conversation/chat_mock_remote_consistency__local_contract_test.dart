import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/chat_service/chat/chat_inbox_view/chat_inbox_view_fixture_builder.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/notification_service/notification_delivery/notification/app_message_typed_double.dart';
import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

Widget _scopedApp({
  ChatInboxRepository? inbox,
  ChatConversationRepository? conversation,
}) {
  return ProviderScope(
    overrides: [
      // 消息页顶部的 App 消息未读角标走 notification 对象的 typed port；
      // 先封死 App↔Cloud 边界，再显式声明本套件真正依赖的两个对象级 port。
      ...sealedCloudBoundaryOverrides(),
      ...chatTestRepositoryOverrides(inbox: inbox, conversation: conversation),
      appMessageQueryProvider.overrideWithValue(
        const EmptyAppMessageQueryDouble(),
      ),
      greetingRepositoryProvider.overrideWithValue(alphaGreetingRepository()),
      visitRecorderServiceProvider.overrideWithValue(_NoopVisitRecorder()),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat',
        routes: [
          GoRoute(
            path: '/chat',
            builder: (_, _) => const Scaffold(body: ChatPage()),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
          GoRoute(
            path: '/chat/:id/settings',
            builder: (_, _) => const SizedBox(),
          ),
        ],
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约 — Mock/Remote Provider 注入一致性
  // ──────────────────────────────────────────────────────────────────
  group('Chat Mock/Remote 一致性 — 渲染契约', () {
    testWidgets('窄接口注入后 ChatPage 可渲染', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('Provider override 可正确切换 Repository', (tester) async {
      final custom = _ChatPageRepositoryOverrides.custom();
      await tester.pumpWidget(
        _scopedApp(inbox: custom.inbox, conversation: custom.conversation),
      );
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约 — 无直接实例化 Repository
  // ──────────────────────────────────────────────────────────────────
  group('Chat Mock/Remote 一致性 — 交互契约', () {
    testWidgets('通过 Provider 注入窄接口正常工作', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatPage), findsOneWidget);
    });

    test('chatTestRepositoryOverrides 可替换单个窄接口', () {
      final custom = _ChatPageRepositoryOverrides.custom();
      final container = ProviderContainer(
        overrides: chatTestRepositoryOverrides(inbox: custom.inbox),
      );
      addTearDown(container.dispose);

      expect(container.read(chatInboxRepositoryProvider), same(custom.inbox));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('Chat Mock/Remote 一致性 — 错误态渲染', () {
    testWidgets('空数据 Repository 注入后 ChatPage 安全渲染', (tester) async {
      final empty = _ChatPageRepositoryOverrides.empty();
      await tester.pumpWidget(
        _scopedApp(inbox: empty.inbox, conversation: empty.conversation),
      );
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('异常 Repository 注入后 ChatPage 不崩溃', (tester) async {
      final error = _ChatPageRepositoryOverrides.error();
      await tester.pumpWidget(
        _scopedApp(inbox: error.inbox, conversation: error.conversation),
      );
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });
  });
}

/// 本套件断言的是 ChatPage 的渲染健壮性，与访问轨迹落库无关。
final class _NoopVisitRecorder extends VisitRecorderService {
  _NoopVisitRecorder() : super();

  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

final class _ChatPageRepositoryOverrides {
  _ChatPageRepositoryOverrides._(this.inbox, this.conversation);

  factory _ChatPageRepositoryOverrides.custom() {
    final state = _InboxRowsState.custom();
    return _ChatPageRepositoryOverrides._(
      _InboxAdapter(state),
      _ConversationListAdapter(state),
    );
  }

  factory _ChatPageRepositoryOverrides.empty() {
    final state = _InboxRowsState.empty();
    return _ChatPageRepositoryOverrides._(
      _InboxAdapter(state),
      _ConversationListAdapter(state),
    );
  }

  factory _ChatPageRepositoryOverrides.error() {
    final state = _InboxRowsState.error();
    return _ChatPageRepositoryOverrides._(
      _InboxAdapter(state),
      _ConversationListAdapter(state),
    );
  }

  final ChatInboxRepository inbox;
  final ChatConversationRepository conversation;
}

final class _InboxRowsState {
  _InboxRowsState.custom() : _mode = _InboxRowsMode.custom;
  _InboxRowsState.empty() : _mode = _InboxRowsMode.empty;
  _InboxRowsState.error() : _mode = _InboxRowsMode.error;

  final _InboxRowsMode _mode;

  Future<List<ChatInboxViewData>> rows() async {
    if (_mode == _InboxRowsMode.error) {
      throw Exception('Repository error');
    }
    if (_mode == _InboxRowsMode.empty) {
      return const <ChatInboxViewData>[];
    }
    return [
      chatInboxFixture(
        id: 'conv_custom',
        type: 'direct',
        title: '自定义会话',
        avatarUrl: '',
        lastMessagePreview: '来自自定义仓库',
        lastMessageType: MessageType.text,
        lastMessageTime: null,
        lastSeq: 1,
        unreadCount: 0,
        mentionUnreadCount: 0,
        muted: false,
        pinned: false,
        circleId: '',
      ),
    ];
  }
}

enum _InboxRowsMode { custom, empty, error }

final class _InboxAdapter extends Fake implements ChatInboxRepository {
  _InboxAdapter(this._state);

  final _InboxRowsState _state;

  @override
  Future<List<ChatInboxViewData>> listInbox({String? cursor, int limit = 20}) =>
      _state.rows();
}

final class _ConversationListAdapter extends Fake
    implements ChatConversationRepository {
  _ConversationListAdapter(this._state);

  final _InboxRowsState _state;

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = 20,
  }) => _state.rows();
}
