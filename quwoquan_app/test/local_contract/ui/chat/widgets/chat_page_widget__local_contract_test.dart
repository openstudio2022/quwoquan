import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/ui/chat/pages/greeting_inbox_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/chat/widgets/chat_conversation_avatar_tokens.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AckAppMessageCommand,
        AppMessage,
        AppMessageCommandWriter,
        AppMessageDestination,
        AppMessageInboxSlice,
        AppMessageQuery,
        AppMessageTarget,
        AppMessageUnreadCountSlice,
        GetAppMessageQuery,
        GetAppMessageUnreadCountQuery,
        GreetingRequestRecord,
        ListAppMessagesQuery,
        ReadAppMessageCommand;

import '../../../../support/cloud_services/user_typed_facet_test_support.dart';
import '../../../../support/fixtures/chat/chat_inbox_fixture_builder.dart';

const _primaryAvatarDataUri =
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PyBqWQAAAABJRU5ErkJggg==';
const _staleConversationAvatarDataUri =
    'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';

Widget _scopedApp({
  ChatRepository? mock,
  Iterable<GreetingRequestRecord> greetingInbox =
      const <GreetingRequestRecord>[],
  bool isDark = false,
  VisitRecorderService? visitRecorder,
  _EmptyAppMessageFacet? appMessageFacet,
}) {
  final repo = mock ?? MockChatRepository();
  final appMessages = appMessageFacet ?? _EmptyAppMessageFacet();
  return ProviderScope(
    retry: (_, _) => null,
    overrides: [
      chatRepositoryCompositionProvider.overrideWithValue(repo),
      greetingRepositoryProvider.overrideWithValue(
        alphaGreetingRepository(seedInbox: greetingInbox),
      ),
      visitRecorderServiceProvider.overrideWithValue(
        visitRecorder ?? _NoopVisitRecorderService(),
      ),
      isDarkProvider.overrideWithValue(isDark),
      appMessageQueryProvider.overrideWithValue(appMessages),
      appMessageCommandWriterProvider.overrideWithValue(appMessages),
    ],
    child: MaterialApp.router(
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: isDark ? ThemeMode.dark : ThemeMode.light,
      routerConfig: GoRouter(
        initialLocation: '/chat',
        routes: [
          GoRoute(
            path: '/chat',
            builder: (_, _) => const Scaffold(body: ChatPage()),
          ),
          GoRoute(
            path: AppRoutePaths.greetingInbox,
            builder: (_, _) => const GreetingInboxPage(),
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

final class _NoopVisitRecorderService extends VisitRecorderService {
  _NoopVisitRecorderService() : super();

  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

/// 通知维度的默认云端 inbox fake：空 inbox / 零未读。
/// 子类覆写 listAppMessages 提供场景数据。
base class _EmptyAppMessageFacet
    implements AppMessageQuery, AppMessageCommandWriter {
  final List<String> readMessageIds = <String>[];

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
    return AppMessageInboxSlice(items: const <AppMessage>[]);
  }

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async {
    final slice = await listAppMessages(const ListAppMessagesQuery(limit: 50));
    return slice.items.firstWhere(
      (message) => message.messageId == query.messageId,
    );
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async {
    final slice = await listAppMessages(const ListAppMessagesQuery(limit: 50));
    return AppMessageUnreadCountSlice(
      unreadCount: slice.items.where((message) => !message.read).length,
    );
  }

  @override
  Future<AppMessage> acknowledge(AckAppMessageCommand command) async {
    return getAppMessage(GetAppMessageQuery(messageId: command.messageId));
  }

  @override
  Future<AppMessage> markRead(ReadAppMessageCommand command) async {
    readMessageIds.add(command.messageId);
    return getAppMessage(GetAppMessageQuery(messageId: command.messageId));
  }
}

/// B11 场景：云端 inbox 返回主页更新提醒 AppMessage。
final class _HomepageReminderAppMessageFacet extends _EmptyAppMessageFacet {
  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
    return AppMessageInboxSlice(
      items: <AppMessage>[
        AppMessage(
          messageId: 'app_msg_homepage_reminder',
          userId: 'mock_me',
          messageType: 'content',
          source: 'homepage',
          sourceId: 'homepage-1',
          destination: const AppMessageDestination(type: 'user', id: 'mock_me'),
          title: '主页更新提醒',
          summary: '北京大学主页有新内容更新',
          target: const AppMessageTarget(
            targetType: 'homepage',
            targetId: 'homepage-1',
          ),
          read: false,
          createdAt: DateTime.utc(2026, 5, 1, 12),
        ),
      ],
    );
  }
}

final class _RecordingVisitRecorderService extends VisitRecorderService {
  _RecordingVisitRecorderService() : super();

  final List<VisitTarget> recordedTargets = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recordedTargets.add(target);
  }
}

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

Finder _findByValueKeyPrefix(String prefix) {
  return find.byWidgetPredicate((widget) {
    final key = widget.key;
    return key is ValueKey<String> && key.value.startsWith(prefix);
  });
}

Finder _inboxAvatarFinder(String conversationId) {
  return find.descendant(
    of: find.byKey(ValueKey<String>('chat-inbox-row-$conversationId')),
    matching: find.byType(RoundedSquareAvatar),
  );
}

Color? _containerColor(WidgetTester tester, Finder finder) {
  final container = tester.widget<Container>(finder);
  final decoration = container.decoration;
  if (decoration is BoxDecoration) {
    return decoration.color;
  }
  return container.color;
}

void main() {
  group('ChatPage — 渲染契约', () {
    testWidgets('正常渲染聊天列表页', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.text(ChatText.chatPrimaryContacts), findsOneWidget);
      expect(find.text(ChatText.unread), findsOneWidget);
      expect(find.text(ChatText.groupChat), findsOneWidget);
      expect(find.text(ChatText.chatPrivateMessages), findsOneWidget);
      expect(find.text(ChatText.chatNotifications), findsOneWidget);
      expect(find.text('趣群'), findsNothing);
      expect(find.text(ChatText.atXiaoqu), findsNothing);
      expect(find.text(ChatText.reminders), findsNothing);
    });

    testWidgets('进入和切换聊天页会记录页面访问', (tester) async {
      final recorder = _RecordingVisitRecorderService();

      await tester.pumpWidget(_scopedApp(visitRecorder: recorder));
      await tester.pump();

      expect(
        recorder.recordedTargets,
        contains(const VisitTarget.page('chat_messages_all')),
      );

      await tester.tap(find.text(ChatText.chatPrimaryContacts));
      await tester.pumpAndSettle();

      expect(
        recorder.recordedTargets,
        contains(const VisitTarget.page('chat_contacts_all')),
      );
    });

    testWidgets('星标朋友保留分组标题但不再渲染行尾星标', (tester) async {
      await tester.pumpWidget(
        _scopedApp(mock: _StarredContactsChatRepository()),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text(ChatText.chatPrimaryContacts));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('chat-contact-section-label-star')),
        findsOneWidget,
      );
      expect(find.text(ChatText.starredFriends), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.star_fill), findsNothing);
    });

    testWidgets('联系人数不超过 20 时隐藏索引，超过阈值后显示', (tester) async {
      for (final count in <int>[20, 21]) {
        await tester.pumpWidget(
          _scopedApp(mock: _ContactIndexThresholdChatRepository(count)),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text(ChatText.chatPrimaryContacts));
        await tester.pumpAndSettle();

        expect(
          _findByValueKeyPrefix('chat-contact-index-letter-'),
          count <= 20 ? findsNothing : findsWidgets,
          reason: '联系人数量为 $count 时索引展示规则不符合阈值契约',
        );

        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump();
      }
    });

    testWidgets('包含 Scaffold 结构', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('列表表面与分割线对齐更多功能语义 token', (tester) async {
      for (final isDark in <bool>[false, true]) {
        await tester.pumpWidget(
          _scopedApp(mock: _NavigationChatRepository(), isDark: isDark),
        );
        await tester.pumpAndSettle();

        final expectedPageBackground = AppColorsFunctional.getColor(
          isDark,
          ColorType.pageBackground,
        );
        final expectedListSurface =
            SettingsSemanticConstants.conversationSheetCardSurface(isDark);
        final expectedListDivider =
            SettingsSemanticConstants.conversationSheetDividerColor(
              isDark,
            ).withValues(alpha: 0.9);
        final expectedPostSeparatorBand =
            SettingsSemanticConstants.conversationSheetPanelBackground(isDark);

        final mainChrome = tester.widget<Container>(
          find.byKey(const ValueKey<String>('chat-main-tabs-chrome')),
        );
        final mainDecoration = mainChrome.decoration! as BoxDecoration;
        expect(mainDecoration.color, expectedPageBackground);
        expect(mainDecoration.border, isNull);

        final secondarySlot = tester.widget<AnimatedContainer>(
          find.byKey(const ValueKey<String>('chat-secondary-tabs-slot')),
        );
        final secondarySlotDecoration =
            secondarySlot.decoration! as BoxDecoration;
        expect(secondarySlotDecoration.color, expectedPageBackground);
        expect(secondarySlotDecoration.border, isNull);

        final secondaryTabs = tester.widget<SecondaryCapsuleTabBar>(
          find.byKey(const ValueKey<String>('chat-secondary-capsule-tabs')),
        );
        expect(secondaryTabs.border, isNull);
        expect(secondaryTabs.backgroundColor, isNull);
        expect(
          secondaryTabs.variant,
          SecondaryCapsuleTabBarVariant.defaultSurface,
        );

        final inboxRowFinder = find.byKey(
          const ValueKey<String>('chat-inbox-row-conv_navigation_test'),
        );
        expect(_containerColor(tester, inboxRowFinder), expectedListSurface);
        final inboxDivider = tester.widget<Divider>(
          find.byKey(
            const ValueKey<String>(
              'chat-inbox-row-divider-conv_navigation_test',
            ),
          ),
        );
        expect(inboxDivider.color, expectedListDivider);

        await tester.tap(find.text(ChatText.chatPrimaryContacts));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        final contactRowFinder = _findByValueKeyPrefix('chat-contact-row-');
        expect(contactRowFinder, findsWidgets);
        expect(
          _containerColor(tester, contactRowFinder.first),
          expectedListSurface,
        );
        final contactAvatarFinder = find.descendant(
          of: contactRowFinder.first,
          matching: find.byType(RoundedSquareAvatar),
        );
        expect(contactAvatarFinder, findsWidgets);
        expect(
          tester.getSize(contactAvatarFinder.first),
          const Size.square(ChatConversationAvatarTokens.listSize),
        );
        final contactTitleFinder = find.descendant(
          of: contactRowFinder.first,
          matching: find.byWidgetPredicate(
            (widget) =>
                widget is Text &&
                widget.style?.fontSize == AppTypography.iosBody,
          ),
        );
        expect(contactTitleFinder, findsWidgets);
        final contactTitle = tester.widget<Text>(contactTitleFinder.first);
        expect(contactTitle.style?.fontSize, AppTypography.iosBody);
        expect(contactTitle.style?.fontWeight, AppTypography.regular);
        expect(contactTitle.style?.height, AppTypography.lineHeightTight);
        final contactSubtitleFinder = find.descendant(
          of: contactRowFinder.first,
          matching: find.byWidgetPredicate(
            (widget) =>
                widget is Text &&
                widget.style?.fontSize == AppTypography.iosFootnote,
          ),
        );
        expect(contactSubtitleFinder, findsOneWidget);
        final contactSubtitle = tester.widget<Text>(contactSubtitleFinder);
        expect(contactSubtitle.data?.isNotEmpty ?? false, isTrue);
        expect(contactSubtitle.style?.fontSize, AppTypography.iosFootnote);
        expect(contactSubtitle.style?.height, AppTypography.lineHeightCompact);
        expect(tester.getTopLeft(contactRowFinder.first).dx, 0);
        expect(
          tester.getSize(contactRowFinder.first).width,
          tester.getSize(find.byType(ChatPage)).width,
        );
        final contactDividerFinder = _findByValueKeyPrefix(
          'chat-contact-row-divider-',
        );
        expect(contactDividerFinder, findsWidgets);
        final contactDivider = tester.widget<Divider>(
          contactDividerFinder.first,
        );
        expect(contactDivider.color, expectedListDivider);
        expect(contactDivider.thickness, AppSpacing.hairline);
        expect(
          tester.getTopLeft(contactDividerFinder.first).dx,
          AppSpacing.md +
              ChatConversationAvatarTokens.dividerInset(
                ChatConversationAvatarTokens.listSize,
              ),
        );
        expect(
          tester.getTopRight(contactDividerFinder.first).dx,
          tester.getSize(find.byType(ChatPage)).width - AppSpacing.md,
        );

        final contactListView = tester.widget<ListView>(
          find
              .byWidgetPredicate(
                (widget) =>
                    widget is ListView &&
                    widget.scrollDirection == Axis.vertical,
              )
              .first,
        );
        expect(contactListView.padding, EdgeInsets.zero);

        final indexLetterFinder = _findByValueKeyPrefix(
          'chat-contact-index-letter-',
        );
        expect(indexLetterFinder, findsWidgets);
        expect(_containerColor(tester, indexLetterFinder.first), isNull);

        final sectionHeaderLabelFinder = _findByValueKeyPrefix(
          'chat-contact-section-label-',
        );
        expect(sectionHeaderLabelFinder, findsWidgets);
        final sectionHeaderFinder = find.ancestor(
          of: sectionHeaderLabelFinder.first,
          matching: find.byWidgetPredicate(
            (widget) =>
                widget is Container &&
                widget.color == expectedPostSeparatorBand,
          ),
        );
        expect(sectionHeaderFinder, findsOneWidget);
        expect(
          tester.getSize(sectionHeaderFinder.first).height,
          AppSpacing.twenty,
        );
        final sectionHeaderText = tester.widget<Text>(
          sectionHeaderLabelFinder.first,
        );
        final indexLetterText = tester.widget<Text>(
          find
              .descendant(
                of: indexLetterFinder.first,
                matching: find.byType(Text),
              )
              .first,
        );
        expect(
          sectionHeaderText.style?.fontSize,
          indexLetterText.style?.fontSize,
        );

        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump();
      }
    });
  });

  group('ChatPage — 交互契约', () {
    testWidgets('tap 会话列表项触发导航', (tester) async {
      await tester.pumpWidget(_scopedApp(mock: _NavigationChatRepository()));
      await tester.pumpAndSettle();

      await tester.tap(find.text('产品共创群').first);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('chat-detail-page')), findsOneWidget);
    });

    testWidgets('通知分组展示 AppMessage 投影', (tester) async {
      // B11：通知维度只消费 notification-service 云端 inbox
      //（ListAppMessages），不再从 chat repo 的 notification filter 拼行。
      await tester.pumpWidget(
        _scopedApp(
          mock: _XiaoquDeliveryChatRepository(),
          appMessageFacet: _HomepageReminderAppMessageFacet(),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text(ChatText.chatNotifications));
      await tester.pumpAndSettle();

      expect(find.text('主页更新提醒'), findsOneWidget);
      expect(find.text('圈子普通聊天'), findsNothing);
    });

    testWidgets('未读胶囊数与未读筛选 read model 保持一致', (tester) async {
      await tester.pumpWidget(
        _scopedApp(mock: _UnreadBadgeConsistencyChatRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('7'), findsOneWidget);
      expect(find.text('摄影爱好者圈子'), findsOneWidget);
      expect(find.text('产品共创群'), findsOneWidget);
      expect(find.text('旅行搭子讨论组'), findsOneWidget);
      expect(find.text('陈倩'), findsNothing);

      final badgeFinder = find.byKey(
        const ValueKey<String>('secondary-capsule-number-badge-1'),
      );
      expect(badgeFinder, findsOneWidget);
      expect(tester.getSize(badgeFinder), const Size.square(AppSpacing.twenty));
    });

    testWidgets('打招呼请求箱回复后进入正式会话', (tester) async {
      final greetingInbox = <GreetingRequestRecord>[
        GreetingRequestRecord(
          id: 'greeting_001',
          requesterSubAccountId: 'user_requester',
          targetSubAccountId: 'mock_me',
          requestMessage: '想和你聊聊川西路线',
          status: 'pending',
          source: 'profile',
          createdAt: DateTime.utc(2026, 1, 1),
          updatedAt: DateTime.utc(2026, 1, 1),
        ),
      ];
      await tester.pumpWidget(_scopedApp(greetingInbox: greetingInbox));
      await tester.pumpAndSettle();

      expect(find.text(ChatText.chatGreetingInboxTitle), findsOneWidget);
      await tester.tap(find.text(ChatText.chatGreetingInboxTitle));
      await tester.pumpAndSettle();
      expect(find.text('想和你聊聊川西路线'), findsWidgets);

      await tester.tap(find.text(ChatText.chatGreetingInboxReply));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('chat-detail-page')), findsOneWidget);
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('下拉刷新不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      await tester.drag(find.byType(ChatPage), const Offset(0, 300));
      await tester.pumpAndSettle();

      expect(find.byType(ChatPage), findsOneWidget);
    });

    testWidgets('右上小趣入口向内收至统一安全边距', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final page = find.byType(ChatPage);
      final sparklesIcon = find.byIcon(CupertinoIcons.sparkles).first;
      final screenWidth = tester.getSize(page).width;
      final sparklesRightInset =
          screenWidth - tester.getTopRight(sparklesIcon).dx;
      final expectedInset = AppSpacing.topBarTrailingVisualInset(
        tester.element(page),
      );

      expect(sparklesRightInset, closeTo(expectedInset, 2.0));
      expect(
        tester.getSize(find.byKey(TestKeys.globalAssistantEntryMark)),
        const Size.square(AppSpacing.globalAssistantEntryMarkSize),
      );
    });

    testWidgets('消息顶部工具栏与发现页搜索壳保持同源安全区节奏', (tester) async {
      tester.view.physicalSize = const Size(1179, 2556);
      tester.view.devicePixelRatio = 3.0;
      tester.view.viewPadding = const FakeViewPadding(top: 59, bottom: 34);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewPadding);

      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final page = tester.element(find.byType(ChatPage));
      final tabBarTop = tester
          .getTopLeft(find.byType(CenteredScrollableTabBar))
          .dy;
      final safeTop =
          tester.view.viewPadding.top / tester.view.devicePixelRatio;
      final expectedTopInset = AppSpacing.primaryTopBarSafeTopInset(
        safeTop,
        page,
      );
      final navHeight = AppSpacing.primaryTopBarHeight(page);

      expect(tabBarTop, greaterThanOrEqualTo(expectedTopInset));
      expect(tabBarTop, lessThan(expectedTopInset + navHeight));
      expect(expectedTopInset, lessThan(safeTop));
    });

    testWidgets('列表区左滑先切二级 Tab，二级越界后再切一级 Tab', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final swipeRegion = find.byType(TabSwipeSwitchRegion).first;

      for (var i = 0; i < 4; i++) {
        await tester.fling(swipeRegion, const Offset(-420, 0), 1200);
        await tester.pumpAndSettle();
      }

      expect(find.text(ChatText.chatNotifications), findsOneWidget);
      expect(find.text(ChatText.secretMessage), findsNothing);

      await tester.fling(
        find.byType(TabSwipeSwitchRegion).first,
        const Offset(-420, 0),
        1200,
      );
      await tester.pumpAndSettle();

      expect(find.text(ChatText.contactsTabGroups), findsOneWidget);
      expect(find.text(ChatText.secretMessage), findsNothing);
    });
  });

  group('ChatPage — 错误态渲染', () {
    testWidgets('Repository 返回空列表时安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(mock: _EmptyChatRepository()));
      await tester.pumpAndSettle();

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.text(ChatText.noConversations), findsOneWidget);
    });

    testWidgets('群头像 URL 缺失时显示稳定群占位且不拉成员', (tester) async {
      _suppressImageErrors();
      final repo = _GroupAvatarFallbackChatRepository();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pumpAndSettle();

      expect(find.text('默认群头像兜底'), findsOneWidget);
      final avatarFinder = _inboxAvatarFinder('conv_fallback_group');
      expect(avatarFinder, findsOneWidget);
      final avatar = tester.widget<RoundedSquareAvatar>(avatarFinder);
      expect(avatar.imageUrl, isNull);
      expect(repo.memberRequestCount, 0);
      expect(find.text('默'), findsNothing);
    });

    testWidgets('群会话使用 avatarUrl 作为预渲染群头像', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _RenderedGroupAvatarChatRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('预渲染群头像'), findsOneWidget);
      final avatarFinder = _inboxAvatarFinder('conv_rendered_group');
      expect(avatarFinder, findsOneWidget);
      final avatar = tester.widget<RoundedSquareAvatar>(avatarFinder);
      expect(avatar.imageUrl, _primaryAvatarDataUri);
    });

    testWidgets('群会话 version 为 0 时仍使用会话 avatarUrl 单图', (tester) async {
      _suppressImageErrors();
      final repo = _NonAuthoritativeGroupAvatarChatRepository();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pumpAndSettle();

      expect(find.text('非权威群头像'), findsOneWidget);
      final avatarFinder = _inboxAvatarFinder('conv_wrong_group_avatar');
      expect(avatarFinder, findsOneWidget);
      final avatar = tester.widget<RoundedSquareAvatar>(avatarFinder);
      expect(avatar.imageUrl, _primaryAvatarDataUri);
      expect(repo.memberRequestCount, 0);
    });

    testWidgets('conv_grid_12 使用云侧预合成 avatarUrl 且不拉成员', (tester) async {
      _suppressImageErrors();
      final repo = _ConvGrid12GroupAvatarChatRepository();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pumpAndSettle();

      expect(find.text('12人测试群'), findsOneWidget);
      final avatarFinder = _inboxAvatarFinder('conv_grid_12');
      expect(avatarFinder, findsOneWidget);
      final avatar = tester.widget<RoundedSquareAvatar>(avatarFinder);
      expect(avatar.imageUrl, _primaryAvatarDataUri);
      expect(repo.memberRequestCount, 0);
    });

    testWidgets('主列表会话头像使用共享边长 token', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _RenderedGroupAvatarChatRepository()),
      );
      await tester.pumpAndSettle();

      final avatarFinder = _inboxAvatarFinder('conv_rendered_group');
      expect(avatarFinder, findsOneWidget);
      final size = tester.getSize(avatarFinder);

      expect(size.width, ChatConversationAvatarTokens.listSize);
      expect(size.height, ChatConversationAvatarTokens.listSize);
    });

    testWidgets('群会话缺失 avatarUrl 时不再端侧拼九宫格', (tester) async {
      _suppressImageErrors();
      final repo = _GroupAvatarCompositeChatRepository();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pumpAndSettle();

      expect(find.text('组合群头像兜底'), findsOneWidget);
      final avatarFinder = _inboxAvatarFinder('conv_composite_group');
      expect(avatarFinder, findsOneWidget);
      final avatar = tester.widget<RoundedSquareAvatar>(avatarFinder);
      expect(avatar.imageUrl, isNull);
      expect(repo.memberRequestCount, 0);
      expect(find.text('组'), findsNothing);
    });

    testWidgets('聊天列表群头像不预取成员，滚动也不触发成员请求', (tester) async {
      _suppressImageErrors();
      tester.view.devicePixelRatio = 1.0;
      tester.view.physicalSize = const Size(390, 640);
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      final repo = _PrefetchedGroupAvatarChatRepository();
      await tester.pumpWidget(_scopedApp(mock: repo));
      await tester.pumpAndSettle();

      expect(repo.memberRequestCount, 0);

      await tester.drag(
        find.byWidgetPredicate(
          (widget) =>
              widget is ListView && widget.scrollDirection == Axis.vertical,
        ),
        const Offset(0, -900),
      );
      await tester.pumpAndSettle();

      expect(repo.memberRequestCount, 0);
    });

    testWidgets('单聊头像 URL 缺失时回退到对方头像而不是标题首字', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _DirectAvatarFallbackChatRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('契约撰稿人'), findsOneWidget);
      final avatarFinder = _inboxAvatarFinder('conv_direct_fallback');
      expect(avatarFinder, findsOneWidget);
      final avatar = tester.widget<RoundedSquareAvatar>(avatarFinder);
      expect(avatar.imageUrl, _primaryAvatarDataUri);
      expect(find.text('契'), findsNothing);
    });

    testWidgets('单聊会话头像优先与联系人头像保持一致', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _DirectAvatarConsistencyChatRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('手机端头像一致性'), findsOneWidget);
      final avatarFinder = _inboxAvatarFinder('conv_direct_consistency');
      expect(avatarFinder, findsOneWidget);
      final avatar = tester.widget<RoundedSquareAvatar>(avatarFinder);
      expect(avatar.imageUrl, _primaryAvatarDataUri);
    });
  });
}

abstract class _ListInboxDrivenChatRepository extends MockChatRepository {
  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    final inbox = await listInbox(cursor: cursor, limit: limit);
    return inbox
        .where((item) {
          return switch (filter) {
            'unread' => item.unreadCount > 0 || item.mentionUnreadCount > 0,
            'group' => item.type == 'group',
            'direct' => item.type == 'direct' || item.type == 'encrypted',
            'notification' => false,
            _ => true,
          };
        })
        .map(
          (item) => MessageHomeRowDto(
            id: item.id,
            conversationId: item.id,
            conversationType: item.type,
            title: item.title,
            summary: item.lastMessagePreview,
            avatarUrl: item.avatarUrl,
            groupAvatarVersion: item.groupAvatarVersion,
            lastActiveAt: item.lastMessageTime,
            unreadCount: item.unreadCount,
            mentionUnreadCount: item.mentionUnreadCount,
            muted: item.muted,
            pinned: item.pinned,
            read: item.unreadCount == 0 && item.mentionUnreadCount == 0,
          ),
        )
        .toList(growable: false);
  }
}

class _EmptyChatRepository extends _ListInboxDrivenChatRepository {
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

class _NavigationChatRepository extends _ListInboxDrivenChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_navigation_test',
        type: 'direct',
        title: '产品共创群',
        avatarUrl: '',
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<CursorPage<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    return CursorPage<ChatContactRowDto>(
      items: <ChatContactRowDto>[
        ChatContactRowDto(
          userId: 'user_navigation_contact',
          displayName: '李明',
          avatarUrl: 'https://example.com/contact.jpg',
          bio: '篮球爱好者',
          relationState: 'mutual',
        ),
      ],
    );
  }
}

class _StarredContactsChatRepository extends MockChatRepository {
  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    return <ContactHomeRowDto>[
      ContactHomeRowDto(
        id: 'user_starred_contact',
        kind: 'user',
        objectId: 'user_starred_contact',
        userId: 'user_starred_contact',
        title: 'Ada Starred',
        avatarUrl: 'https://example.com/starred_contact.jpg',
        subtitle: 'Starred contact',
        relationState: 'mutual',
        isStarred: true,
      ),
      ContactHomeRowDto(
        id: 'user_regular_contact',
        kind: 'user',
        objectId: 'user_regular_contact',
        userId: 'user_regular_contact',
        title: 'Ben Regular',
        avatarUrl: 'https://example.com/regular_contact.jpg',
        subtitle: 'Regular contact',
        relationState: 'mutual',
      ),
    ];
  }
}

class _ContactIndexThresholdChatRepository extends MockChatRepository {
  _ContactIndexThresholdChatRepository(this.count);

  final int count;

  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    return List<ContactHomeRowDto>.generate(
      count,
      (index) => ContactHomeRowDto(
        id: 'threshold_contact_$index',
        kind: 'user',
        objectId: 'threshold_contact_$index',
        userId: 'threshold_contact_$index',
        title: 'A Contact ${index + 1}',
        relationState: 'mutual',
      ),
    ).take(limit).toList(growable: false);
  }
}

class _XiaoquDeliveryChatRepository extends MockChatRepository {
  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    final now = DateTime.utc(2026, 5, 1, 12);
    if (filter == 'notification') {
      return <MessageHomeRowDto>[
        MessageHomeRowDto(
          id: 'app_msg_homepage_reminder',
          kind: 'notification',
          notificationId: 'app_msg_homepage_reminder',
          title: '主页更新提醒',
          summary: '北京大学主页有新内容更新',
          lastActiveAt: now,
          unreadCount: 1,
        ),
      ];
    }
    return <MessageHomeRowDto>[
      MessageHomeRowDto(
        id: 'conv_regular_group',
        kind: 'conversation',
        conversationId: 'conv_regular_group',
        conversationType: 'group',
        title: '圈子普通聊天',
        summary: '今晚一起拍照吗',
        lastActiveAt: now.subtract(const Duration(minutes: 2)),
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    final now = DateTime.utc(2026, 5, 1, 12);
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_xiaoqu_comment_reply',
        type: 'group',
        title: '小趣评论回复',
        lastMessagePreview: '@小趣 已回复你的评论',
        lastMessageTime: now,
        unreadCount: 1,
        mentionUnreadCount: 1,
      ),
      chatInboxFixture(
        id: 'conv_homepage_reminder',
        type: 'group',
        title: '主页更新提醒',
        lastMessagePreview: '北京大学主页有新内容更新',
        lastMessageTime: now.subtract(const Duration(minutes: 1)),
        unreadCount: 1,
      ),
      chatInboxFixture(
        id: 'conv_regular_group',
        type: 'group',
        title: '圈子普通聊天',
        lastMessagePreview: '今晚一起拍照吗',
        lastMessageTime: now.subtract(const Duration(minutes: 2)),
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }
}

class _UnreadBadgeConsistencyChatRepository extends MockChatRepository {
  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) async {
    final now = DateTime.utc(2026, 6, 16, 10);
    final unreadRows = <MessageHomeRowDto>[
      MessageHomeRowDto(
        id: 'conv_group_photo',
        kind: 'conversation',
        conversationId: 'conv_group_photo',
        conversationType: 'group',
        title: '摄影爱好者圈子',
        summary: '分享一组新疆风景照',
        lastActiveAt: now,
        unreadCount: 2,
      ),
      MessageHomeRowDto(
        id: 'conv_group_product',
        kind: 'conversation',
        conversationId: 'conv_group_product',
        conversationType: 'group',
        title: '产品共创群',
        summary: '今晚 8 点前把评审意见同步到文档里',
        lastActiveAt: now.subtract(const Duration(minutes: 3)),
        unreadCount: 1,
      ),
      MessageHomeRowDto(
        id: 'conv_group_travel',
        kind: 'conversation',
        conversationId: 'conv_group_travel',
        conversationType: 'group',
        title: '旅行搭子讨论组',
        summary: '我把演示视频压缩后重新发你了',
        lastActiveAt: now.subtract(const Duration(minutes: 5)),
        unreadCount: 4,
      ),
    ];
    if (filter == 'unread' || filter == 'all' || filter == 'group') {
      return unreadRows;
    }
    if (filter == 'direct' || filter == 'notification') {
      return const <MessageHomeRowDto>[];
    }
    return unreadRows;
  }

  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_direct_mismatch_seed',
        type: 'direct',
        title: '陈倩',
        lastMessagePreview: '我把演示视频压缩后重新发你了',
        lastMessageTime: DateTime.utc(2026, 6, 16, 9, 58),
        unreadCount: 1,
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }
}

class _GroupAvatarFallbackChatRepository
    extends _ListInboxDrivenChatRepository {
  int memberRequestCount = 0;

  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_fallback_group',
        type: 'group',
        title: '默认群头像兜底',
        avatarUrl: '',
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    memberRequestCount += 1;
    return <ChatConversationMemberDto>[
      ChatConversationMemberDto(
        userId: 'user_002',
        displayName: '李明',
        avatarUrl: 'https://example.com/user_002.jpg',
      ),
      ChatConversationMemberDto(
        userId: 'user_003',
        displayName: '张华',
        avatarUrl: '',
      ),
    ];
  }
}

class _RenderedGroupAvatarChatRepository
    extends _ListInboxDrivenChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_rendered_group',
        type: 'group',
        title: '预渲染群头像',
        avatarUrl: _primaryAvatarDataUri,
        groupAvatarVersion: 2,
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }
}

class _ConvGrid12GroupAvatarChatRepository
    extends _ListInboxDrivenChatRepository {
  int memberRequestCount = 0;

  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_grid_12',
        type: 'group',
        title: '12人测试群',
        avatarUrl: _primaryAvatarDataUri,
        groupAvatarVersion: 1,
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    memberRequestCount += 1;
    return const <ChatConversationMemberDto>[];
  }
}

class _NonAuthoritativeGroupAvatarChatRepository
    extends _ListInboxDrivenChatRepository {
  int memberRequestCount = 0;

  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_wrong_group_avatar',
        type: 'group',
        title: '非权威群头像',
        avatarUrl: _primaryAvatarDataUri,
        groupAvatarVersion: 0,
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    memberRequestCount += 1;
    return <ChatConversationMemberDto>[
      ChatConversationMemberDto(
        userId: 'user_002',
        displayName: '李明',
        avatarUrl: 'https://example.com/wrong-single.jpg',
      ),
      ChatConversationMemberDto(
        userId: 'user_003',
        displayName: '张华',
        avatarUrl: 'https://example.com/user_003.jpg',
      ),
      ChatConversationMemberDto(
        userId: 'user_004',
        displayName: '王芳',
        avatarUrl: 'https://example.com/user_004.jpg',
      ),
    ];
  }
}

class _GroupAvatarCompositeChatRepository
    extends _ListInboxDrivenChatRepository {
  int memberRequestCount = 0;

  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_composite_group',
        type: 'group',
        title: '组合群头像兜底',
        avatarUrl: '',
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    memberRequestCount += 1;
    return <ChatConversationMemberDto>[
      ChatConversationMemberDto(
        userId: 'user_002',
        displayName: '李明',
        avatarUrl: 'https://example.com/user_002.jpg',
      ),
      ChatConversationMemberDto(
        userId: 'user_003',
        displayName: '张华',
        avatarUrl: 'https://example.com/user_003.jpg',
      ),
      ChatConversationMemberDto(
        userId: 'user_004',
        displayName: '王芳',
        avatarUrl: 'https://example.com/user_004.jpg',
      ),
    ];
  }
}

class _DirectAvatarFallbackChatRepository
    extends _ListInboxDrivenChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_direct_fallback',
        type: 'direct',
        title: '契约撰稿人',
        avatarUrl: '',
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    return <ChatConversationMemberDto>[
      ChatConversationMemberDto(
        userId: 'user_me',
        displayName: '我',
        avatarUrl: 'https://example.com/user_me.jpg',
        isCurrentUser: true,
      ),
      ChatConversationMemberDto(
        userId: 'user_002',
        displayName: '契约撰稿人',
        avatarUrl: _primaryAvatarDataUri,
      ),
    ];
  }
}

class _DirectAvatarConsistencyChatRepository
    extends _ListInboxDrivenChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'conv_direct_consistency',
        type: 'direct',
        title: '手机端头像一致性',
        avatarUrl: _staleConversationAvatarDataUri,
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    return <ChatConversationMemberDto>[
      ChatConversationMemberDto(
        userId: 'user_me',
        displayName: '我',
        avatarUrl: 'https://example.com/me.jpg',
        isCurrentUser: true,
      ),
      ChatConversationMemberDto(
        userId: 'user_contact',
        displayName: '手机端头像一致性',
        avatarUrl: _primaryAvatarDataUri,
      ),
    ];
  }
}

class _PrefetchedGroupAvatarChatRepository
    extends _ListInboxDrivenChatRepository {
  int memberRequestCount = 0;

  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return List<ChatInboxDto>.generate(10, (index) {
      final number = index + 1;
      return chatInboxFixture(
        id: 'conv_prefetch_$number',
        type: 'group',
        title: '预取群$number',
        avatarUrl: '',
      );
    });
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    memberRequestCount += 1;
    final suffix = conversationId.replaceFirst('conv_prefetch_', '');
    return <ChatConversationMemberDto>[
      ChatConversationMemberDto(
        userId: 'user_$suffix',
        displayName: '用户$suffix',
        avatarUrl: 'https://example.com/user_$suffix.jpg',
      ),
      ChatConversationMemberDto(
        userId: 'user_${suffix}_b',
        displayName: '成员$suffix',
        avatarUrl: 'https://example.com/user_${suffix}_b.jpg',
      ),
    ];
  }
}
