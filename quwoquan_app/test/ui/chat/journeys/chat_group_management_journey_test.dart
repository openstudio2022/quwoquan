import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/group-chat/conv_test',
        routes: [
          GoRoute(
            path: '/group-chat/:id',
            builder: (_, state) => StartGroupChatPage(
              conversationId: state.pathParameters['id'] ?? '',
              onBack: () {},
            ),
          ),
          GoRoute(
            path: '/user/:id',
            builder: (_, state) => Scaffold(
              body: Center(
                child: Text('User ${state.pathParameters['id']}'),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final msg = details.exception.toString();
    if (msg.contains('HTTP request failed') ||
        msg.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  group('旅程正常路径', () {
    testWidgets('发起群聊页正常加载', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(StartGroupChatPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('搜索框可见且可输入', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(TextField), findsOneWidget);
      await tester.enterText(find.byType(TextField), '测试搜索');
      await tester.pump();

      expect(find.text('测试搜索'), findsOneWidget);
    });

    testWidgets('相关同好列表区域可见', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(StartGroupChatPage), findsOneWidget);
      expect(find.byType(ListView), findsWidgets);
    });
  });

  group('旅程错误路径', () {
    testWidgets('加载失败页面不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _ErrorGroupChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(StartGroupChatPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('创建群聊 Repository 异常时页面安全', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _ErrorGroupChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(StartGroupChatPage), findsOneWidget);
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('无联系人时安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _EmptyContactsChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(StartGroupChatPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('空会话列表安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _EmptyConversationChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(StartGroupChatPage), findsOneWidget);
    });

    testWidgets('多次搜索输入不导致状态异常', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final textField = find.byType(TextField);
      for (final query in ['测试一', '测试二', '测试三']) {
        await tester.enterText(textField, query);
        await tester.pump();
      }
      expect(find.byType(StartGroupChatPage), findsOneWidget);
    });
  });
}

class _ErrorGroupChatRepository extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    throw Exception('Network error');
  }

  @override
  Future<List<Map<String, dynamic>>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    throw Exception('Network error');
  }

  @override
  Future<Map<String, dynamic>> createConversation({
    required String type,
    String? title,
    String? circleId,
    int? maxGroupSize,
  }) async {
    throw Exception('创建群聊失败');
  }
}

class _EmptyContactsChatRepository extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    return [];
  }
}

class _EmptyConversationChatRepository extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return [];
  }
}
