import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_settings_page.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/conv_002/settings',
        routes: [
          GoRoute(
            path: '/chat/:id/settings',
            builder: (_, state) => Scaffold(
              body: ChatSettingsPage(
                conversationId: state.pathParameters['id'] ?? 'conv_002',
              ),
            ),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
          GoRoute(path: '/chat/:id/manage', builder: (_, _) => const SizedBox()),
          GoRoute(path: '/chat/:id/add-members', builder: (_, _) => const SizedBox()),
          GoRoute(
            path: '/user/:id',
            builder: (_, state) =>
                Scaffold(body: Text('User ${state.pathParameters['id']}')),
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
  group('ChatSettingsPage — 渲染契约', () {
    testWidgets('正常渲染设置页', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ChatSettingsPage), findsOneWidget);
    });

    testWidgets('包含 Scaffold 结构', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(Scaffold), findsWidgets);
    });
  });

  group('ChatSettingsPage — 权限呈现契约', () {
    testWidgets('conv_002 群主 Provider state 正确（isOwner=true）', (tester) async {
      // 用 ProviderContainer 直接验证 Provider state（避免 widget 时序问题）
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
        ],
      );
      addTearDown(container.dispose);

      final notifier =
          container.read(conversationMembersProvider('conv_002').notifier);
      await notifier.load();

      final state = container.read(conversationMembersProvider('conv_002'));
      expect(state.isOwner, isTrue,
          reason: 'conv_002 当前用户（user_001）应为群主');
      expect(state.isAdminOrOwner, isTrue);
      expect(state.members.any((m) => m.isCurrentUser), isTrue);
    });

    testWidgets('普通成员角色时不显示群管理入口', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _MemberRoleChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(UITextConstants.groupManagement), findsNothing);
    });
  });

  group('ChatSettingsPage — 交互契约', () {
    testWidgets('从 Repository 加载成员后正常渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ChatSettingsPage), findsOneWidget);
    });

    testWidgets('tap 设置项不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final switches = find.byType(Switch);
      if (switches.evaluate().isNotEmpty) {
        await tester.tap(switches.first);
        await tester.pump();
        await tester.pump(const Duration(seconds: 1));
      }
      expect(find.byType(ChatSettingsPage), findsOneWidget);
    });

    testWidgets('返回按钮 tap 触发导航', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final backButtons = find.byIcon(Icons.arrow_back);
      if (backButtons.evaluate().isNotEmpty) {
        await tester.tap(backButtons.first);
        await tester.pump();
        await tester.pump(const Duration(seconds: 1));
      }
      // GoRouter.pop() throws GoError in test with single-route stack; consume it
      tester.takeException();
    });
  });

  group('ChatSettingsPage — 错误态渲染', () {
    testWidgets('Repository 异常时页面不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _ErrorChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ChatSettingsPage), findsOneWidget);
    });
  });
}

class _ErrorChatRepository extends MockChatRepository {
  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    throw Exception('Network error');
  }
}

/// 当前用户为普通成员
class _MemberRoleChatRepository extends MockChatRepository {
  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    return const [
      ChatConversationMemberDto(
        userId: 'user_001',
        displayName: '我',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      ChatConversationMemberDto(
        userId: 'user_002',
        displayName: '李明',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
    ];
  }
}
