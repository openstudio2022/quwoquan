import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat',
        routes: [
          GoRoute(
            path: '/chat',
            builder: (_, _) => const Scaffold(body: ChatPage()),
          ),
          GoRoute(
            path: '/chat/:id',
            builder: (_, _) =>
                const SizedBox(key: ValueKey('chat-detail-page')),
          ),
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
  group('ChatPage — 渲染契约', () {
    testWidgets('正常渲染聊天列表页', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('包含 Scaffold 结构', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(Scaffold), findsWidgets);
    });
  });

  group('ChatPage — 交互契约', () {
    testWidgets('tap 会话列表项触发导航', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('产品共创群').first);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('chat-detail-page')), findsOneWidget);
    });

    testWidgets('下拉刷新不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      await tester.drag(find.byType(ChatPage), const Offset(0, 300));
      await tester.pumpAndSettle();

      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('右上入口向内收至统一安全边距', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final page = find.byType(ChatPage);
      final addIcon = find.byIcon(CupertinoIcons.add).first;
      final screenWidth = tester.getSize(page).width;
      final addRightInset = screenWidth - tester.getTopRight(addIcon).dx;
      final expectedInset = AppSpacing.topBarTrailingVisualInset(
        tester.element(page),
      );

      expect(addRightInset, closeTo(expectedInset, 2.0));
    });

    testWidgets('列表区左滑先切二级 Tab，二级越界后再切一级 Tab', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final swipeRegion = find.byType(SafeArea).first;

      for (var i = 0; i < 3; i++) {
        await tester.fling(swipeRegion, const Offset(-420, 0), 1200);
        await tester.pumpAndSettle();
      }

      expect(find.text(UITextConstants.secretPasswordPrompt), findsOneWidget);

      await tester.fling(
        find.text(UITextConstants.secretPasswordPrompt),
        const Offset(-420, 0),
        1200,
      );
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.contactsTabFunGroup), findsOneWidget);
      expect(find.text(UITextConstants.secretPasswordPrompt), findsNothing);
    });
  });

  group('ChatPage — 错误态渲染', () {
    testWidgets('Repository 返回空列表时安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(mock: _EmptyChatRepository()));
      await tester.pumpAndSettle();

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.text(UITextConstants.noConversations), findsOneWidget);
    });
  });
}

class _EmptyChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return const <ChatInboxDto>[];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return const <ChatInboxDto>[];
  }
}
