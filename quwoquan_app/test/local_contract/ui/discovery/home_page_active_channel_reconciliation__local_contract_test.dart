// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

final _testHomeChannelsProvider =
    NotifierProvider<_TestHomeChannelsNotifier, List<HomeChannelConfig>>(
      _TestHomeChannelsNotifier.new,
    );

class _TestHomeChannelsNotifier extends Notifier<List<HomeChannelConfig>> {
  @override
  List<HomeChannelConfig> build() => <HomeChannelConfig>[
    _channel('recommend'),
    _channel('travel'),
    _channel('car'),
  ];

  void replaceWith(List<HomeChannelConfig> channels) {
    state = channels;
  }
}

class _RecordingDiscoveryFeedMapNotifier extends DiscoveryFeedMapNotifier {
  final List<String> deactivatedChannelIds = <String>[];

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() =>
      <String, AsyncValue<DiscoveryFeedState>>{};

  @override
  void deactivateChannel(String channelId) {
    deactivatedChannelIds.add(channelId);
  }
}

HomeChannelConfig _channel(String id) =>
    ContentUIConfig.homeChannels.firstWhere((channel) => channel.id == id);

Widget _buildHome() {
  return ProviderScope(
    overrides: [
      homeChannelsProvider.overrideWith(
        (ref) => ref.watch(_testHomeChannelsProvider),
      ),
      discoveryFeedMapProvider.overrideWith(
        _RecordingDiscoveryFeedMapNotifier.new,
      ),
      isDarkProvider.overrideWithValue(false),
    ],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: const MaterialApp(
        home: HomePage(isStartupHomeActive: false, routeLocation: '/'),
      ),
    ),
  );
}

void main() {
  testWidgets('远端移除当前频道后同步真实 active 状态，后续 swipe 回收展示频道', (tester) async {
    await tester.pumpWidget(_buildHome());
    await tester.pump();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(HomePage)),
    );
    final channels = container.read(_testHomeChannelsProvider.notifier);
    final feedNotifier =
        container.read(discoveryFeedMapProvider.notifier)
            as _RecordingDiscoveryFeedMapNotifier;

    expect(
      tester
          .widget<HomePrimaryTabStrip>(find.byType(HomePrimaryTabStrip))
          .activeChannelId,
      'recommend',
    );

    channels.replaceWith(<HomeChannelConfig>[
      _channel('travel'),
      _channel('car'),
    ]);
    await tester.pump();
    await tester.pump();

    expect(
      tester
          .widget<HomePrimaryTabStrip>(find.byType(HomePrimaryTabStrip))
          .activeChannelId,
      'travel',
    );
    expect(feedNotifier.deactivatedChannelIds, <String>['recommend']);

    tester
        .widget<TabSwipeSwitchRegion>(find.byType(TabSwipeSwitchRegion))
        .onSwipe(TabSwipeDirection.next);
    await tester.pump();

    expect(
      tester
          .widget<HomePrimaryTabStrip>(find.byType(HomePrimaryTabStrip))
          .activeChannelId,
      'car',
    );
    expect(feedNotifier.deactivatedChannelIds, <String>['recommend', 'travel']);
  });
}
