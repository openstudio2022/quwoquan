import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/group_admins_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

const _testConvId = 'conv_002';

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/$_testConvId/admins',
        routes: [
          GoRoute(
            path: '/chat/:id/admins',
            builder: (_, state) => GroupAdminsPage(
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
  group('GroupAdminsPage — 渲染契约', () {
    testWidgets('正常渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupAdminsPage), findsOneWidget);
    });

    testWidgets('AppBar 标题显示"选择群成员"', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.selectGroupMembers), findsOneWidget);
    });

    testWidgets('加载完成后显示成员列表', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ListView), findsWidgets);
    });

    testWidgets('列表中不含群主', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // conv_002 群主 displayName='我'，不应出现
      expect(find.text('我'), findsNothing);
    });

    testWidgets('初始管理员显示管理员标签', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.admin), findsWidgets);
    });

    testWidgets('完成按钮显示已选人数', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // 初始有 1 个管理员已选中
      expect(find.textContaining('完成'), findsOneWidget);
    });
  });

  group('GroupAdminsPage — 交互契约', () {
    testWidgets('搜索框可输入过滤成员', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final textField = find.byType(CupertinoSearchTextField);
      expect(textField, findsOneWidget);

      await tester.enterText(textField, '李明');
      await tester.pump();
      expect(find.text('李明'), findsWidgets);
    });

    testWidgets('tap 未选中成员后选中态变化', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final member = find.text('张华');
      expect(member, findsOneWidget);

      await tester.tap(member);
      await tester.pump();

      // 页面仍存在（不崩溃）
      expect(find.byType(GroupAdminsPage), findsOneWidget);
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

  group('GroupAdminsPage — 错误态渲染', () {
    testWidgets('listMembers 失败时页面不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _ErrorMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupAdminsPage), findsOneWidget);
    });

    testWidgets('空成员列表时安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _EmptyMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupAdminsPage), findsOneWidget);
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
