import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/chat_repository_facade.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_announcement_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_settings_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/group_admins_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/group_manage_page.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/transfer_ownership_page.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/group_home_provider.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

const _testConvId = 'fixture_conv_group';

ChatInteractionTelemetryTracker _telemetryTracker() =>
    ChatInteractionTelemetryTracker(
      telemetryReporter: RecordingAppTelemetryRecorder(),
    );

List<Override> _chatTestOverrides(ChatRepository repo) => [
  chatRepositoryCompositionProvider.overrideWithValue(repo),
  currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
];

/// 完整路由栈：settings → manage → transfer-ownership / admins
Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: _chatTestOverrides(repo),
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/$_testConvId/settings',
        routes: [
          GoRoute(
            path: '/chat/:id',
            builder: (_, _) => const Scaffold(body: SizedBox.shrink()),
            routes: [
              GoRoute(
                path: 'settings',
                builder: (_, state) => ChatSettingsPage(
                  conversationId: state.pathParameters['id'] ?? _testConvId,
                ),
                routes: [
                  GoRoute(
                    path: 'manage',
                    builder: (_, state) => GroupManagePage(
                      conversationId: state.pathParameters['id'] ?? _testConvId,
                      conversationDissolver: repo,
                    ),
                    routes: [
                      GoRoute(
                        path: 'transfer-ownership',
                        builder: (_, state) => TransferOwnershipPage(
                          conversationId:
                              state.pathParameters['id'] ?? _testConvId,
                          telemetryTracker: _telemetryTracker(),
                        ),
                      ),
                      GoRoute(
                        path: 'admins',
                        builder: (_, state) => GroupAdminsPage(
                          conversationId:
                              state.pathParameters['id'] ?? _testConvId,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              GoRoute(
                path: 'announcement',
                builder: (_, state) => ChatAnnouncementPage(
                  conversationId: state.pathParameters['id'] ?? _testConvId,
                ),
              ),
              GoRoute(
                path: 'add-members',
                builder: (_, _) => const Scaffold(body: SizedBox()),
              ),
            ],
          ),
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
  group('旅程 A — 设置页入口权限', () {
    testWidgets('J-A1: 群主 Provider state 验证（isOwner=true）且设置页存在', (
      tester,
    ) async {
      _suppressImageErrors();
      // 用 canonical fixture 验证当前用户为 owner。
      final container = ProviderContainer(
        overrides: _chatTestOverrides(MockChatRepository()),
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        conversationMembersProvider(_testConvId).notifier,
      );
      await notifier.load();

      final state = container.read(conversationMembersProvider(_testConvId));
      expect(state.isOwner, isTrue, reason: 'fixture_conv_group 的当前用户应为群主');
      expect(state.isAdminOrOwner, isTrue);

      // widget 层：渲染 ChatSettingsPage，验证页面存在（UI 分离测试见 widget test）
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(body: ChatSettingsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ChatSettingsPage), findsOneWidget);
    });

    testWidgets('J-A3: 普通成员不显示群管理入口', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _MemberRoleMockRepo()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ChatSettingsPage), findsOneWidget);
      expect(find.text(ChatText.groupManagement), findsNothing);
    });

    testWidgets('J-A4: 群主从设置页发布公告并返回权威新值', (tester) async {
      _suppressImageErrors();
      final repository = _OwnerRoleMockRepo();
      await tester.pumpWidget(_scopedApp(mock: repository));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text(ChatText.groupAnnouncement));
      await tester.pumpAndSettle();
      expect(find.byType(ChatAnnouncementPage), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      final container = ProviderScope.containerOf(
        tester.element(find.byType(ChatAnnouncementPage)),
      );
      expect(
        container.read(conversationMembersProvider(_testConvId)).isOwner,
        isTrue,
      );
      expect(container.read(groupHomeProvider(_testConvId)).hasValue, isTrue);
      expect(
        find.byKey(const ValueKey('chat_announcement_editor')),
        findsOneWidget,
      );

      await tester.enterText(
        find.byKey(const ValueKey('chat_announcement_editor')),
        '旅程公告：周日集合',
      );
      await tester.tap(
        find.byKey(const ValueKey('chat_announcement_publish_button')),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      await tester.tap(
        find.widgetWithText(
          CupertinoDialogAction,
          ChatText.groupAnnouncementPublish,
        ),
      );
      for (
        var attempt = 0;
        attempt < 20 && find.byType(ChatSettingsPage).evaluate().isEmpty;
        attempt += 1
      ) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      await tester.pump(const Duration(seconds: 1));

      final updatedGroup = await repository.getGroupHome(_testConvId);
      expect(updatedGroup.announcement, '旅程公告：周日集合');
      expect(find.byType(ChatSettingsPage), findsOneWidget);
      expect(find.text('旅程公告：周日集合'), findsOneWidget);
      await tester.pump(const Duration(seconds: 3));
    });
  });

  group('旅程 B — 群管理页元素验证', () {
    testWidgets('J-B1: GroupManagePage 仅展示真实群名治理开关', (tester) async {
      _suppressImageErrors();
      final repository = MockChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(repository),
          child: MaterialApp.router(
            routerConfig: GoRouter(
              initialLocation: '/chat/$_testConvId/settings/manage',
              routes: [
                GoRoute(
                  path: '/chat/:id/settings',
                  builder: (_, s) => ChatSettingsPage(
                    conversationId: s.pathParameters['id'] ?? _testConvId,
                  ),
                  routes: [
                    GoRoute(
                      path: 'manage',
                      builder: (_, s) => GroupManagePage(
                        conversationId: s.pathParameters['id'] ?? _testConvId,
                        conversationDissolver: repository,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.nameEditableByAdminOnly), findsOneWidget);
      expect(find.byType(CupertinoSwitch), findsOneWidget);
      expect(find.text('二维码进群'), findsNothing);
      expect(find.text('进群需要群主/群管理员确认'), findsNothing);
    });

    testWidgets('J-B2: ChatSettingsPage 不展示未落地隐私盾开关', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      await tester.scrollUntilVisible(
        find.text(ChatText.exitGroupChat),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      await tester.pump();

      expect(find.text('隐私屏障(禁截屏、禁转发)'), findsNothing);
      expect(find.byType(CupertinoSwitch), findsNWidgets(2));
    });

    testWidgets('J-B3: 群主可见群主管理权转让和群管理员入口', (tester) async {
      _suppressImageErrors();
      final repository = MockChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(repository),
          child: MaterialApp(
            home: Scaffold(
              body: GroupManagePage(
                conversationId: _testConvId,
                conversationDissolver: repository,
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.transferOwnership), findsOneWidget);
      expect(find.text(ChatText.groupAdmins), findsOneWidget);
    });

    testWidgets('J-B4: 群主可见解散群聊按钮', (tester) async {
      _suppressImageErrors();
      final repository = MockChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(repository),
          child: MaterialApp(
            home: Scaffold(
              body: GroupManagePage(
                conversationId: _testConvId,
                conversationDissolver: repository,
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.dissolveGroupChat), findsOneWidget);
    });
  });

  group('旅程 C — 群主转让完整旅程', () {
    testWidgets('J-C1: TransferOwnershipPage 页面标题正确', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(
              body: TransferOwnershipPage(
                conversationId: _testConvId,
                telemetryTracker: _telemetryTracker(),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.selectNewOwner), findsOneWidget);
    });

    testWidgets('J-C2: 转让页成员列表不含群主自身', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(
              body: TransferOwnershipPage(
                conversationId: _testConvId,
                telemetryTracker: _telemetryTracker(),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.text(chatDisplayNameFor(chatCurrentUserProfileId())),
        findsNothing,
      );
    });

    testWidgets('J-C3: 搜索框可见且可输入过滤', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(
              body: TransferOwnershipPage(
                conversationId: _testConvId,
                telemetryTracker: _telemetryTracker(),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final searchField = find.byType(CupertinoSearchTextField);
      expect(searchField, findsOneWidget);

      await tester.enterText(searchField, '契约同伴一');
      await tester.pump();
      expect(find.text('契约同伴一'), findsWidgets);
    });

    testWidgets('J-C4: 点击成员弹出确认弹窗', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(
              body: TransferOwnershipPage(
                conversationId: _testConvId,
                telemetryTracker: _telemetryTracker(),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // 点击第一个候选成员
      final memberItems = find.byType(CupertinoListTile);
      expect(memberItems, findsWidgets);
      await tester.tap(memberItems.first);
      await tester.pumpAndSettle();

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    });

    testWidgets('J-C5: 确认转让后 transferOwnership 被调用', (tester) async {
      _suppressImageErrors();
      final tracking = _TrackingChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(tracking),
          child: MaterialApp(
            home: Scaffold(
              body: TransferOwnershipPage(
                conversationId: _testConvId,
                telemetryTracker: _telemetryTracker(),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.byType(CupertinoListTile).first);
      await tester.pumpAndSettle();

      await tester.tap(find.text(FoundationText.confirm));
      await tester.pump(const Duration(milliseconds: 200));

      expect(tracking.transferCount, equals(1));
      expect(tracking.lastTransferIdempotencyKey, isNotEmpty);
    });

    testWidgets('J-C7: 转让后 Provider state 中当前用户变为 member', (tester) async {
      _suppressImageErrors();
      final container = ProviderContainer(
        overrides: _chatTestOverrides(MockChatRepository()),
      );
      addTearDown(container.dispose);

      // 触发加载
      final notifier = container.read(
        conversationMembersProvider(_testConvId).notifier,
      );
      await notifier.load();

      expect(
        container.read(conversationMembersProvider(_testConvId)).isOwner,
        isTrue,
      );

      await notifier.transferOwnership(
        'fixture_user_weekend_1',
        idempotencyKey: 'fixture_transfer_owner_1',
      );

      final state = container.read(conversationMembersProvider(_testConvId));
      expect(state.currentUserRole, equals('member'));
      expect(
        state.members
            .firstWhere((m) => m.userId == 'fixture_user_weekend_1')
            .role,
        equals('owner'),
      );
    });
  });

  group('旅程 D — 管理员设置完整旅程', () {
    testWidgets('J-D1: GroupAdminsPage 页面标题正确', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(body: GroupAdminsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.selectGroupMembers), findsOneWidget);
    });

    testWidgets('J-D2: GroupAdminsPage 列表不含群主', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(body: GroupAdminsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.text(chatDisplayNameFor(chatCurrentUserProfileId())),
        findsNothing,
      );
    });

    testWidgets('J-D4: 初始管理员显示管理员标签', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp(
            home: Scaffold(body: GroupAdminsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // canonical fixture 中 fixture_user_weekend_1 是初始管理员。
      expect(find.text(ChatText.admin), findsWidgets);
    });

    testWidgets('J-D6: 超过 3 人弹出限制提示', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(_AdminLimitMockRepo()),
          child: MaterialApp(
            home: Scaffold(body: GroupAdminsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      for (final name in const <String>['候选一', '候选二', '候选三']) {
        final candidate = find.ancestor(
          of: find.text(name),
          matching: find.byType(CupertinoButton),
        );
        expect(candidate, findsOneWidget);
        await tester.tap(candidate);
        await tester.pump();
      }
      await tester.pumpAndSettle();

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.text(ChatText.maxAdminsReached), findsOneWidget);
      await tester.tap(find.text(FoundationText.confirm));
      await tester.pumpAndSettle();
      expect(find.byType(CupertinoAlertDialog), findsNothing);
    });

    testWidgets('J-D7: 点击完成调用 updateGroupAdmins', (tester) async {
      _suppressImageErrors();
      final tracking = _TrackingChatRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(tracking),
          child: MaterialApp(
            home: Scaffold(body: GroupAdminsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // 初始管理员已选中，完成按钮应可用
      final doneBtn = find.textContaining(CommunityText.done);
      await tester.tap(doneBtn);
      await tester.pump(const Duration(milliseconds: 200));

      expect(tracking.updateAdminsCount, greaterThanOrEqualTo(1));
      expect(tracking.lastAdminsIdempotencyKey, isNotEmpty);
    });

    testWidgets('J-D9: updateGroupAdmins 后 Provider state 已更新', (tester) async {
      _suppressImageErrors();
      final container = ProviderContainer(
        overrides: _chatTestOverrides(MockChatRepository()),
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        conversationMembersProvider(_testConvId).notifier,
      );
      await notifier.load();

      await notifier.updateGroupAdmins([
        'fixture_user_weekend_2',
      ], idempotencyKey: 'fixture_update_admins_1');

      final state = container.read(conversationMembersProvider(_testConvId));
      expect(
        state.members
            .firstWhere((m) => m.userId == 'fixture_user_weekend_2')
            .role,
        equals('admin'),
      );
      expect(
        state.members
            .firstWhere((m) => m.userId == 'fixture_user_weekend_1')
            .role,
        equals('member'),
      );
      // 群主角色不变
      expect(
        state.members
            .firstWhere((m) => m.userId == chatCurrentUserProfileId())
            .role,
        equals('owner'),
      );
    });
  });

  group('旅程 E — 错误态与边界', () {
    testWidgets('J-E1: listMembers 失败时 GroupAdminsPage 不崩溃', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(_ErrorMembersRepo()),
          child: MaterialApp(
            home: Scaffold(body: GroupAdminsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupAdminsPage), findsOneWidget);
    });

    testWidgets('J-E2: transferOwnership 失败后 state 回滚', (tester) async {
      _suppressImageErrors();
      final container = ProviderContainer(
        overrides: _chatTestOverrides(MockChatRepository()),
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        conversationMembersProvider(_testConvId).notifier,
      );
      await notifier.load();

      final stateBefore = container.read(
        conversationMembersProvider(_testConvId),
      );
      expect(stateBefore.isOwner, isTrue);

      // 替换为失败 repo 并尝试转让
      final failContainer = ProviderContainer(
        overrides: _chatTestOverrides(_FailTransferRepo()),
      );
      addTearDown(failContainer.dispose);

      final failNotifier = failContainer.read(
        conversationMembersProvider(_testConvId).notifier,
      );
      await failNotifier.load();
      final previousState = failContainer.read(
        conversationMembersProvider(_testConvId),
      );

      try {
        await failNotifier.transferOwnership(
          'fixture_user_weekend_1',
          idempotencyKey: 'fixture_transfer_owner_failure',
        );
      } catch (_) {}

      final stateAfter = failContainer.read(
        conversationMembersProvider(_testConvId),
      );
      expect(stateAfter.currentUserRole, equals(previousState.currentUserRole));
    });

    testWidgets('J-E3: updateGroupAdmins 失败后 state 回滚', (tester) async {
      _suppressImageErrors();
      final container = ProviderContainer(
        overrides: _chatTestOverrides(_FailAdminsRepo()),
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        conversationMembersProvider(_testConvId).notifier,
      );
      await notifier.load();

      final stateBefore = container.read(
        conversationMembersProvider(_testConvId),
      );
      final adminsBefore = stateBefore.members
          .where((m) => m.role == 'admin')
          .map((m) => m.userId)
          .toList();

      try {
        await notifier.updateGroupAdmins([
          'user_999',
        ], idempotencyKey: 'fixture_update_admins_failure');
      } catch (_) {}

      final stateAfter = container.read(
        conversationMembersProvider(_testConvId),
      );
      final adminsAfter = stateAfter.members
          .where((m) => m.role == 'admin')
          .map((m) => m.userId)
          .toList();

      expect(adminsAfter, equals(adminsBefore));
    });

    testWidgets('J-E4: 空成员列表时 GroupAdminsPage 安全渲染', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(_EmptyMembersRepo()),
          child: MaterialApp(
            home: Scaffold(body: GroupAdminsPage(conversationId: _testConvId)),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(GroupAdminsPage), findsOneWidget);
      expect(find.byType(AppPageErrorState), findsOneWidget);
    });
  });
}

// ─── Mock 辅助类 ──────────────────────────────────────────────────────────────

/// 追踪型：验证方法调用次数和参数
class _TrackingChatRepository extends MockChatRepository {
  int transferCount = 0;
  String? lastNewOwnerId;
  String? lastTransferIdempotencyKey;
  int updateAdminsCount = 0;
  List<String>? lastAdminIds;
  String? lastAdminsIdempotencyKey;

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId, {
    String? idempotencyKey,
  }) async {
    transferCount++;
    lastNewOwnerId = newOwnerId;
    lastTransferIdempotencyKey = idempotencyKey;
    await super.transferOwnership(
      conversationId,
      newOwnerId,
      idempotencyKey: idempotencyKey,
    );
  }

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds, {
    String? idempotencyKey,
  }) async {
    updateAdminsCount++;
    lastAdminIds = adminIds;
    lastAdminsIdempotencyKey = idempotencyKey;
    await super.updateGroupAdmins(
      conversationId,
      adminIds,
      idempotencyKey: idempotencyKey,
    );
  }
}

/// 当前用户为普通成员（验证权限隔离）
class _MemberRoleMockRepo extends MockChatRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    return [
      ConversationMemberListRow(
        userId: chatCurrentUserProfileId(),
        userHandle: '',
        displayName: '我',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      ConversationMemberListRow(
        userId: 'user_002',
        userHandle: '',
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

class _OwnerRoleMockRepo extends MockChatRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
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
      ConversationMemberListRow(
        userId: 'user_002',
        userHandle: '',
        displayName: '普通成员',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
    ];
  }
}

class _AdminLimitMockRepo extends MockChatRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    ConversationMemberListRow member(
      String userId,
      String displayName,
      String role, {
      bool isCurrentUser = false,
    }) {
      return ConversationMemberListRow(
        userId: userId,
        userHandle: '',
        displayName: displayName,
        avatarUrl: '',
        role: role,
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: isCurrentUser,
      );
    }

    return <ConversationMemberListRow>[
      member(chatCurrentUserProfileId(), '当前群主', 'owner', isCurrentUser: true),
      member('initial_admin', '已有管理员', 'admin'),
      member('candidate_1', '候选一', 'member'),
      member('candidate_2', '候选二', 'member'),
      member('candidate_3', '候选三', 'member'),
    ];
  }
}

/// listMembers 抛异常
class _ErrorMembersRepo extends MockChatRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    throw Exception('network error');
  }
}

/// transferOwnership 抛异常（验证乐观回滚）
class _FailTransferRepo extends MockChatRepository {
  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId, {
    String? idempotencyKey,
  }) async {
    throw Exception('transfer failed');
  }
}

/// updateGroupAdmins 抛异常（验证乐观回滚）
class _FailAdminsRepo extends MockChatRepository {
  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds, {
    String? idempotencyKey,
  }) async {
    throw Exception('update admins failed');
  }
}

/// 返回空成员列表
class _EmptyMembersRepo extends MockChatRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    return [];
  }
}

// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-002
// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-004
