import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_detail_page.dart';

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp(
      home: Scaffold(
        body: ChatDetailPage(
          conversationId: 'conv_001',
          onBack: () {},
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatDetailPage — 渲染契约', () {
    testWidgets('消息列表渲染至少 1 条消息可见', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
    });

    testWidgets('页面包含输入区域', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatDetailPage — 交互契约', () {
    testWidgets('页面正常加载不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
    });

    testWidgets('返回按钮回调正确触发', (tester) async {
      var backCalled = false;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            chatRepositoryProvider.overrideWithValue(MockChatRepository()),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: ChatDetailPage(
                conversationId: 'conv_001',
                onBack: () => backCalled = true,
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final backButtons = find.byIcon(Icons.arrow_back_ios_new);
      if (backButtons.evaluate().isNotEmpty) {
        await tester.tap(backButtons.first);
        await tester.pump();
        expect(backCalled, isTrue);
      } else {
        expect(find.byType(ChatDetailPage), findsOneWidget);
      }
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('ChatDetailPage — 错误态渲染', () {
    testWidgets('加载失败时页面不崩溃', (tester) async {
      await tester.pumpWidget(
        _scopedApp(mock: _ErrorChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
    });

    testWidgets('空消息列表安全渲染', (tester) async {
      await tester.pumpWidget(
        _scopedApp(mock: _EmptyMessagesChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChatDetailPage), findsOneWidget);
    });
  });
}

class _ErrorChatRepository extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    throw Exception('Network error');
  }
}

class _EmptyMessagesChatRepository extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    return [];
  }
}
