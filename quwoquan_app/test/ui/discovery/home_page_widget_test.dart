import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_multi_form_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

Widget _buildApp() {
  return ProviderScope(
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
              builder: (context, state) => const GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:username',
              builder: (context, state) => const SizedBox(),
            ),
          ],
        ),
      ),
    ),
  );
}

Widget _buildDarkApp() {
  return ProviderScope(
    overrides: [isDarkProvider.overrideWith((ref) => true)],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        theme: ThemeData.dark(),
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
              builder: (context, state) => const GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:username',
              builder: (_, _) => const SizedBox(),
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
      contentRepositoryProvider.overrideWithValue(
        _StableFollowingArticleContentRepository(),
      ),
      contentFeatureFlagProvider(
        'enable_article_distribution_profiles',
      ).overrideWith((ref) => true),
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
              builder: (context, state) => const GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:username',
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
      if (stableArticles) ...[
        contentRepositoryProvider.overrideWithValue(
          _StableFollowingArticleContentRepository(),
        ),
        contentFeatureFlagProvider(
          'enable_article_distribution_profiles',
        ).overrideWith((ref) => true),
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
              builder: (context, state) => const GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:username',
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
      activeSubAccountId: 'test-sub-account',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

class _StableFollowingArticleContentRepository extends MockContentRepository {
  @override
  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix() {
    return <PostBaseDto>[
      _articlePost(
        id: 'web-dev',
        title: '给新同事的 Web 工程工具清单',
        body: '从构建、调试到部署，把最容易漏掉的环节集中整理成一页。',
        coverUrl:
            'media/image/s/archived-image/post/fixture_article_001/v1/cover.png',
      ),
      _articlePost(
        id: 'ritual_plain',
        title: '晨间复盘的十分钟礼记',
        body: '把前一天的情绪、节奏和待办留在固定版式里，早晨更容易进入状态。',
      ),
      _articlePost(
        id: 'diffuse_cover_body_only',
        body: '把路线、风向和停留时间直接写进正文里，让临场决定也能保持连贯。',
        coverUrl:
            'media/image/s/archived-image/post/fixture_article_001/v1/image-2.png',
      ),
      _articlePost(
        id: 'journal_plain_body_only',
        body: '没有标题也没有封面，仍然可以用正文首句承接整张卡片的信息层级。',
      ),
    ];
  }

  PostBaseDto _articlePost({
    required String id,
    String title = '',
    required String body,
    String coverUrl = '',
  }) {
    return postBaseDtoFromMap(<String, dynamic>{
      'id': id,
      '_id': id,
      'postId': id,
      'contentType': 'article',
      'type': 'article',
      'authorId': 'fixture_user_current',
      'displayName': '测试作者',
      'title': title,
      'body': body,
      'coverUrl': coverUrl,
      'imageUrl': coverUrl,
      'mediaCoverUrl': coverUrl,
      'createdAt': '2026-05-01T08:00:00Z',
      'articleTemplate': id == 'ritual_plain'
          ? 'ritual'
          : id == 'diffuse_cover_body_only'
          ? 'diffuse'
          : id == 'journal_plain_body_only'
          ? 'journal'
          : 'tech',
    });
  }
}

class _StableFollowingDiscoveryFeedMapNotifier
    extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'following': const AsyncData(
        DiscoveryFeedState(
          items: <PostBaseDto>[],
          seenItemIds: <String>[],
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

PostBaseDto _singleRecommendPost() {
  return postBaseDtoFromMap(<String, dynamic>{
    'id': _singleRecommendPostId,
    '_id': _singleRecommendPostId,
    'postId': _singleRecommendPostId,
    'contentType': 'micro',
    'type': 'micro',
    'authorId': 'fixture_user_current',
    'subAccountId': 'fixture_user_current',
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
          items: <PostBaseDto>[_singleRecommendPost()],
          seenItemIds: const <String>[],
          nextCursor: null,
          isLoading: false,
        ),
      ),
    };
  }

  // 禁用真实拉取：移除卡片后保持空态，避免 mock 仓储回填打散断言。
  @override
  Future<void> load(String channelId, {bool force = false}) async {}
}

Widget _buildAppWithSingleRecommendPost() {
  return ProviderScope(
    overrides: [
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
              builder: (context, state) => const GlobalSearchPage(
                launchContext: SearchLaunchContext(entrySurfaceId: '/'),
              ),
            ),
            GoRoute(
              path: '/user/:username',
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
    testWidgets('展示首页频道与小趣搜入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(HomePage), findsOneWidget);
      expect(find.text(UITextConstants.homeTabFollowing), findsWidgets);
      expect(find.text(UITextConstants.homeTabRecommended), findsWidgets);
      expect(find.text(UITextConstants.circleScenarioCampus), findsWidgets);
      expect(find.text(UITextConstants.homeTabTravel), findsWidgets);
      expect(find.text(UITextConstants.homeTabPhotography), findsWidgets);
      expect(find.text(UITextConstants.homeTabTech), findsWidgets);
      expect(find.text(UITextConstants.homeTabCarFriends), findsWidgets);
      expect(
        find.text(UITextConstants.circleScenarioTravelPhotography),
        findsNothing,
      );
      expect(find.byIcon(CupertinoIcons.search), findsAtLeastNWidgets(1));
      expect(find.byIcon(CupertinoIcons.sparkles), findsAtLeastNWidgets(1));
    });

    testWidgets('首页小趣搜入口保留统一全屏搜索启动器', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(_buildApp());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byKey(TestKeys.globalSearchLauncherButton), findsOneWidget);
      expect(find.text(UITextConstants.globalXiaoquSearchHint), findsOneWidget);
      expect(find.text(UITextConstants.globalXiaoquSearchAsk), findsOneWidget);
      expect(
        tester.getSize(find.byKey(TestKeys.globalAssistantEntryMark)),
        const Size.square(AppSpacing.globalAssistantEntryMarkSize),
      );
      final assistantMarkRect = tester.getRect(
        find.byKey(TestKeys.globalAssistantEntryMark),
      );
      final assistantLabelRect = tester.getRect(
        find.text(UITextConstants.globalXiaoquSearchAsk),
      );
      expect(
        assistantLabelRect.top - assistantMarkRect.bottom,
        moreOrLessEquals(
          AppSpacing.globalAssistantEntryLabelGap,
          epsilon: AppSpacing.hairline,
        ),
      );
    });

    testWidgets('浅色首页状态栏和搜索区使用品牌蓝沉浸背景', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      tester.view.viewPadding = const FakeViewPadding(top: 59, bottom: 34);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewPadding);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final chrome = tester.widget<Container>(
        find.byKey(const ValueKey<String>('home-search-chrome')),
      );
      expect(chrome.color, AppColors.primaryColor);
      expect(
        tester
            .widget<GlobalXiaoquSearchBar>(find.byType(GlobalXiaoquSearchBar))
            .surface,
        AppChromeSurface.immersive,
      );
      final searchField = tester
          .widgetList<Container>(
            find.descendant(
              of: find.byType(GlobalXiaoquSearchBar),
              matching: find.byType(Container),
            ),
          )
          .firstWhere((widget) => widget.decoration is BoxDecoration);
      final searchFieldDecoration = searchField.decoration! as BoxDecoration;
      expect(
        searchFieldDecoration.color,
        AppColorsFunctional.getColor(
          false,
          ColorType.globalSearchFieldBackground,
        ),
      );
      final searchHint = tester.widget<Text>(
        find.text(UITextConstants.globalXiaoquSearchHint),
      );
      final searchIcon = tester.widget<Icon>(
        find
            .descendant(
              of: find.byType(GlobalXiaoquSearchBar),
              matching: find.byIcon(CupertinoIcons.search),
            )
            .first,
      );
      expect(
        searchHint.style?.color,
        AppColorsFunctional.getColor(false, ColorType.foregroundSecondary),
      );
      expect(
        searchIcon.color,
        AppColorsFunctional.getColor(false, ColorType.foregroundSecondary),
      );
      final overlay = tester.widget<AnnotatedRegion<SystemUiOverlayStyle>>(
        find
            .descendant(
              of: find.byType(HomePage),
              matching: find.byType(AnnotatedRegion<SystemUiOverlayStyle>),
            )
            .first,
      );
      expect(overlay.value.statusBarIconBrightness, Brightness.light);
      expect(overlay.value.statusBarBrightness, Brightness.dark);
    });

    testWidgets('深色首页搜索输入框使用低对比语义背景', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildDarkApp());
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<GlobalXiaoquSearchBar>(find.byType(GlobalXiaoquSearchBar))
            .surface,
        AppChromeSurface.immersive,
      );
      final searchField = tester
          .widgetList<Container>(
            find.descendant(
              of: find.byType(GlobalXiaoquSearchBar),
              matching: find.byType(Container),
            ),
          )
          .firstWhere((widget) => widget.decoration is BoxDecoration);
      final decoration = searchField.decoration! as BoxDecoration;
      expect(
        decoration.color,
        AppColorsFunctional.getColor(
          true,
          ColorType.globalSearchFieldBackground,
        ),
      );
      expect(decoration.color, isNot(AppColors.white));
    });

    testWidgets('首页搜索框避开安全区并使用 post 正文字号', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      tester.view.viewPadding = const FakeViewPadding(top: 59, bottom: 34);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewPadding);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final page = tester.element(find.byType(HomePage));
      final searchBar = find.byType(GlobalXiaoquSearchBar);
      final stripTop = tester.getTopLeft(find.byType(HomePrimaryTabStrip)).dy;
      final searchTop = tester.getTopLeft(searchBar).dy;
      final searchSize = tester.getSize(searchBar);
      final searchHint = tester.widget<Text>(
        find.text(UITextConstants.globalXiaoquSearchHint),
      );
      final safeTop =
          tester.view.viewPadding.top / tester.view.devicePixelRatio;
      final expectedTopInset = safeTop + AppSpacing.intraGroupXs;
      final searchHeight = AppSpacing.globalSearchFieldHeight;
      final searchToTabGap = AppSpacing.intraGroupXs;
      final navHeight = AppSpacing.primaryTopBarHeight(page);

      expect(searchTop, greaterThanOrEqualTo(expectedTopInset));
      expect(searchSize.height, equals(searchHeight));
      expect(
        searchHint.style?.fontSize,
        equals(AppTypography.feedBodyResponsive(page)),
      );
      expect(
        stripTop,
        greaterThanOrEqualTo(expectedTopInset + searchHeight + searchToTabGap),
      );
      expect(
        stripTop,
        lessThanOrEqualTo(
          expectedTopInset + searchHeight + searchToTabGap + navHeight,
        ),
      );
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
              matching: find.text(UITextConstants.homeTabRecommended),
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
        SettingsSemanticConstants.conversationSheetDividerColor(
          false,
        ).withValues(alpha: 0.9),
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
      final bodyOnlyCoverCard = find.byKey(
        const ValueKey<String>(
          'following-article-card-diffuse_cover_body_only',
        ),
      );
      final bodyOnlyTextCard = find.byKey(
        const ValueKey<String>(
          'following-article-card-journal_plain_body_only',
        ),
      );

      await _scrollUntilFinderVisible(tester, scrollable, coverCard);
      await tester.pumpAndSettle();
      expect(coverCard, findsOneWidget);
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
      expect(
        find.descendant(
          of: textOnlyCard,
          matching: find.byKey(
            const ValueKey<String>('following-article-thumbnail-ritual_plain'),
          ),
        ),
        findsNothing,
      );

      await _scrollUntilFinderVisible(tester, scrollable, bodyOnlyCoverCard);
      await tester.pumpAndSettle();
      expect(bodyOnlyCoverCard, findsOneWidget);
      expect(
        find.descendant(
          of: bodyOnlyCoverCard,
          matching: find.byKey(
            const ValueKey<String>(
              'following-article-thumbnail-diffuse_cover_body_only',
            ),
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: bodyOnlyCoverCard,
          matching: find.textContaining('把路线、风向和停留时间直接写进正文里'),
        ),
        findsOneWidget,
      );

      await _scrollUntilFinderVisible(tester, scrollable, bodyOnlyTextCard);
      await tester.pumpAndSettle();
      expect(bodyOnlyTextCard, findsOneWidget);
      expect(
        find.descendant(
          of: bodyOnlyTextCard,
          matching: find.byKey(
            const ValueKey<String>(
              'following-article-thumbnail-journal_plain_body_only',
            ),
          ),
        ),
        findsNothing,
      );
      expect(
        find.descendant(
          of: bodyOnlyTextCard,
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
      expect(find.text('打赏'), findsOneWidget);
      expect(find.text('私信'), findsOneWidget);
      expect(find.text('复制链接'), findsOneWidget);
      expect(find.text('字体设置'), findsOneWidget);
      expect(find.text('取消'), findsOneWidget);
      expect(find.text('分享'), findsNothing);
      expect(find.text('查看原图'), findsNothing);

      await tester.drag(
        find.byKey(TestKeys.modalBottomSheetQuickActionsRail),
        const Offset(-320, 0),
      );
      await tester.pumpAndSettle();

      expect(find.text('功能反馈'), findsOneWidget);
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

    testWidgets('全局搜索以全屏面板呈现', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(TestKeys.globalSearchLauncherButton));
      await tester.pumpAndSettle();

      final searchPanel = find.byKey(TestKeys.fullscreenModalSurface);
      final logicalSize =
          tester.view.physicalSize / tester.view.devicePixelRatio;

      expect(searchPanel, findsOneWidget);
      expect(tester.getSize(searchPanel), equals(logicalSize));
    });

    testWidgets('首页一级频道包含关注推荐与五个业务垂类', (tester) async {
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
      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.featuredChannelId),
        ),
        findsNothing,
      );
    });

    testWidgets('精品沉浸页独立承接全屏作品体验', (tester) async {
      _suppressExpectedErrors();
      var exited = false;
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: HomeFeaturedImmersivePage(
                onExitToHome: () => exited = true,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // V1.0：顶部不再有形态分段，仅保留返回与更多。
      expect(
        find.byKey(const ValueKey<String>('works-format-tab-strip')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('works-top-back')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('works-top-more')),
        findsOneWidget,
      );
      expect(find.byType(WorksImmersiveViewer), findsOneWidget);
      expect(exited, isFalse);
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

      final firstCard = find.byKey(
        const ValueKey<String>('home-feed-card-0'),
      );
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

    testWidgets('推荐流不感兴趣即时移除卡片并给出降级提示', (tester) async {
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

      final notInterested = find.text(AppStrings.notInterested);
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

      // 清理 toast 的 3s 计时器，避免挂起 Timer。
      await tester.pump(const Duration(seconds: 3));
    });
  });
}
