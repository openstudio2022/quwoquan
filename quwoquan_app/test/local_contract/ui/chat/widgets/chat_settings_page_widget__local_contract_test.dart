import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/components/rtc/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_settings_page.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_permission_guard.dart';
import '../../../../support/fixtures/chat/chat_mock_seed_refs.dart';

List<Override> _chatTestOverrides(ChatRepository repo) => [
  chatRepositoryCompositionProvider.overrideWithValue(repo),
  currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
];

Widget _scopedApp({
  ChatRepository? mock,
  List<Override> overrides = const <Override>[],
}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: <Override>[..._chatTestOverrides(repo), ...overrides],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/fixture_conv_group/settings',
        routes: [
          GoRoute(
            path: '/chat/:id/settings',
            builder: (_, state) => Scaffold(
              body: ChatSettingsPage(
                conversationId:
                    state.pathParameters['id'] ?? 'fixture_conv_group',
              ),
            ),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
          GoRoute(
            path: '/chat/:id/manage',
            builder: (_, _) => const SizedBox(),
          ),
          GoRoute(
            path: '/chat/:id/add-members',
            builder: (_, _) => const SizedBox(),
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
  group('ChatSettingsPage — 渲染契约', () {
    testWidgets('正常渲染设置页', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ChatSettingsPage), findsOneWidget);
      expect(find.text(ChatText.groupCapabilityAlbum), findsOneWidget);
      expect(find.text(ChatText.groupCapabilityFile), findsOneWidget);
      expect(find.text(ChatText.groupCapabilityActivity), findsNothing);
      expect(find.text(ChatText.groupCapabilityMembers), findsNothing);
      expect(find.text('新同学_260622_6698692'), findsOneWidget);
      expect(find.text('契约同伴一'), findsOneWidget);
      expect(find.text('${ChatText.chatInfoTitle}(3)'), findsOneWidget);
    });

    testWidgets('摄影爱好者圈子标题人数与成员网格一致', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(MockChatRepository()),
          child: MaterialApp.router(
            routerConfig: GoRouter(
              initialLocation: '/chat/fixture_conv_photo_group/settings',
              routes: [
                GoRoute(
                  path: '/chat/:id/settings',
                  builder: (_, state) => Scaffold(
                    body: ChatSettingsPage(
                      conversationId:
                          state.pathParameters['id'] ??
                          'fixture_conv_photo_group',
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text('${ChatText.chatInfoTitle}(3)'), findsOneWidget);
      expect(find.text('契约摄影师'), findsOneWidget);
      expect(find.text('契约好友'), findsOneWidget);
    });

    testWidgets('退出群聊使用 SettingsInsetCenteredActionRow', (tester) async {
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

      expect(find.byType(SettingsInsetCenteredActionRow), findsOneWidget);
      expect(find.text(ChatText.exitGroupChat), findsOneWidget);
    });

    testWidgets('聊天设置页不显示未落地隐私盾开关', (tester) async {
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

    testWidgets('成员数不超过折叠容量时不显示更多成员', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.moreMembers), findsNothing);
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
    testWidgets('fixture 群主 Provider state 正确（isOwner=true）', (tester) async {
      // 用 ProviderContainer 直接验证 Provider state（避免 widget 时序问题）
      final container = ProviderContainer(
        overrides: _chatTestOverrides(MockChatRepository()),
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        conversationMembersProvider('fixture_conv_group').notifier,
      );
      await notifier.load();

      final state = container.read(
        conversationMembersProvider('fixture_conv_group'),
      );
      expect(state.isOwner, isTrue, reason: 'fixture_conv_group 当前用户应为群主');
      expect(state.isAdminOrOwner, isTrue);
      expect(state.members.any((m) => m.isCurrentUser), isTrue);
    });

    testWidgets('普通成员角色时不显示群管理入口', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _MemberRoleChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.groupManagement), findsNothing);
    });

    testWidgets('仅管理员可改群名时普通成员收到真实权限提示', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        _scopedApp(mock: _MemberRoleAdminOnlyNameRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      await tester.scrollUntilVisible(
        find.text(ChatText.groupName),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );

      await tester.tap(find.text(ChatText.groupName));
      await tester.pumpAndSettle();

      expect(find.text(ChatText.groupNameAdminOnly), findsOneWidget);
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

    testWidgets('群设置语音入口复用 participant picker 并携带 conversation context', (
      tester,
    ) async {
      _suppressImageErrors();
      final pickerIntents = <RtcCallEntryIntent>[];
      await tester.pumpWidget(
        _scopedApp(
          overrides: <Override>[
            rtcCallEntryPresenterProvider.overrideWithValue(
              RtcCallEntryPresenter(
                permissionRequest: (_, _) async =>
                    CallPermissionOutcome.granted,
                participantPicker: (_, intent) async {
                  pickerIntents.add(intent);
                  return null;
                },
              ),
            ),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(find.text(UITextConstants.callGroupVoice));
      await tester.pump();

      expect(pickerIntents, hasLength(1));
      expect(
        pickerIntents.single.contextKind,
        RtcCallEntryContextKind.conversation,
      );
      expect(pickerIntents.single.conversationId, 'fixture_conv_group');
      expect(pickerIntents.single.participantCount, 3);
      expect(pickerIntents.single.defaultSelectAll, isTrue);
    });

    testWidgets('紧凑宽度下成员头像网格不发生纵向溢出', (tester) async {
      final original = FlutterError.onError;
      final overflowErrors = <FlutterErrorDetails>[];
      FlutterError.onError = (FlutterErrorDetails details) {
        final message = details.exceptionAsString();
        if (message.contains('RenderFlex') && message.contains('overflow')) {
          overflowErrors.add(details);
          return;
        }
        if (message.contains('HTTP request failed') ||
            message.contains('NetworkImageLoadException')) {
          return;
        }
        original?.call(details);
      };
      addTearDown(() {
        FlutterError.onError = original;
      });

      await tester.binding.setSurfaceSize(const Size(320, 640));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.byType(ChatSettingsPage), findsOneWidget);
      expect(overflowErrors, isEmpty);
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

  group('ChatSettingsPage — 群治理入口契约', () {
    testWidgets('群主可见移出成员入口并在移出模式暴露可移出徽标', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final removeEntry = find.byKey(
        const ValueKey('chat_settings_remove_member_entry'),
      );
      expect(removeEntry, findsOneWidget, reason: '群主应看到「−」移出成员入口');

      await tester.tap(removeEntry);
      await tester.pump();

      // 移出模式下：非当前用户的普通成员出现可移出徽标；当前用户（群主）没有。
      expect(
        find.byKey(
          const ValueKey('chat_settings_remove_badge_fixture_user_weekend_1'),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(
          const ValueKey('chat_settings_remove_badge_fixture_user_current'),
        ),
        findsNothing,
      );
    });

    testWidgets('移出模式点击成员弹确认并经 Repository 移出', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final repo = _RecordingChatRepository();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(
        find.byKey(const ValueKey('chat_settings_remove_member_entry')),
      );
      await tester.pump();

      await tester.tap(find.text('契约同伴一'));
      await tester.pumpAndSettle();
      expect(find.text(ChatText.removeMemberEntry), findsOneWidget);

      await tester.tap(find.text(UITextConstants.confirm));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(repo.removedUserIds, contains('fixture_user_weekend_1'));

      // 消化移出成功 toast 的自动消失 timer，避免残留 pending timer。
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('普通成员不可见移出成员入口', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(mock: _MemberRoleChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.byKey(const ValueKey('chat_settings_remove_member_entry')),
        findsNothing,
      );
    });

    testWidgets('退出群聊经 LeaveConversation 而非 removeMember(self)', (
      tester,
    ) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final repo = _RecordingChatRepository();
      await tester.pumpWidget(_scopedApp(mock: repo));
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
      await tester.tap(find.text(ChatText.exitGroupChat));
      await tester.pumpAndSettle();
      await tester.tap(find.text(ChatText.exitGroupChat).last);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(repo.leaveConversationCalls, contains('fixture_conv_group'));
      expect(
        repo.removedUserIds,
        isNot(contains(chatCurrentUserProfileId())),
        reason: '退群不得复用治理动作 removeMember(self)',
      );
    });
  });
}

/// 记录治理动作调用，验证页面动作与 Repository 契约绑定。
class _RecordingChatRepository extends MockChatRepository {
  final List<String> removedUserIds = <String>[];
  final List<String> leaveConversationCalls = <String>[];

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    removedUserIds.add(userId);
    await super.removeMember(conversationId: conversationId, userId: userId);
  }

  @override
  Future<void> leaveConversation(String conversationId) async {
    leaveConversationCalls.add(conversationId);
    await super.leaveConversation(conversationId);
  }
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
    return [
      ChatConversationMemberDto(
        userId: 'fixture_user_current',
        displayName: '我',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      ChatConversationMemberDto(
        userId: 'fixture_user_friend',
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

class _MemberRoleAdminOnlyNameRepository extends _MemberRoleChatRepository {
  @override
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId) async {
    return ChatGroupSettingsDto(
      nameEditableByAdminOnly: true,
      conversationType: 'group',
    );
  }
}
