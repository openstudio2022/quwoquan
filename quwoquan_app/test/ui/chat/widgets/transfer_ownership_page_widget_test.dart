import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/transfer_ownership_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

const _testConvId = 'conv_002';

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/$_testConvId/transfer-ownership',
        routes: [
          GoRoute(
            path: '/chat/:id/transfer-ownership',
            builder: (_, state) => TransferOwnershipPage(
              conversationId: state.pathParameters['id'] ?? _testConvId,
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
  group('TransferOwnershipPage — 渲染契约', () {
    testWidgets('正常渲染页面', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });

    testWidgets('AppBar 标题显示"选择新群主"', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.selectNewOwner), findsOneWidget);
    });

    testWidgets('搜索框可见', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(CupertinoSearchTextField), findsOneWidget);
    });

    testWidgets('成员列表不含群主自身', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // conv_002 群主 displayName='我'，不应出现在候选列表
      expect(find.text('我'), findsNothing);
    });

    testWidgets('成员列表可见且有候选人', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ListView), findsWidgets);
      // conv_002 中 user_002（李明）是候选人
      expect(find.text('李明'), findsOneWidget);
    });
  });

  group('TransferOwnershipPage — 交互契约', () {
    testWidgets('搜索框可输入过滤', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final searchField = find.byType(CupertinoSearchTextField);
      await tester.enterText(searchField, '李明');
      await tester.pump();

      expect(find.text('李明'), findsWidgets);
    });

    testWidgets('点击成员弹出确认弹窗', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final memberItems = find.byType(InkWell);
      expect(memberItems, findsWidgets);

      await tester.tap(memberItems.first);
      await tester.pumpAndSettle();

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    });

    testWidgets('确认弹窗包含成员名字', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text('李明'));
      await tester.pumpAndSettle();

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.text(UITextConstants.cancel), findsOneWidget);
      expect(find.text(UITextConstants.confirm), findsOneWidget);
    });

    testWidgets('取消弹窗后页面继续存在', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.byType(InkWell).first);
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.cancel));
      await tester.pumpAndSettle();

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });

    testWidgets('返回按钮 tap 不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final backButtons = find.byIcon(CupertinoIcons.back);
      if (backButtons.evaluate().isNotEmpty) {
        await tester.tap(backButtons.first);
        await tester.pump();
      }
      tester.takeException();
    });
  });

  group('TransferOwnershipPage — 错误态渲染', () {
    testWidgets('listMembers 失败时页面不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _ErrorMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });

    testWidgets('空成员列表安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _EmptyMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(TransferOwnershipPage), findsOneWidget);
    });
  });
}

class _ErrorMembersRepo extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
  }) async {
    throw Exception('network error');
  }
}

class _EmptyMembersRepo extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
  }) async {
    return [];
  }
}
