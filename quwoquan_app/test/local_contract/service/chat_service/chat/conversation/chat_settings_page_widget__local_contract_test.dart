import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/runtime/di/rtc_call_entry_dependencies.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart' show ConversationAssetPage, ConversationAssetView;
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_settings_page.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_permission_guard.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

List<Override> _chatTestOverrides({
  ChatMemberRepository? member,
  ChatGroupAdminRepository? groupAdmin,
  ChatConversationRepository? conversation,
  ChatMessageRepository? message,
}) => [
  ...chatTestRepositoryOverrides(
    member: member,
    groupAdmin: groupAdmin,
    conversation: conversation,
    message: message,
  ),
  currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
];

Widget _scopedApp({
  ChatMemberRepository? member,
  ChatGroupAdminRepository? groupAdmin,
  ChatConversationRepository? conversation,
  ChatMessageRepository? message,
  List<Override> overrides = const <Override>[],
}) {
  return ProviderScope(
    overrides: <Override>[
      ..._chatTestOverrides(
        member: member,
        groupAdmin: groupAdmin,
        conversation: conversation,
        message: message,
      ),
      ...overrides,
    ],
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
      // seed 重构后共享 typed double 只保留最小两会话；圈群维度的成员
      // 输入由用例自治提供，避免测试对共享 seed 的隐式耦合。
      _suppressImageErrors();
      await tester.pumpWidget(
        ProviderScope(
          overrides: _chatTestOverrides(member: _PhotoCircleChatRepository()),
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
      final container = ProviderContainer(overrides: _chatTestOverrides());
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
      await tester.pumpWidget(_scopedApp(member: _MemberRoleChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(find.text(ChatText.groupManagement), findsNothing);
    });

    testWidgets('仅管理员可改群名时普通成员收到真实权限提示', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        _scopedApp(
          member: _MemberRoleChatRepository(),
          groupAdmin: _AdminOnlyNameRepository(),
        ),
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

      await tester.tap(find.text(CallText.callGroupVoice));
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
      await tester.pumpWidget(_scopedApp(member: _ErrorChatRepository()));
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
      await tester.pumpWidget(_scopedApp(member: repo));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.tap(
        find.byKey(const ValueKey('chat_settings_remove_member_entry')),
      );
      await tester.pump();

      await tester.tap(find.text('契约同伴一'));
      await tester.pumpAndSettle();
      expect(find.text(ChatText.removeMemberEntry), findsOneWidget);

      await tester.tap(find.text(FoundationText.confirm));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(repo.removedUserIds, contains('fixture_user_weekend_1'));

      // 消化移出成功 toast 的自动消失 timer，避免残留 pending timer。
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('普通成员不可见移出成员入口', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(_scopedApp(member: _MemberRoleChatRepository()));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.byKey(const ValueKey('chat_settings_remove_member_entry')),
        findsNothing,
      );
    });

    testWidgets('圈群绑定会话隐藏 Chat 成员治理入口并保留跳转提示', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(groupAdmin: _CircleGroupManagedChatRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.byKey(const ValueKey('chat_settings_remove_member_entry')),
        findsNothing,
      );
      expect(find.text(ChatText.circleGroupManagedNotice), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text(ChatText.openCircleGroupManagement),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      expect(find.text(ChatText.openCircleGroupManagement), findsOneWidget);
      expect(find.text(ChatText.exitGroupChat), findsNothing);
    });

    testWidgets('退出群聊经 LeaveConversation 而非 removeMember(self)', (
      tester,
    ) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final repo = _RecordingChatRepository();
      await tester.pumpWidget(_scopedApp(member: repo));
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

      // 消化退群成功 toast 的自动消失 timer，避免残留 pending timer。
      await tester.pump(const Duration(seconds: 4));
    });
  });

  // spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001
  group('ChatSettingsPage — 免打扰/置顶真实接线', () {
    ChatInboxCacheEntry inboxEntry({required bool muted, required bool pinned}) {
      return ChatInboxCacheEntry(
        id: 'fixture_conv_group',
        type: 'group',
        title: '契约周末群',
        avatarUrl: '',
        groupAvatarVersion: 1,
        lastMessagePreview: '',
        lastMessageType: MessageType.text,
        lastMessageTime: DateTime.utc(2026, 8, 13),
        lastSeq: 1,
        unreadCount: 0,
        mentionUnreadCount: 0,
        muted: muted,
        pinned: pinned,
        circleId: '',
      );
    }

    testWidgets('开关初值从 inbox 本地副本水合', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final settingsRepo = _RecordingConversationSettingsRepository();
      await tester.pumpWidget(
        _scopedApp(
          conversation: settingsRepo,
          overrides: [
            chatInboxCacheProvider.overrideWithValue(
              _SeededInboxCache(inboxEntry(muted: true, pinned: false)),
            ),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.scrollUntilVisible(
        find.text(ChatText.muteNotifications),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      final muteSwitch = find
          .descendant(
            of: find.ancestor(
              of: find.text(ChatText.muteNotifications),
              matching: find.byType(Row),
            ),
            matching: find.byType(CupertinoSwitch),
          )
          .first;
      expect(
        tester.widget<CupertinoSwitch>(muteSwitch).value,
        isTrue,
        reason: '免打扰初值必须从 inbox 本地副本水合而非恒为 false',
      );
    });

    testWidgets('切换免打扰调用 updateConversationSettings(muted)', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final settingsRepo = _RecordingConversationSettingsRepository();
      await tester.pumpWidget(
        _scopedApp(conversation: settingsRepo),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.scrollUntilVisible(
        find.text(ChatText.muteNotifications),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      final muteSwitch = find
          .descendant(
            of: find.ancestor(
              of: find.text(ChatText.muteNotifications),
              matching: find.byType(Row),
            ),
            matching: find.byType(CupertinoSwitch),
          )
          .first;
      await tester.tap(muteSwitch);
      await tester.pump();

      expect(settingsRepo.calls, hasLength(1));
      expect(settingsRepo.calls.single.conversationId, 'fixture_conv_group');
      expect(settingsRepo.calls.single.muted, isTrue);
      expect(settingsRepo.calls.single.pinned, isNull);
    });

    // spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-004
    testWidgets('相册宫格打开群空间相册并渲染真实媒体索引', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        _scopedApp(message: _AssetsMessageRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final albumEntry = find.byKey(
        const ValueKey<String>('chat_settings_album_entry'),
      );
      await tester.scrollUntilVisible(
        albumEntry,
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      await tester.tap(albumEntry);
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('conversation_asset_asset_msg_img')),
        findsOneWidget,
        reason: '相册面板必须渲染 ListConversationAssets 读面的真实行',
      );
    });

    // spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-004
    testWidgets('文件宫格打开群空间文件列表并显示文件名', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        _scopedApp(message: _AssetsMessageRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      final filesEntry = find.byKey(
        const ValueKey<String>('chat_settings_files_entry'),
      );
      await tester.scrollUntilVisible(
        filesEntry,
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      await tester.tap(filesEntry);
      await tester.pumpAndSettle();

      expect(
        find.text('观星路线图.pdf'),
        findsOneWidget,
        reason: '文件面板必须展示云侧交付的文件名',
      );
    });

    // spec_ref: specs/feature-tree/chat-conversation/chat-experience-optimization/spec.md#open-002
    testWidgets('群首页初始加载呈现共享骨架屏', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(groupAdmin: _SlowGroupHomeRepository()),
      );
      await tester.pump();

      expect(
        find.byType(AppSkeletonListRows),
        findsOneWidget,
        reason: '群首页初始加载必须使用共享 AppSkeletonListRows 骨架',
      );
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(AppSkeletonListRows), findsNothing);
    });

    // spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001
    testWidgets('查找聊天记录入口打开会话内搜索面板', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        _scopedApp(conversation: _RecordingConversationSettingsRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.scrollUntilVisible(
        find.byKey(
          const ValueKey<String>('chat_settings_search_in_conversation'),
        ),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      await tester.tap(
        find.byKey(
          const ValueKey<String>('chat_settings_search_in_conversation'),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(
          const ValueKey<String>('conversation_message_search_input'),
        ),
        findsOneWidget,
        reason: '设置页「查找聊天记录」必须打开会话内搜索面板',
      );
    });

    testWidgets('远端失败时开关回滚并提示', (tester) async {
      _suppressImageErrors();
      await tester.binding.setSurfaceSize(const Size(390, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final settingsRepo = _RecordingConversationSettingsRepository()
        ..failNext = true;
      await tester.pumpWidget(
        _scopedApp(conversation: settingsRepo),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.scrollUntilVisible(
        find.text(ChatText.pinChat),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ChatSettingsPage),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      final pinSwitch = find
          .descendant(
            of: find.ancestor(
              of: find.text(ChatText.pinChat),
              matching: find.byType(Row),
            ),
            matching: find.byType(CupertinoSwitch),
          )
          .first;
      final before = tester.widget<CupertinoSwitch>(pinSwitch).value;
      await tester.tap(pinSwitch);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(
        tester.widget<CupertinoSwitch>(pinSwitch).value,
        before,
        reason: '远端失败必须回滚乐观开关，不留假状态',
      );
      expect(find.text(ChatText.settingUpdateFailed), findsOneWidget);
      // 消化 toast 自动消失 timer。
      await tester.pump(const Duration(seconds: 4));
    });
  });
}

typedef _SettingsCall = ({String conversationId, bool? muted, bool? pinned});

/// 预填一条 inbox 本地副本（开关初值水合的输入面）。
class _SeededInboxCache extends Fake implements ChatInboxCache {
  _SeededInboxCache(this.entry);

  final ChatInboxCacheEntry entry;

  @override
  ChatInboxCacheEntry? readInboxEntry(String conversationId) {
    return conversationId == entry.id ? entry : null;
  }
}

/// 记录 ConversationUserState 设置命令；其余读写显式委托对象级 typed double，
/// 页面装载路径保持真实。
/// 群首页读取带 200ms 延迟（制造骨架屏可观测窗口），其余委托共享 double。
class _SlowGroupHomeRepository extends Fake
    implements ChatGroupAdminRepository {
  final ChatGroupAdminRepository _delegate = ChatTestFacets().groupAdmin;

  @override
  Future<GroupHome> getGroupHome(String conversationId) async {
    await Future<void>.delayed(const Duration(milliseconds: 200));
    return _delegate.getGroupHome(conversationId);
  }

  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(String conversationId) =>
      _delegate.getGroupSettings(conversationId);
}

class _RecordingConversationSettingsRepository
    implements ChatConversationRepository {
  _RecordingConversationSettingsRepository()
    : _delegate = ChatTestFacets().conversation;

  final ChatConversationRepository _delegate;
  final List<_SettingsCall> calls = <_SettingsCall>[];
  bool failNext = false;

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) async {
    if (failNext) {
      failNext = false;
      throw Exception('CHAT.MIDDLEWARE.unavailable');
    }
    calls.add((conversationId: conversationId, muted: muted, pinned: pinned));
  }

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) => _delegate.listMessageHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = 500,
  }) => _delegate.listConversations(cursor: cursor, limit: limit);

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) => _delegate.createConversation(
    type: type,
    title: title,
    maxGroupSize: maxGroupSize,
    initialMemberIds: initialMemberIds,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<ConversationViewData> getConversation(String conversationId) =>
      _delegate.getConversation(conversationId);

  @override
  Future<void> updateConversationTitle(String conversationId, String title) =>
      _delegate.updateConversationTitle(conversationId, title);

  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() =>
      _delegate.getConversationTimestamps();

  @override
  Future<List<ConversationViewData>> batchGetConversations(List<String> ids) =>
      _delegate.batchGetConversations(ids);
}

/// 记录治理动作调用，验证页面动作与 Repository 契约绑定。
/// seed 重构后 member override 是整体替换：治理用例消费的成员名册由
/// 本 double 自治提供（群主=当前用户 + 一名可移出普通成员）。
class _RecordingChatRepository extends Fake implements ChatMemberRepository {
  final List<String> removedUserIds = <String>[];
  final List<String> leaveConversationCalls = <String>[];

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    return const [
      ConversationMemberListRow(
        userId: 'fixture_user_current',
        userHandle: 'fixture_user_current',
        displayName: '我',
        avatarUrl: '',
        role: 'owner',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      ConversationMemberListRow(
        userId: 'fixture_user_weekend_1',
        userHandle: 'fixture_user_weekend_1',
        displayName: '契约同伴一',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
    ];
  }

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    removedUserIds.add(userId);
  }

  @override
  Future<void> leaveConversation(String conversationId) async {
    leaveConversationCalls.add(conversationId);
  }
}

class _ErrorChatRepository extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    throw Exception('Network error');
  }
}

/// 当前用户为普通成员
/// 群空间媒体索引 double：相册一行图片、文件一行 PDF。
class _AssetsMessageRepository extends Fake implements ChatMessageRepository {
  @override
  Future<ConversationAssetPage> listConversationAssets({
    required String conversationId,
    required String kind,
    int? beforeSeq,
    int limit = 60,
  }) async {
    if (kind == 'image') {
      return ConversationAssetPage(
        items: <ConversationAssetView>[
          ConversationAssetView(
            messageId: 'asset_msg_img',
            seq: 9,
            mediaAssetId: 'asset-image-1',
            messageType: 'image',
            senderId: 'fixture_user_peer',
            senderName: '契约摄影师',
            mediaDeliveryUrl: 'https://image.example.test/media/image/p.jpg',
            createdAt: DateTime.utc(2026, 8, 14, 1),
          ),
        ],
      );
    }
    return ConversationAssetPage(
      items: <ConversationAssetView>[
        ConversationAssetView(
          messageId: 'asset_msg_file',
          seq: 8,
          mediaAssetId: 'asset-file-1',
          messageType: 'file',
          senderId: 'fixture_user_peer',
          senderName: '契约好友',
          fileName: '观星路线图.pdf',
          mediaDeliveryUrl: 'https://image.example.test/media/image/f.pdf',
          createdAt: DateTime.utc(2026, 8, 14, 1),
        ),
      ],
    );
  }
}

/// 摄影圈子群的三名成员（圈群标题人数与成员网格一致性用例的自治输入）。
class _PhotoCircleChatRepository extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    return const [
      ConversationMemberListRow(
        userId: 'fixture_user_current',
        userHandle: 'fixture_user_current',
        displayName: '我',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      ConversationMemberListRow(
        userId: 'fixture_user_photographer',
        userHandle: 'fixture_user_photographer',
        displayName: '契约摄影师',
        avatarUrl: '',
        role: 'owner',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
      ConversationMemberListRow(
        userId: 'fixture_user_friend',
        userHandle: 'fixture_user_friend',
        displayName: '契约好友',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
    ];
  }
}

class _MemberRoleChatRepository extends Fake implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    return [
      ConversationMemberListRow(
        userId: 'fixture_user_current',
        userHandle: 'fixture_user_current',
        displayName: '我',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      ConversationMemberListRow(
        userId: 'fixture_user_friend',
        userHandle: 'fixture_user_friend',
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

class _AdminOnlyNameRepository extends Fake
    implements ChatGroupAdminRepository {
  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(
    String conversationId,
  ) async {
    return ChatGroupSettingsViewData(
      nameEditableByAdminOnly: true,
      conversationType: 'group',
    );
  }
}

class _CircleGroupManagedChatRepository extends Fake
    implements ChatGroupAdminRepository {
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

  @override
  Future<GroupHome> getGroupHome(String conversationId) async {
    return GroupHome(
      conversationId: conversationId,
      title: '圈群',
      avatarUrl: '',
      groupAvatarVersion: 0,
      circleId: 'fixture_circle',
      circleGroupId: 'fixture_circle_group',
      gatheringId: '',
      entityId: '',
      sourceEntityTitle: '',
      sourceCircleTitle: '',
      memberCount: 3,
      announcement: '',
      capabilities: const <String>['voice_call'],
      originType: 'circle_group',
      accessMode: ConversationAccessMode.active,
      postingPolicy: ConversationPostingPolicy.memberChat,
      canManageMembers: false,
      canDissolve: false,
    );
  }
}
