// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004

import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show appTelemetryContextProvider;
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/runtime/transport/cloud_retry_policy.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/design_system/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

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

class _AutomaticRecoveryFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _AutomaticRecoveryFeedMapNotifier(this.failure);

  RuntimeFailure failure;
  int forceLoadCalls = 0;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() =>
      <String, AsyncValue<DiscoveryFeedState>>{
        'recommend': AsyncData(DiscoveryFeedState(blockingError: failure)),
      };

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async {
    if (force) {
      forceLoadCalls += 1;
    }
    return DiscoveryFeedLoadResult(
      terminal: DiscoveryFeedLoadTerminal.stillBlocked,
      generation: forceLoadCalls,
      failure: failure,
    );
  }

  void replaceBlockingFailure(RuntimeFailure next) {
    failure = next;
    state = <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(DiscoveryFeedState(blockingError: next)),
    };
  }
}

class _RecordingAppRemoteConfigNotifier extends AppRemoteConfigNotifier {
  int refreshCalls = 0;

  @override
  AppRemoteConfigState build() => AppRemoteConfigState(
    active: buildProductionContentRuntimeConfigDefaults(),
  );

  @override
  Future<void> refresh() async {
    refreshCalls += 1;
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
      appRemoteConfigProvider.overrideWith(
        _RecordingAppRemoteConfigNotifier.new,
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
      appRemoteConfigProvider.overrideWith(
        _RecordingAppRemoteConfigNotifier.new,
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

RuntimeFailure _transientFeedFailure(RuntimeFailureKind kind) {
  return RuntimeFailure(
    code: kind == RuntimeFailureKind.timeout
        ? RuntimeFailureCodes.appTimeoutRequestTimeout
        : RuntimeFailureCodes.appNetworkOffline,
    semanticReason: 'home_automatic_recovery_test',
    origin: RuntimeFailureOrigin.localClient,
    kind: kind,
    nature: RuntimeFailureNature.transient,
    location: const RuntimeFailureLocation(
      businessObject: 'content.discovery_feed',
      functionModule: 'home_page',
    ),
    context: const RuntimeFailureContext(),
  );
}

Future<
  ({
    StreamController<List<ConnectivityResult>> connectivity,
    ProviderContainer container,
    _AutomaticRecoveryFeedMapNotifier feed,
    _RecordingAppRemoteConfigNotifier config,
  })
>
_pumpRecoveryHome(
  WidgetTester tester, {
  required RuntimeFailure failure,
}) async {
  final connectivity = StreamController<List<ConnectivityResult>>.broadcast();
  final telemetryContext = AppTelemetryContextProvider(
    staticContextLoader: () async => const AppTelemetryStaticContext(
      deviceManufacturer: 'test',
      deviceModel: 'test',
      appVersion: 'test',
      devicePlatform: 'ios',
    ),
    connectivityLoader: () async => const <ConnectivityResult>[
      ConnectivityResult.none,
    ],
    connectivityChanges: connectivity.stream,
  );
  await telemetryContext.initialize();
  addTearDown(telemetryContext.dispose);
  addTearDown(connectivity.close);

  final feed = _AutomaticRecoveryFeedMapNotifier(failure);
  final config = _RecordingAppRemoteConfigNotifier();
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        homeChannelsProvider.overrideWith(
          (ref) => ref.watch(_testHomeChannelsProvider),
        ),
        discoveryFeedMapProvider.overrideWith(() => feed),
        appRemoteConfigProvider.overrideWith(() => config),
        appTelemetryContextProvider.overrideWithValue(telemetryContext),
        isDarkProvider.overrideWithValue(false),
      ],
      child: ScreenUtilInit(
        designSize: const Size(393, 852),
        child: const MaterialApp(
          home: HomePage(isStartupHomeActive: true, routeLocation: '/'),
        ),
      ),
    ),
  );
  await tester.pump();
  final container = ProviderScope.containerOf(
    tester.element(find.byType(HomePage)),
  );
  return (
    connectivity: connectivity,
    container: container,
    feed: feed,
    config: config,
  );
}

void main() {
  testWidgets('typed timeout 终态按 canonical backoff 自动重取一次且不轮询', (tester) async {
    final harness = await _pumpRecoveryHome(
      tester,
      failure: _transientFeedFailure(RuntimeFailureKind.timeout),
    );

    await tester.pump(const CloudRetryPolicy().maxBackoff);
    await tester.pump();

    expect(harness.config.refreshCalls, 1);
    expect(harness.feed.forceLoadCalls, 1);

    await tester.pump(const Duration(seconds: 5));
    expect(harness.config.refreshCalls, 1);
    expect(harness.feed.forceLoadCalls, 1);
  });

  testWidgets('网络恢复仅自动重取一次 config/feed，失败后保留手动恢复终态', (tester) async {
    final harness = await _pumpRecoveryHome(
      tester,
      failure: _transientFeedFailure(RuntimeFailureKind.timeout),
    );

    harness.connectivity.add(const <ConnectivityResult>[
      ConnectivityResult.wifi,
    ]);
    await tester.pump();
    await tester.pump();

    expect(harness.config.refreshCalls, 1);
    expect(harness.feed.forceLoadCalls, 1);
    expect(
      harness.container
          .read(discoveryFeedMapProvider)['recommend']
          ?.value
          ?.blockingError,
      isNotNull,
    );

    harness.connectivity.add(const <ConnectivityResult>[
      ConnectivityResult.ethernet,
    ]);
    await tester.pump();
    await tester.pump();

    expect(harness.config.refreshCalls, 1);
    expect(harness.feed.forceLoadCalls, 1);

    harness.feed.replaceBlockingFailure(
      _transientFeedFailure(RuntimeFailureKind.timeout),
    );
    harness.connectivity.add(const <ConnectivityResult>[
      ConnectivityResult.wifi,
    ]);
    await tester.pump();
    await tester.pump();

    expect(harness.config.refreshCalls, 2);
    expect(harness.feed.forceLoadCalls, 2);
  });

  testWidgets('前后台恢复对同一 transient 阻断态也至多自动重取一次', (tester) async {
    final harness = await _pumpRecoveryHome(
      tester,
      failure: _transientFeedFailure(RuntimeFailureKind.network),
    );

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump();

    expect(harness.config.refreshCalls, 1);
    expect(harness.feed.forceLoadCalls, 1);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump();

    expect(harness.config.refreshCalls, 1);
    expect(harness.feed.forceLoadCalls, 1);
  });

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
