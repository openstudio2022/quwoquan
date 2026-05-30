import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/discovery/widgets/moment_social_feed.dart';
import 'package:shared_preferences/shared_preferences.dart';

const HomeChannelConfig _following = HomeChannelConfig(
  id: 'following',
  labelKey: 'home_tab_following',
  template: 'single_column_relations',
  feedQuery: <String, String>{'category': 'following', 'identity': 'moment'},
  moodCopyKey: 'home_mood_following',
  order: 0,
);

const HomeChannelConfig _recommend = HomeChannelConfig(
  id: 'recommend',
  labelKey: 'home_tab_recommend',
  template: 'intersection_rail_masonry',
  feedQuery: <String, String>{'category': 'moment', 'identity': 'moment'},
  moodCopyKey: 'home_mood_recommend',
  order: 1,
);

Widget _buildHome(List<HomeChannelConfig> channels) {
  return ProviderScope(
    overrides: [homeChannelsProvider.overrideWithValue(channels)],
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
            GoRoute(path: '/user/:username', builder: (_, _) => const SizedBox()),
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
      await tester.pumpWidget(_buildHome(<HomeChannelConfig>[_following, _recommend]));
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.byKey(HomePrimaryTabStrip.tabKey('following')),
        findsOneWidget,
      );
      expect(
        find.byKey(HomePrimaryTabStrip.tabKey('recommend')),
        findsOneWidget,
      );
      // 默认 7 频道里的垂类不在本覆盖集合中，不应渲染。
      expect(find.byKey(HomePrimaryTabStrip.tabKey('campus')), findsNothing);
      expect(find.byKey(HomePrimaryTabStrip.tabKey('car')), findsNothing);
    });

    testWidgets('默认激活 recommend → body 使用 intersection_rail_masonry 模板', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildHome(<HomeChannelConfig>[_following, _recommend]));
      await tester.pump(const Duration(milliseconds: 300));

      final feed = tester.widget<MomentSocialFeed>(find.byType(MomentSocialFeed));
      expect(feed.feedTabId, 'recommend');
      expect(feed.template, 'intersection_rail_masonry');
    });

    testWidgets('频道集不含 recommend 时回退首个频道 → 单列关系流模板', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildHome(<HomeChannelConfig>[_following]));
      await tester.pump(const Duration(milliseconds: 300));

      final feed = tester.widget<MomentSocialFeed>(find.byType(MomentSocialFeed));
      expect(feed.feedTabId, 'following');
      expect(feed.template, 'single_column_relations');
    });
  });
}
