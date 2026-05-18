import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/chat/widgets/chat_conversation_avatar_tokens.dart';

Widget _scopedApp({ChatRepository? mock}) {
  final repo = mock ?? MockChatRepository();
  return ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat',
        routes: [
          GoRoute(
            path: '/chat',
            builder: (_, _) => const Scaffold(body: ChatPage()),
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

void main() {
  group('ChatPage — 渲染契约', () {
    testWidgets('正常渲染聊天列表页', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.text(UITextConstants.atXiaoqu), findsOneWidget);
      expect(find.text(UITextConstants.reminders), findsOneWidget);
    });

    testWidgets('包含 Scaffold 结构', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(Scaffold), findsWidgets);
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

    testWidgets('@小趣分组展示评论和群聊小趣回复投影', (tester) async {
      await tester.pumpWidget(
        _scopedApp(mock: _XiaoquDeliveryChatRepository()),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.atXiaoqu));
      await tester.pumpAndSettle();

      expect(find.text('小趣评论回复'), findsOneWidget);
      expect(find.text('圈子普通聊天'), findsNothing);
    });

    testWidgets('提醒分组展示实体更新和圈子摘要投影', (tester) async {
      await tester.pumpWidget(
        _scopedApp(mock: _XiaoquDeliveryChatRepository()),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.reminders));
      await tester.pumpAndSettle();

      expect(find.text('主页更新提醒'), findsOneWidget);
      expect(find.text('圈子普通聊天'), findsNothing);
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
      final sparklesRightInset = screenWidth - tester.getTopRight(sparklesIcon).dx;
      final expectedInset = AppSpacing.topBarTrailingVisualInset(
        tester.element(page),
      );

      expect(sparklesRightInset, closeTo(expectedInset, 2.0));
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
      final tabBarTop =
          tester.getTopLeft(find.byType(CenteredScrollableTabBar)).dy;
      final safeTop = tester.view.viewPadding.top / tester.view.devicePixelRatio;
      final expectedTopInset =
          AppSpacing.primaryTopBarSafeTopInset(safeTop, page);
      final navHeight = AppSpacing.primaryTopBarHeight(page);

      expect(tabBarTop, greaterThanOrEqualTo(expectedTopInset));
      expect(tabBarTop, lessThan(expectedTopInset + navHeight));
      expect(expectedTopInset, lessThan(safeTop));
    });

    testWidgets('列表区左滑先切二级 Tab，二级越界后再切一级 Tab', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final swipeRegion = find.byType(TabSwipeSwitchRegion).first;

      for (var i = 0; i < 5; i++) {
        await tester.fling(swipeRegion, const Offset(-420, 0), 1200);
        await tester.pumpAndSettle();
      }

      expect(find.text(UITextConstants.secretPasswordPrompt), findsOneWidget);

      await tester.fling(
        find.text(UITextConstants.secretPasswordPrompt),
        const Offset(-420, 0),
        1200,
      );
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.contactsTabFunGroup), findsOneWidget);
      expect(find.text(UITextConstants.secretPasswordPrompt), findsNothing);
    });
  });

  group('ChatPage — 错误态渲染', () {
    testWidgets('Repository 返回空列表时安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(mock: _EmptyChatRepository()));
      await tester.pumpAndSettle();

      expect(find.byType(ChatPage), findsOneWidget);
      expect(find.text(UITextConstants.noConversations), findsOneWidget);
    });

    testWidgets('群头像 URL 缺失时使用姓名首字母占位（不再显示默认群图标）', (tester) async {
      await tester.pumpWidget(
        _scopedApp(mock: _GroupAvatarFallbackChatRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('默认群头像兜底'), findsOneWidget);
      expect(find.byIcon(Icons.group), findsNothing);
      expect(find.text('默'), findsWidgets);
    });

    testWidgets('群会话使用 avatarUrl 作为预渲染群头像', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _RenderedGroupAvatarChatRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('预渲染群头像'), findsOneWidget);
      expect(find.byType(Image), findsWidgets);
      expect(find.byIcon(Icons.group), findsNothing);
    });

    testWidgets('主列表会话头像使用共享边长 token', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _RenderedGroupAvatarChatRepository()),
      );
      await tester.pumpAndSettle();

      final avatarFinder = find.byType(RoundedSquareAvatar).first;
      final size = tester.getSize(avatarFinder);

      expect(size.width, ChatConversationAvatarTokens.listSize);
      expect(size.height, ChatConversationAvatarTokens.listSize);
    });

    testWidgets('群会话缺失 avatarUrl 时不再渲染九宫格拼图', (tester) async {
      _suppressImageErrors();
      await tester.pumpWidget(
        _scopedApp(mock: _GroupAvatarCompositeChatRepository()),
      );
      await tester.pumpAndSettle();

      expect(find.text('组合群头像兜底'), findsOneWidget);
      expect(find.text('组'), findsWidgets);
    });
  });
}

class _EmptyChatRepository extends MockChatRepository {
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

class _NavigationChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      ChatInboxDto(
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
}

class _XiaoquDeliveryChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    final now = DateTime.utc(2026, 5, 1, 12);
    return <ChatInboxDto>[
      ChatInboxDto(
        id: 'conv_xiaoqu_comment_reply',
        type: 'group',
        title: '小趣评论回复',
        lastMessagePreview: '@小趣 已回复你的评论',
        lastMessageTime: now,
        unreadCount: 1,
        mentionUnreadCount: 1,
      ),
      ChatInboxDto(
        id: 'conv_homepage_reminder',
        type: 'group',
        title: '主页更新提醒',
        lastMessagePreview: '北京大学主页有新内容更新',
        lastMessageTime: now.subtract(const Duration(minutes: 1)),
        unreadCount: 1,
      ),
      ChatInboxDto(
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

class _GroupAvatarFallbackChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      ChatInboxDto(
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
}

class _RenderedGroupAvatarChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      ChatInboxDto(
        id: 'conv_rendered_group',
        type: 'group',
        title: '预渲染群头像',
        avatarUrl: 'https://example.com/group-rendered.jpg',
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

class _GroupAvatarCompositeChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      ChatInboxDto(
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
}
