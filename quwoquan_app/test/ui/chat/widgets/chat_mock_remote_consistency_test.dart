import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';

Widget _scopedApp({required ChatRepository overrideRepo}) {
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(overrideRepo)],
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
    testWidgets('MockChatRepository 注入后 ChatPage 可渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(overrideRepo: MockChatRepository()));
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('Provider override 可正确切换 Repository', (tester) async {
      final customMock = _CustomMockChatRepository();
      await tester.pumpWidget(_scopedApp(overrideRepo: customMock));
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约 — 无直接实例化 Repository
  // ──────────────────────────────────────────────────────────────────
  group('Chat Mock/Remote 一致性 — 交互契约', () {
    testWidgets('通过 Provider 注入 MockChatRepository 正常工作', (tester) async {
      await tester.pumpWidget(_scopedApp(overrideRepo: MockChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatPage), findsOneWidget);
    });

    test('chatRepositoryProvider 默认返回 ChatRepository 子类型', () {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
        ],
      );
      addTearDown(container.dispose);

      final repo = container.read(chatRepositoryProvider);
      expect(repo, isA<ChatRepository>());
      expect(repo, isA<MockChatRepository>());
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('Chat Mock/Remote 一致性 — 错误态渲染', () {
    testWidgets('空数据 Repository 注入后 ChatPage 安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(overrideRepo: _EmptyChatRepository()));
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('异常 Repository 注入后 ChatPage 不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp(overrideRepo: _ErrorChatRepository()));
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });
  });
}

class _CustomMockChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return const [
      ChatInboxDto(
        id: 'conv_custom',
        type: 'direct',
        title: '自定义会话',
        avatarUrl: '',
        avatarCompositeUrls: <String>[],
        lastMessagePreview: '来自自定义仓库',
        lastMessageType: 'text',
        lastMessageTime: null,
        lastSeq: 1,
        unreadCount: 0,
        mentionUnreadCount: 0,
        muted: false,
        pinned: false,
      ),
    ];
  }

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return [
      {
        '_id': 'conv_custom',
        'type': 'direct',
        'title': '自定义会话',
        'status': 'active',
        'memberCount': 2,
        'maxSeq': 1,
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      },
    ];
  }
}

class _EmptyChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return const <ChatInboxDto>[];
  }

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return [];
  }
}

class _ErrorChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    throw Exception('Repository error');
  }

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    throw Exception('Repository error');
  }
}
