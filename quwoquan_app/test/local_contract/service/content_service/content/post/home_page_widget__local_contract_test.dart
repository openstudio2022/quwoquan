import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/shell/actions/global_surface_actions.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show contentFeatureFlagProvider;
import 'package:quwoquan_app/l10n/app_localizations_zh.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/home_circles_hub_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_featured_immersive_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/following_subject_strip.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/global_search_page.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

InMemoryContentPostStore _homeStore() {
  return InMemoryContentPostStore(
    posts: <ContentPostViewData>[
      ...contentPostListBuilder(
        contentType: 'image',
        count: 2,
        idPrefix: 'home-image',
      ),
      ...contentPostListBuilder(
        contentType: 'video',
        count: 2,
        idPrefix: 'home-video',
      ),
      ...contentPostListBuilder(
        contentType: 'micro',
        count: 2,
        idPrefix: 'home-micro',
      ),
      ...contentPostListBuilder(
        contentType: 'article',
        count: 2,
        idPrefix: 'home-article',
      ),
    ],
  );
}

Widget _buildApp() {
  return ProviderScope(
    overrides: [...mockContentFacetOverrides(store: _homeStore())],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) =>
                  const Scaffold(body: HomePage(routeLocation: '/')),
            ),
            GoRoute(
              path: '/login',
              builder: (context, state) => const Scaffold(
                body: SizedBox(key: ValueKey<String>('login-route-sentinel')),
              ),
            ),
            GoRoute(
              path: '/circles',
              builder: (context, state) =>
                  const Scaffold(body: CirclesHubPage()),
            ),
            GoRoute(
              path: '/circle/:id',
              builder: (context, state) => const SizedBox(),
            ),
            GoRoute(
              path: '/chat/:id',
              builder: (context, state) => const SizedBox(),
            ),
            GoRoute(
              path: '/search',
              builder: (context, state) => GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:userHandle',
              builder: (context, state) => const SizedBox(),
            ),
          ],
        ),
      ),
    ),
  );
}

Widget _buildAppWithStableFollowingArticles() {
  return ProviderScope(
    overrides: [
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'test-persona',
          ownerUserId: 'test-user',
          displayName: '测试用户',
          avatarUrl: '',
        ),
      ),
      followingSubjectsProvider.overrideWith((_) async => const []),
      ...mockContentFacetOverrides(store: _homeStore()),
      contentFeatureFlagProvider('enable_article_distribution_profiles')
          .overrideWith((ref) => true),
      discoveryFeedMapProvider.overrideWith(
        _StableFollowingDiscoveryFeedMapNotifier.new,
      ),
    ],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) =>
                  const Scaffold(body: HomePage(routeLocation: '/following')),
            ),
            GoRoute(
              path: '/circles',
              builder: (context, state) =>
                  const Scaffold(body: CirclesHubPage()),
            ),
            GoRoute(
              path: '/circle/:id',
              builder: (context, state) => const SizedBox(),
            ),
            GoRoute(
              path: '/chat/:id',
              builder: (context, state) => const SizedBox(),
            ),
            GoRoute(
              path: '/search',
              builder: (context, state) => GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:userHandle',
              builder: (context, state) => const SizedBox(),
            ),
          ],
        ),
      ),
    ),
  );
}

Widget _buildAppWithStableFollowingFeed({bool stableArticles = false}) {
  return ProviderScope(
    overrides: [
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'test-persona',
          ownerUserId: 'test-user',
          displayName: '测试用户',
          avatarUrl: '',
        ),
      ),
      followingSubjectsProvider.overrideWith((_) async => const []),
      if (!stableArticles)
        ...mockContentFacetOverrides(store: _homeStore())
      else ...[
        ...mockContentFacetOverrides(store: _homeStore()),
        contentFeatureFlagProvider('enable_article_distribution_profiles')
            .overrideWith((ref) => true),
      ],
    ],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) =>
                  const Scaffold(body: HomePage(routeLocation: '/following')),
            ),
            GoRoute(
              path: '/search',
              builder: (context, state) => GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:userHandle',
              builder: (context, state) => const SizedBox(),
            ),
          ],
        ),
      ),
    ),
  );
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      ownerId: 'test-user',
      activePersonaId: 'test-persona',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

List<ContentPostViewData> _stableFollowingArticles() {
  return <ContentPostViewData>[
    _stableFollowingArticlePost(
      id: 'web-dev',
      title: '给新同事的 Web 工程工具清单',
      summary: '从构建、调试到部署，把最容易漏掉的环节集中整理成一页。',
      coverUrl:
          'media/image/s/archived-image/post/fixture_article_001/v1/cover.png',
    ),
    _stableFollowingArticlePost(
      id: 'ritual_plain',
      title: '晨间复盘的十分钟礼记',
      summary: '把前一天的情绪、节奏和待办留在固定版式里，早晨更容易进入状态。',
    ),
    _stableFollowingArticlePost(
      id: 'diffuse_cover_summary_only',
      summary: '把路线、风向和停留时间直接写进正文里，让临场决定也能保持连贯。',
      coverUrl:
          'media/image/s/archived-image/post/fixture_article_001/v1/image-2.png',
    ),
    _stableFollowingArticlePost(
      id: 'journal_plain_summary_only',
      summary: '没有标题也没有封面，仍然可以用摘要承接整张卡片的信息层级。',
    ),
  ];
}

ContentPostViewData _stableFollowingArticlePost({
  required String id,
  String title = '',
  required String summary,
  String coverUrl = '',
}) {
  return contentPostViewDataFromReadModelMap(<String, dynamic>{
    'id': id,
    '_id': id,
    'postId': id,
    'contentType': 'article',
    'type': 'article',
    'authorId': 'fixture_user_current',
    'displayName': '测试作者',
    'title': title,
    'summary': summary,
    'coverUrl': coverUrl,
    'imageUrl': coverUrl,
    'mediaCoverUrl': coverUrl,
    'createdAt': '2026-05-01T08:00:00Z',
    'articleTemplate': id == 'ritual_plain'
        ? 'ritual'
        : id == 'diffuse_cover_summary_only'
        ? 'diffuse'
        : id == 'journal_plain_summary_only'
        ? 'journal'
        : 'tech',
  });
}

class _StableFollowingDiscoveryFeedMapNotifier
    extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    final items = _stableFollowingArticles();
    return <String, AsyncValue<DiscoveryFeedState>>{
      'following': AsyncData(
        DiscoveryFeedState(
          items: items,
          seenItemIds: items.map((post) => post.id).toList(growable: false),
          nextCursor: null,
          isLoading: false,
        ),
      ),
    };
  }
}

/// 任务 A · 推荐流即时反馈测试用：固定单条 micro post，禁用真实加载，
/// 使卡片即时计数与负反馈移除可被确定性观测。
const String _singleRecommendPostId = 'rec_single_post_1';
const String _singleRecommendPostBody = '推荐流即时反馈验证正文内容片段';

ContentPostViewData _singleRecommendPost() {
  return contentPostViewDataFromReadModelMap(<String, dynamic>{
    'id': _singleRecommendPostId,
    '_id': _singleRecommendPostId,
    'postId': _singleRecommendPostId,
    'contentType': 'micro',
    'type': 'micro',
    'authorId': 'fixture_user_current',
    'personaId': 'fixture_user_current',
    'displayName': '即时反馈作者',
    'body': _singleRecommendPostBody,
    'likeCount': 55,
    'commentCount': 33,
    'shareCount': 77,
    'createdAt': '2026-05-01T08:00:00Z',
  });
}

class _SingleRecommendPostFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        DiscoveryFeedState(
          items: <ContentPostViewData>[_singleRecommendPost()],
          seenItemIds: const <String>[],
          nextCursor: null,
          isLoading: false,
        ),
      ),
    };
  }

  // 禁用真实拉取：移除卡片后保持空态，避免 mock 仓储回填打散断言。
  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );
}

Widget _buildAppWithSingleRecommendPost() {
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(store: _homeStore()),
      discoveryFeedMapProvider.overrideWith(
        _SingleRecommendPostFeedMapNotifier.new,
      ),
    ],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) =>
                  const Scaffold(body: HomePage(routeLocation: '/')),
            ),
            GoRoute(
              path: '/search',
              builder: (context, state) => GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:userHandle',
              builder: (context, state) => const SizedBox(),
            ),
          ],
        ),
      ),
    ),
  );
}

void _suppressExpectedErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException') ||
        message.contains('overflowed')) {
      return;
    }
    original?.call(details);
  };
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1179, 2556);
  tester.view.devicePixelRatio = 3.0;
}

void _setWideSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(2048, 2732);
  tester.view.devicePixelRatio = 2.0;
}

Future<void> _scrollUntilFinderVisible(
  WidgetTester tester,
  Finder scrollable,
  Finder target, {
  Offset step = const Offset(0, -320),
  int maxScrolls = 12,
}) async {
  for (var i = 0; i < maxScrolls; i++) {
    if (target.evaluate().isNotEmpty) {
      return;
    }
    await tester.drag(scrollable, step);
    await tester.pumpAndSettle();
  }
  expect(target, findsOneWidget);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('HomePage', () {
    testWidgets('展示八个首页文本频道并在频道条右侧保留全局搜索与小趣入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(HomePage), findsOneWidget);
      expect(find.text(DiscoveryText.homeTabFollowing), findsWidgets);
      expect(find.text(DiscoveryText.homeTabRecommended), findsWidgets);
      expect(find.text(DiscoveryText.homeTabFeatured), findsOneWidget);
      expect(find.text(DiscoveryText.circleScenarioCampus), findsWidgets);
      expect(find.text(DiscoveryText.homeTabTravel), findsWidgets);
      expect(find.text(DiscoveryText.homeTabPhotography), findsWidgets);
      expect(find.text(DiscoveryText.homeTabTech), findsWidgets);
      expect(find.text(DiscoveryText.homeTabCarFriends), findsWidgets);
      expect(
        find.byKey(const ValueKey<String>('home-primary-tab-chrome')),
        findsOneWidget,
      );
      // 首页是发现主入口，AppRoot REQ-001 的统一搜索入口与 REQ-008 的首页小趣入口
      // 必须与聊天页、个人页同源；缺任一入口即为 Journey 断点。
      expect(find.byType(GlobalTopActions), findsOneWidget);
      expect(find.byKey(TestKeys.globalSearchLauncherButton), findsOneWidget);
      expect(find.byKey(TestKeys.globalAssistantEntryMark), findsOneWidget);
    });

    testWidgets('首页文本频道栏避开安全区且状态栏跟随主题', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      tester.view.viewPadding = const FakeViewPadding(top: 59, bottom: 34);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewPadding);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final stripTop = tester.getTopLeft(find.byType(HomePrimaryTabStrip)).dy;
      final safeTop =
          tester.view.viewPadding.top / tester.view.devicePixelRatio;
      expect(stripTop, greaterThanOrEqualTo(safeTop));

      final overlay = tester.widget<AnnotatedRegion<SystemUiOverlayStyle>>(
        find
            .descendant(
              of: find.byType(HomePage),
              matching: find.byType(AnnotatedRegion<SystemUiOverlayStyle>),
            )
            .first,
      );
      expect(overlay.value.statusBarIconBrightness, Brightness.dark);
      expect(overlay.value.statusBarBrightness, Brightness.light);
    });

    testWidgets('浅色首页一级 Tab 选中 label 和下划线使用蓝色', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final selectedTab = find.byKey(
        HomePrimaryTabStrip.channelKey(
          HomePrimaryTabStrip.recommendedChannelId,
        ),
      );
      final selectedLabel = tester.widget<Text>(
        find
            .descendant(
              of: selectedTab,
              matching: find.text(DiscoveryText.homeTabRecommended),
            )
            .first,
      );
      final underline = tester.widget<AnimatedContainer>(
        find.descendant(
          of: selectedTab,
          matching: find.byType(AnimatedContainer),
        ),
      );
      final underlineDecoration = underline.decoration! as BoxDecoration;

      expect(selectedLabel.style?.color, AppColors.primaryColor);
      expect(underlineDecoration.color, AppColors.primaryColor);
    });

    testWidgets('浅色首页一级 Tab 与推荐单列流露底使用 post 表面色', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final expectedSurface =
          SettingsSemanticConstants.conversationSheetCardSurface(false);
      final tabChrome = tester.widget<Container>(
        find.byKey(const ValueKey<String>('home-primary-tab-chrome')),
      );
      final feedBackground = tester.widget<ColoredBox>(
        find
            .ancestor(
              of: find.byKey(const ValueKey<String>('home-feed-card-0')),
              matching: find.byType(ColoredBox),
            )
            .first,
      );

      expect(tabChrome.decoration, isA<BoxDecoration>());
      expect((tabChrome.decoration! as BoxDecoration).color, expectedSurface);
      expect((tabChrome.decoration! as BoxDecoration).border, isNull);
      expect(feedBackground.color, expectedSurface);
    });

    testWidgets('关注流 post 之间使用消息列表同源分割线', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithStableFollowingFeed());
      await tester.pumpAndSettle();

      final divider = tester.widget<Divider>(
        find.byKey(const ValueKey<String>('home-feed-divider-0')),
      );
      expect(divider.height, AppSpacing.one);
      expect(divider.thickness, AppSpacing.hairline);
      expect(
        divider.color,
        SettingsSemanticConstants.conversationSheetDividerColor(false)
            .withValues(alpha: 0.9),
      );
    });

    testWidgets('首页主 Tab 不再渲染圈子入口', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.circlesChannelId),
        ),
        findsNothing,
      );
    });

    testWidgets('默认停留在推荐信息流', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(HomeMultiFormFeed), findsOneWidget);
      expect(find.byType(HomePrimaryTabStrip), findsOneWidget);
      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(
            HomePrimaryTabStrip.recommendedChannelId,
          ),
        ),
        findsOneWidget,
      );
    });

    testWidgets('游客点击关注 tab 引导登录而不进入空白关注流', (tester) async {
      // 登录门有进程级防抖，先复位避免受其它用例触发影响。
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.channelKey(
            HomePrimaryTabStrip.followingChannelId,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 游客点击「关注」应被登录门拦截并引导至登录路由，而不是无效路由或空白关注流。
      expect(find.text('Page Not Found'), findsNothing);
      expect(
        find.byKey(const ValueKey<String>('login-route-sentinel')),
        findsOneWidget,
      );

      // 让登录提示 toast 的计时器结束，避免挂起的 Timer。
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('关注流手机端首条 post 占满屏宽', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithStableFollowingFeed());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(const ValueKey<String>('home-feed-card-0'));
      final screenWidth =
          tester.view.physicalSize.width / tester.view.devicePixelRatio;

      expect(cardFinder, findsOneWidget);
      expect(tester.getSize(cardFinder).width, closeTo(screenWidth, 1.0));
      final cardDecoration =
          tester.widget<DecoratedBox>(cardFinder).decoration as BoxDecoration;
      final isDark =
          CupertinoTheme.of(tester.element(cardFinder)).brightness ==
          Brightness.dark;
      expect(
        cardDecoration.color,
        SettingsSemanticConstants.conversationSheetCardSurface(isDark),
      );
      expect(
        (cardDecoration.border! as Border).top.color,
        AppColors.transparent,
      );
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(CupertinoIcons.ellipsis_circle),
        ),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('home-feed-more-0')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(Icons.more_horiz_rounded),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(CupertinoIcons.arrowshape_turn_up_right),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(CupertinoIcons.arrow_2_squarepath),
        ),
        findsNothing,
      );
    });

    testWidgets('关注流宽屏下首条 post 维持单列全宽关系卡', (tester) async {
      _suppressExpectedErrors();
      _setWideSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithStableFollowingFeed());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(const ValueKey<String>('home-feed-card-0'));
      final screenWidth =
          tester.view.physicalSize.width / tester.view.devicePixelRatio;

      expect(cardFinder, findsOneWidget);
      expect(tester.getSize(cardFinder).width, closeTo(screenWidth, 1.0));
    });

    testWidgets('关注流文章卡覆盖封面/标题四种组合', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithStableFollowingArticles());
      await tester.pumpAndSettle();

      final scrollable = find.byType(Scrollable).first;
      final coverCard = find.byKey(
        const ValueKey<String>('following-article-card-web-dev'),
      );
      final textOnlyCard = find.byKey(
        const ValueKey<String>('following-article-card-ritual_plain'),
      );
      final summaryOnlyCoverCard = find.byKey(
        const ValueKey<String>(
          'following-article-card-diffuse_cover_summary_only',
        ),
      );
      final summaryOnlyTextCard = find.byKey(
        const ValueKey<String>(
          'following-article-card-journal_plain_summary_only',
        ),
      );

      await _scrollUntilFinderVisible(tester, scrollable, coverCard);
      await tester.pumpAndSettle();
      expect(coverCard, findsOneWidget);
      expect(
        find.descendant(of: coverCard, matching: find.textContaining('科技')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: coverCard,
          matching: find.byKey(
            const ValueKey<String>('following-article-thumbnail-web-dev'),
          ),
        ),
        findsOneWidget,
      );

      await _scrollUntilFinderVisible(tester, scrollable, textOnlyCard);
      await tester.pumpAndSettle();
      expect(textOnlyCard, findsOneWidget);
      // 「礼记」既是 articleTemplate 标签也出现在本条标题里：分别断言 eyebrow
      // 与标题，避免用子串匹配把两处混成一处。
      expect(
        find.descendant(of: textOnlyCard, matching: find.text('文章 · 礼记')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: textOnlyCard, matching: find.text('晨间复盘的十分钟礼记')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: textOnlyCard,
          matching: find.byKey(
            const ValueKey<String>('following-article-thumbnail-ritual_plain'),
          ),
        ),
        findsNothing,
      );

      await _scrollUntilFinderVisible(tester, scrollable, summaryOnlyCoverCard);
      await tester.pumpAndSettle();
      expect(summaryOnlyCoverCard, findsOneWidget);
      expect(
        find.descendant(
          of: summaryOnlyCoverCard,
          matching: find.textContaining('弥散'),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: summaryOnlyCoverCard,
          matching: find.byKey(
            const ValueKey<String>(
              'following-article-thumbnail-diffuse_cover_summary_only',
            ),
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: summaryOnlyCoverCard,
          matching: find.textContaining('把路线、风向和停留时间直接写进正文里'),
        ),
        findsOneWidget,
      );

      await _scrollUntilFinderVisible(tester, scrollable, summaryOnlyTextCard);
      await tester.pumpAndSettle();
      expect(summaryOnlyTextCard, findsOneWidget);
      expect(
        find.descendant(
          of: summaryOnlyTextCard,
          matching: find.textContaining('手帐'),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: summaryOnlyTextCard,
          matching: find.byKey(
            const ValueKey<String>(
              'following-article-thumbnail-journal_plain_summary_only',
            ),
          ),
        ),
        findsNothing,
      );
      expect(
        find.descendant(
          of: summaryOnlyTextCard,
          matching: find.textContaining('没有标题也没有封面'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('关注流更多菜单不显示分享和查看原图', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithStableFollowingArticles());
      await tester.pumpAndSettle();

      final articleCard = find.byKey(
        const ValueKey<String>('following-article-card-web-dev'),
      );
      expect(articleCard, findsOneWidget);
      await tester.tap(
        find.descendant(
          of: articleCard,
          matching: find.byIcon(Icons.more_horiz_rounded),
        ),
      );
      await tester.pumpAndSettle();

      final page = find.byType(HomePage);
      final panel = find.byKey(TestKeys.modalBottomSheetPanel);

      expect(find.byKey(TestKeys.modalBottomSheetPanel), findsOneWidget);
      expect(tester.getTopLeft(panel).dy, greaterThan(0));
      expect(
        tester.getBottomRight(panel).dy,
        closeTo(tester.getSize(page).height, 2.0),
      );
      expect(find.text(FoundationText.copyLink), findsOneWidget);
      expect(find.text(FoundationText.cancel), findsOneWidget);
      expect(find.text(FoundationText.share), findsNothing);
      expect(find.text(ContentText.viewOriginal), findsNothing);
      expect(find.text('打赏'), findsNothing);
      expect(find.text('私信'), findsNothing);
      expect(find.text('字体设置'), findsNothing);
      expect(find.text('功能反馈'), findsNothing);
    });

    testWidgets('关注流宽屏下文章卡更多面板贴底呈现', (tester) async {
      _suppressExpectedErrors();
      _setWideSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithStableFollowingArticles());
      await tester.pumpAndSettle();

      final articleCard = find.byKey(
        const ValueKey<String>('following-article-card-web-dev'),
      );
      expect(articleCard, findsOneWidget);

      await tester.tap(
        find.descendant(
          of: articleCard,
          matching: find.byIcon(Icons.more_horiz_rounded),
        ),
      );
      await tester.pumpAndSettle();

      final panel = find.byKey(TestKeys.modalBottomSheetPanel);
      expect(panel, findsOneWidget);
      expect(tester.getTopLeft(panel).dy, greaterThan(0));

      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('首页一级频道按关注推荐视频书与五个业务垂类排序', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      for (final channelId in HomePrimaryTabStrip.homeChannelIds) {
        expect(
          find.byKey(HomePrimaryTabStrip.channelKey(channelId)),
          findsOneWidget,
        );
      }
      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(
            HomePrimaryTabStrip.followingChannelId,
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(
            HomePrimaryTabStrip.recommendedChannelId,
          ),
        ),
        findsOneWidget,
      );
      final tabLabels = <String>[];
      for (final channelId in HomePrimaryTabStrip.homeChannelIds) {
        tabLabels.add(
          tester
              .widget<Text>(
                find.descendant(
                  of: find.byKey(HomePrimaryTabStrip.channelKey(channelId)),
                  matching: find.byType(Text),
                ),
              )
              .data!,
        );
      }
      expect(
        tabLabels,
        equals(<String>['关注', '推荐', '视频书', '校园', '旅行', '摄影', '科技', '车之家']),
      );
    });

    testWidgets('视频书文本 Tab 复用 premium 沉浸 viewer 作为特殊正文', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.featuredChannelId),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.byKey(const ValueKey<String>('home-featured-channel-body')),
        findsOneWidget,
      );
      expect(find.byType(HomeFeaturedImmersivePage), findsOneWidget);
      expect(find.byType(WorksImmersiveViewer), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('works-top-back')),
        findsOneWidget,
      );
      // 视频书只作为文本频道存在，不再有顶栏专用入口图标；
      // 沉浸正文接管的是频道 body，顶栏的搜索与小趣入口必须保持可达。
      expect(
        find.byKey(const ValueKey<String>('home-featured-entry')),
        findsNothing,
      );
      expect(find.byKey(TestKeys.globalSearchLauncherButton), findsOneWidget);
      expect(find.byKey(TestKeys.globalAssistantEntryMark), findsOneWidget);
    });

    testWidgets('横滑校园内容切到旅行频道', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId),
        ),
      );
      await tester.pumpAndSettle();

      final firstCard = find.byKey(const ValueKey<String>('home-feed-card-0'));
      expect(firstCard, findsOneWidget);

      await tester.flingFrom(
        tester.getCenter(firstCard),
        const Offset(-320, 0),
        1400,
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId),
        ),
        findsOneWidget,
      );
    });

    testWidgets('切到旅行后主 tab 位置保持稳定', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final campusBefore = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId),
        ),
      );
      final travelBefore = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId),
        ),
      );
      final campusTopBefore = tester.getTopLeft(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId),
        ),
      );
      final travelTopBefore = tester.getTopLeft(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId),
        ),
      );
      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId),
        ),
      );
      await tester.pumpAndSettle();

      final campusAfter = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId),
        ),
      );
      final travelAfter = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId),
        ),
      );
      final campusTopAfter = tester.getTopLeft(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId),
        ),
      );
      final travelTopAfter = tester.getTopLeft(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId),
        ),
      );
      expect(campusAfter.dx, closeTo(campusBefore.dx, 0.1));
      expect(travelAfter.dx, closeTo(travelBefore.dx, 0.1));
      expect(campusTopAfter.dy, closeTo(campusTopBefore.dy, 0.1));
      expect(travelTopAfter.dy, closeTo(travelTopBefore.dy, 0.1));
    });

    testWidgets('推荐流卡片即时反映评论计数变化（无整屏刷新）', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithSingleRecommendPost());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(const ValueKey<String>('home-feed-card-0'));
      expect(cardFinder, findsOneWidget);
      // 初始计数来自 DTO（评论 33 / 分享 77），由乐观态桥接口径渲染。
      expect(
        find.descendant(of: cardFinder, matching: find.text('33')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: cardFinder, matching: find.text('77')),
        findsOneWidget,
      );

      // 模拟评论返回后的即时计数同步（PostInteractionState 乐观态确认）。
      final container = ProviderScope.containerOf(
        tester.element(find.byType(HomeMultiFormFeed)),
      );
      container
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedCounters(_singleRecommendPostId, commentCount: 99);
      await tester.pump();

      // 计数即时更新且不触发整屏刷新：卡片仍在原位，仅 label 数字变化。
      expect(cardFinder, findsOneWidget);
      expect(
        find.descendant(of: cardFinder, matching: find.text('99')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: cardFinder, matching: find.text('33')),
        findsNothing,
      );
    });

    testWidgets('推荐流不感兴趣即时移除卡片且撤销后原位恢复', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildAppWithSingleRecommendPost());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(const ValueKey<String>('home-feed-card-0'));
      expect(cardFinder, findsOneWidget);
      expect(find.text(_singleRecommendPostBody), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey<String>('home-feed-more-0')));
      await tester.pumpAndSettle();

      final notInterested = find.text(AppLocalizationsZh().notInterested);
      expect(notInterested, findsOneWidget);
      await tester.ensureVisible(notInterested);
      await tester.tap(notInterested);
      await tester.pumpAndSettle();

      // 卡片即时从信息流消失（本地乐观移除），落到空态而非空白滚动视图。
      expect(cardFinder, findsNothing);
      expect(find.text(_singleRecommendPostBody), findsNothing);

      // 即时降级提示 toast 可见。
      expect(
        find.text(DiscoveryFeedText.feedNegativeFeedbackNotInterested),
        findsOneWidget,
      );

      // 撤销会恢复原卡片，并把 HotPath 反向行为反馈给服务端。
      expect(find.text(ContentText.undo), findsOneWidget);
      await tester.tap(find.text(ContentText.undo));
      await tester.pumpAndSettle();
      expect(cardFinder, findsOneWidget);
      expect(find.text(_singleRecommendPostBody), findsOneWidget);
      expect(find.text(ContentText.notInterestedUndone), findsOneWidget);

      // 清理撤销成功 toast 的 3s 计时器，避免挂起 Timer。
      await tester.pump(const Duration(seconds: 3));
    });
  });
}
