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
import 'package:quwoquan_app/ui/discovery/widgets/moment_social_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

class _StableFollowingArticleContentRepository extends MockContentRepository {
  @override
  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix() {
    return <PostBaseDto>[
      _articlePost(
        id: 'web-dev',
        title: '给新同事的 Web 工程工具清单',
        body: '从构建、调试到部署，把最容易漏掉的环节集中整理成一页。',
        coverUrl: 'https://example.com/article-web-dev-cover.jpg',
      ),
      _articlePost(
        id: 'ritual_plain',
        title: '晨间复盘的十分钟礼记',
        body: '把前一天的情绪、节奏和待办留在固定版式里，早晨更容易进入状态。',
      ),
      _articlePost(
        id: 'diffuse_cover_body_only',
        body: '把路线、风向和停留时间直接写进正文里，让临场决定也能保持连贯。',
        coverUrl: 'https://example.com/article-diffuse-cover.jpg',
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
      await tester.pumpAndSettle();

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
        HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.recommendedChannelId),
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

    testWidgets('浅色首页一级 Tab 与列表露底使用 post 表面色', (tester) async {
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
      final listBackground = tester.widget<ColoredBox>(
        find
            .ancestor(
              of: find.byType(ListView),
              matching: find.byType(ColoredBox),
            )
            .first,
      );

      expect(tabChrome.decoration, isA<BoxDecoration>());
      expect((tabChrome.decoration! as BoxDecoration).color, expectedSurface);
      expect((tabChrome.decoration! as BoxDecoration).border, isNull);
      expect(listBackground.color, expectedSurface);
    });

    testWidgets('首页 post 之间使用消息列表同源分割线', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final divider = tester.widget<Divider>(
        find.byKey(const ValueKey<String>('moment-feed-divider-0')),
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

      expect(find.byType(MomentSocialFeed), findsOneWidget);
      expect(find.byType(HomePrimaryTabStrip), findsOneWidget);
      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.recommendedChannelId),
        ),
        findsOneWidget,
      );
    });

    testWidgets('点击关注 tab 不触发无效路由跳转', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.followingChannelId),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Page Not Found'), findsNothing);
      expect(find.byType(HomePage), findsOneWidget);
      expect(find.byType(MomentSocialFeed), findsOneWidget);
    });

    testWidgets('关注流手机端首条 post 占满屏宽', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(
        const ValueKey<String>('moment-feed-card-0'),
      );
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
        find.byKey(const ValueKey<String>('moment-feed-more-0')),
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

    testWidgets('关注流宽屏下首条 post 收敛到最大宽度', (tester) async {
      _suppressExpectedErrors();
      _setWideSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(
        const ValueKey<String>('moment-feed-card-0'),
      );
      final screenWidth =
          tester.view.physicalSize.width / tester.view.devicePixelRatio;

      expect(cardFinder, findsOneWidget);
      expect(tester.getSize(cardFinder).width, lessThan(screenWidth));
      final ctx = tester.element(cardFinder);
      final cols = AppSpacing.feedResponsiveColumns(ctx);
      final pad = AppSpacing.feedContentHorizontal(ctx);
      final gap = AppSpacing.postPreviewGridSpacing;
      final expected =
          (MediaQuery.sizeOf(ctx).width - 2 * pad - (cols - 1) * gap) / cols;
      expect(tester.getSize(cardFinder).width, closeTo(expected, 1.0));
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

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(const ValueKey<String>('moment-feed-more-0')),
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
      expect(find.text('保存'), findsOneWidget);
      expect(find.text('私信'), findsOneWidget);
      expect(find.text('复制链接'), findsOneWidget);
      expect(find.text('字体设置'), findsOneWidget);
      expect(find.text('取消'), findsOneWidget);
      expect(find.text('分享'), findsNothing);
      expect(find.text('查看原图'), findsNothing);

      await tester.drag(find.byType(ListView).last, const Offset(-320, 0));
      await tester.pumpAndSettle();

      expect(find.text('功能反馈'), findsOneWidget);
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
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.followingChannelId),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(
          HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.recommendedChannelId),
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

      expect(find.byType(HomePrimaryTabStrip), findsOneWidget);
      expect(find.byType(WorksImmersiveViewer), findsOneWidget);
      expect(exited, isFalse);
    });

    testWidgets('横滑校园内容切到旅行频道', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId)),
      );
      await tester.pumpAndSettle();

      final firstCard = find.byKey(
        const ValueKey<String>('moment-feed-card-0'),
      );
      expect(firstCard, findsOneWidget);

      await tester.flingFrom(
        tester.getCenter(firstCard),
        const Offset(-320, 0),
        1400,
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId)),
        findsOneWidget,
      );
    });

    testWidgets('切到旅行后主 tab 位置保持稳定', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final campusBefore = tester.getCenter(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId)),
      );
      final travelBefore = tester.getCenter(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId)),
      );
      final campusTopBefore = tester.getTopLeft(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId)),
      );
      final travelTopBefore = tester.getTopLeft(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId)),
      );
      await tester.tap(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId)),
      );
      await tester.pumpAndSettle();

      final campusAfter = tester.getCenter(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId)),
      );
      final travelAfter = tester.getCenter(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId)),
      );
      final campusTopAfter = tester.getTopLeft(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.campusChannelId)),
      );
      final travelTopAfter = tester.getTopLeft(
        find.byKey(HomePrimaryTabStrip.channelKey(HomePrimaryTabStrip.travelChannelId)),
      );
      expect(campusAfter.dx, closeTo(campusBefore.dx, 0.1));
      expect(travelAfter.dx, closeTo(travelBefore.dx, 0.1));
      expect(campusTopAfter.dy, closeTo(campusTopBefore.dy, 0.1));
      expect(travelTopAfter.dy, closeTo(travelTopBefore.dy, 0.1));
    });
  });
}
