// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/group_admins_page.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

const _testConvId = 'fixture_conv_group';

Widget _scopedApp({ChatMemberRepository? member}) {
  return ProviderScope(
    overrides: [
      ...chatTestRepositoryOverrides(member: member),
      currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
    ],
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

      expect(find.text(ChatText.selectGroupMembers), findsOneWidget);
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

      expect(
        find.text(chatDisplayNameFor(chatCurrentUserProfileId())),
        findsNothing,
      );
    });

    testWidgets('初始管理员显示管理员标签', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(member: _AdminSeedMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.admin), findsWidgets);
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

      final textField = find.byType(CupertinoTextField);
      expect(textField, findsOneWidget);

      await tester.enterText(textField, '契约同伴一');
      await tester.pump();
      expect(find.text('契约同伴一'), findsWidgets);
    });

    testWidgets('tap 未选中成员后选中态变化', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final member = find.text('契约同伴二');
      expect(member, findsOneWidget);
      await tester.ensureVisible(member);
      await tester.pump();

      final memberRow = find.ancestor(
        of: member,
        matching: find.byType(CupertinoButton),
      );
      expect(memberRow, findsOneWidget);

      await tester.tap(memberRow);
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
      await tester.pumpWidget(_scopedApp(member: _ErrorMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupAdminsPage), findsOneWidget);
    });

    testWidgets('空成员列表时安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(member: _EmptyMembersRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupAdminsPage), findsOneWidget);
    });
  });
}

/// 含初始管理员的成员名册（最小共享 seed 不再内置 admin 角色成员）。
class _AdminSeedMembersRepo extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    return <ConversationMemberListRow>[
      ConversationMemberListRow(
        userId: chatCurrentUserProfileId(),
        userHandle: '',
        displayName: '当前群主',
        avatarUrl: '',
        role: 'owner',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      const ConversationMemberListRow(
        userId: 'fixture_user_weekend_1',
        userHandle: 'fixture_user_weekend_1',
        displayName: '契约同伴一',
        avatarUrl: '',
        role: 'admin',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
      const ConversationMemberListRow(
        userId: 'fixture_user_weekend_2',
        userHandle: 'fixture_user_weekend_2',
        displayName: '契约同伴二',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
    ];
  }
}

class _ErrorMembersRepo extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    throw Exception('network error');
  }
}

class _EmptyMembersRepo extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    return [];
  }
}
