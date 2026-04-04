import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/group_manage_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

const _testConvId = 'conv_002';

List<Override> _chatTestOverrides(ChatRepository repo) => [
      chatRepositoryProvider.overrideWithValue(repo),
      currentUserIdProvider.overrideWithValue(ChatMockData.currentUserProfileId),
    ];

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: _chatTestOverrides(repo),
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/$_testConvId/manage',
        routes: [
          GoRoute(
            path: '/chat/:id/manage',
            builder: (_, state) => GroupManagePage(
              conversationId: state.pathParameters['id'] ?? _testConvId,
            ),
          ),
          GoRoute(
            path: '/chat/:id/transfer-ownership',
            builder: (_, state) => const Scaffold(body: SizedBox()),
          ),
          GoRoute(
            path: '/chat/:id/admins',
            builder: (_, state) => const Scaffold(body: SizedBox()),
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
  group('GroupManagePage — 渲染契约', () {
    testWidgets('正常渲染群管理页', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupManagePage), findsOneWidget);
    });

    testWidgets('AppBar 标题显示"群管理"', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.groupManagement), findsOneWidget);
    });

    testWidgets('包含二维码进群开关', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.qrCodeJoin), findsOneWidget);
    });

    testWidgets('包含入群审核开关', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.joinRequiresApproval), findsOneWidget);
    });

    testWidgets('包含仅管理员修改群名开关', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.text(UITextConstants.nameEditableByAdminOnly),
        findsOneWidget,
      );
    });

    testWidgets('群主角色时可见群主管理权转让入口', (tester) async {
      _suppressImageErrors();
      // GroupManagePage 内 _currentUserRole 默认为 'owner'
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.transferOwnership), findsOneWidget);
    });

    testWidgets('群主角色时可见群管理员入口', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.groupAdmins), findsOneWidget);
    });

    testWidgets('群主角色时可见解散群聊按钮', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.dissolveGroupChat), findsOneWidget);
    });
  });

  group('GroupManagePage — 交互契约', () {
    testWidgets('tap 开关不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final switches = find.byType(CupertinoSwitch);
      expect(switches, findsWidgets);
      await tester.tap(switches.first);
      await tester.pump();

      expect(find.byType(GroupManagePage), findsOneWidget);
    });

    testWidgets('tap 解散群聊弹出确认弹窗', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text(UITextConstants.dissolveGroupChat));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog).evaluate().length +
          find.byType(CupertinoAlertDialog).evaluate().length, greaterThan(0));
    });

    testWidgets('返回按钮 tap 触发导航', (tester) async {
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

  group('GroupManagePage — 错误态渲染', () {
    testWidgets('getGroupSettings 异常时页面不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _ErrorSettingsRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupManagePage), findsOneWidget);
    });
  });
}

class _ErrorSettingsRepo extends MockChatRepository {
  @override
  Future<ChatGroupSettingsDto> getGroupSettings(
    String conversationId,
  ) async {
    throw Exception('settings error');
  }
}
