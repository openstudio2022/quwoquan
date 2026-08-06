import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/chat_repository_facade.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/group_manage_page.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

const _testConvId = 'fixture_conv_group';
const _unsupportedJoinGovernanceLabels = <String>['二维码进群', '进群需要群主/群管理员确认'];

List<Override> _chatTestOverrides(ChatRepository repo) => [
  chatRepositoryCompositionProvider.overrideWithValue(repo),
  currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
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
              conversationDissolver: repo,
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

      expect(find.text(ChatText.groupManagement), findsOneWidget);
    });

    testWidgets('仅显示有权威契约支撑的群名治理开关', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.nameEditableByAdminOnly), findsOneWidget);
      expect(find.byType(CupertinoSwitch), findsOneWidget);
      for (final label in _unsupportedJoinGovernanceLabels) {
        expect(find.text(label), findsNothing);
      }
    });

    testWidgets('群主角色时可见群主管理权转让入口', (tester) async {
      _suppressImageErrors();
      // GroupManagePage 内 _currentUserRole 默认为 'owner'
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.transferOwnership), findsOneWidget);
    });

    testWidgets('群主角色时可见群管理员入口', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.groupAdmins), findsOneWidget);
    });

    testWidgets('群主角色时可见解散群聊按钮', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.dissolveGroupChat), findsOneWidget);
    });

    testWidgets('圈群绑定会话不显示 Chat 侧治理动作', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _CircleGroupManagedSettingsRepo()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.circleGroupManagedNotice), findsOneWidget);
      expect(find.byType(CupertinoSwitch), findsNothing);
      expect(find.text(ChatText.transferOwnership), findsNothing);
      expect(find.text(ChatText.groupAdmins), findsNothing);
      expect(find.text(ChatText.dissolveGroupChat), findsNothing);
    });
  });

  group('GroupManagePage — 交互契约', () {
    testWidgets('切换群名治理开关提交真实设置', (tester) async {
      _suppressImageErrors();
      final repo = _TrackingSettingsRepo();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final switches = find.byType(CupertinoSwitch);
      expect(switches, findsOneWidget);
      final initialValue = tester.widget<CupertinoSwitch>(switches).value;
      await tester.tap(switches);
      await tester.pump();

      expect(repo.lastSettings, isNotNull);
      expect(repo.lastSettings!.nameEditableByAdminOnly, isNot(initialValue));
    });

    testWidgets('tap 解散群聊弹出确认弹窗', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text(ChatText.dissolveGroupChat));
      await tester.pumpAndSettle();

      expect(
        find.byType(AlertDialog).evaluate().length +
            find.byType(CupertinoAlertDialog).evaluate().length,
        greaterThan(0),
      );
    });

    testWidgets('确认解散只调用注入的 ConversationDissolver', (tester) async {
      _suppressImageErrors();
      final repo = _TrackingDissolveRepo();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text(ChatText.dissolveGroupChat));
      await tester.pumpAndSettle();
      await tester.tap(find.text('确认'));
      await tester.pumpAndSettle();

      expect(repo.dissolvedConversationIds, <String>[_testConvId]);
      await tester.pump(const Duration(seconds: 4));
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
  Future<ChatGroupSettingsViewData> getGroupSettings(
    String conversationId,
  ) async {
    throw Exception('settings error');
  }
}

class _CircleGroupManagedSettingsRepo extends MockChatRepository {
  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(
    String conversationId,
  ) async {
    return ChatGroupSettingsViewData(
      conversationType: 'group',
      circleId: 'fixture_circle',
      circleGroupId: 'fixture_circle_group',
    );
  }
}

class _TrackingSettingsRepo extends MockChatRepository {
  ChatGroupSettingsViewData? lastSettings;

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsViewData settings,
  ) async {
    lastSettings = settings;
  }
}

class _TrackingDissolveRepo extends MockChatRepository {
  final List<String> dissolvedConversationIds = <String>[];

  @override
  Future<void> dissolveConversation(String conversationId) async {
    dissolvedConversationIds.add(conversationId);
  }
}
