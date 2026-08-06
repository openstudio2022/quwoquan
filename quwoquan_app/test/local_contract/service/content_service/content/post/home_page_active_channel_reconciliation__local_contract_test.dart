// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/design_system/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show homeChannelsProvider;

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
  final List<String> cancelledChannelIds = <String>[];

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() =>
      <String, AsyncValue<DiscoveryFeedState>>{};

  @override
  void deactivateChannel(String channelId) {
    deactivatedChannelIds.add(channelId);
  }

  @override
  void cancelChannelRequests(String channelId) {
    cancelledChannelIds.add(channelId);
  }
}

class _StateWritingDiscoveryFeedMapNotifier
    extends _RecordingDiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() =>
      <String, AsyncValue<DiscoveryFeedState>>{
        'recommend': const AsyncData(DiscoveryFeedState()),
      };

  @override
  void deactivateChannel(String channelId) {
    super.deactivateChannel(channelId);
    state = Map<String, AsyncValue<DiscoveryFeedState>>.from(state)
      ..remove(channelId);
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

Widget _buildActivityChangingHome(ValueNotifier<bool> isActive) {
  return ProviderScope(
    overrides: [
      homeChannelsProvider.overrideWith(
        (ref) => ref.watch(_testHomeChannelsProvider),
      ),
      discoveryFeedMapProvider.overrideWith(
        _StateWritingDiscoveryFeedMapNotifier.new,
      ),
      isDarkProvider.overrideWithValue(false),
    ],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp(
        home: ValueListenableBuilder<bool>(
          valueListenable: isActive,
          builder: (context, active, _) =>
              HomePage(isStartupHomeActive: active, routeLocation: '/'),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('IndexedStack 切出首页时延后 Provider 写入且不抛 build 异常', (tester) async {
    final isActive = ValueNotifier<bool>(true);
    addTearDown(isActive.dispose);
    await tester.pumpWidget(_buildActivityChangingHome(isActive));
    await tester.pump();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(HomePage)),
    );
    final feedNotifier =
        container.read(discoveryFeedMapProvider.notifier)
            as _StateWritingDiscoveryFeedMapNotifier;

    isActive.value = false;
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(feedNotifier.cancelledChannelIds, contains('recommend'));
    expect(feedNotifier.deactivatedChannelIds, contains('recommend'));
    expect(
      container.read(discoveryFeedMapProvider),
      isNot(contains('recommend')),
    );
  });

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
