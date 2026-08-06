import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show homeChannelsProvider;
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

const HomeChannelConfig _following = HomeChannelConfig(
  id: 'following',
  labelKey: 'home_tab_following',
  template: 'single_column_relations',
  layoutTemplate: 'singleColumnRelations',
  phoneColumns: 1,
  supportsFullSpanModules: false,
  intersectionModulePolicy: 'none',
  contentCardPolicy: 'richRelation',
  feedQuery: <String, String>{'category': 'following', 'identity': 'moment'},
  moodCopyKey: 'home_mood_following',
  order: 0,
);

const HomeChannelConfig _recommend = HomeChannelConfig(
  id: 'recommend',
  labelKey: 'home_tab_recommend',
  template: 'intersection_rail_masonry',
  layoutTemplate: 'dualColumnDiscovery',
  phoneColumns: 2,
  supportsFullSpanModules: true,
  intersectionModulePolicy: 'spotlightSegment',
  contentCardPolicy: 'compactVisual',
  feedQuery: <String, String>{'category': 'micro', 'identity': 'moment'},
  moodCopyKey: 'home_mood_recommend',
  order: 1,
);

Widget _buildHome(List<HomeChannelConfig> channels) {
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(MockContentRepository()),
      homeChannelsProvider.overrideWithValue(channels),
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
            GoRoute(path: '/search', builder: (_, _) => const SizedBox()),
            GoRoute(
              path: '/user/:userHandle',
              builder: (_, _) => const SizedBox(),
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

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('首页频道运营驱动（端默认 + 远程覆盖）', () {
    testWidgets('strip 仅渲染 provider 提供的频道（运营覆盖后频道集随之变化）', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildHome(<HomeChannelConfig>[_following, _recommend]),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.byKey(HomePrimaryTabStrip.channelKey('following')),
        findsOneWidget,
      );
      expect(
        find.byKey(HomePrimaryTabStrip.channelKey('recommend')),
        findsOneWidget,
      );
      // 默认 7 频道里的垂类不在本覆盖集合中，不应渲染。
      expect(
        find.byKey(HomePrimaryTabStrip.channelKey('campus')),
        findsNothing,
      );
      expect(find.byKey(HomePrimaryTabStrip.channelKey('car')), findsNothing);
    });

    testWidgets('默认激活 recommend → body 使用双列发现布局策略', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildHome(<HomeChannelConfig>[_following, _recommend]),
      );
      await tester.pump(const Duration(milliseconds: 300));

      final feed = tester.widget<HomeMultiFormFeed>(
        find.byType(HomeMultiFormFeed),
      );
      expect(feed.channelId, 'recommend');
      expect(feed.template, 'intersection_rail_masonry');
    });

    testWidgets('频道集不含 recommend 时回退首个频道 → 单列关系流模板', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildHome(<HomeChannelConfig>[_following]));
      await tester.pump(const Duration(milliseconds: 300));

      final feed = tester.widget<HomeMultiFormFeed>(
        find.byType(HomeMultiFormFeed),
      );
      expect(feed.channelId, 'following');
      expect(feed.template, 'single_column_relations');
    });
  });
}
