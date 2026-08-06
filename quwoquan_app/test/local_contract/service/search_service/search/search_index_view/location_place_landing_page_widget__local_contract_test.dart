import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/search_location_place_hit_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/location_place_read_query.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/location_place_landing_page.dart';

import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

GoRouter _buildRouter({
  required LocationPlaceReadQuery locationPlaceReadQuery,
  required JourneyEventTracker journeyEventTracker,
}) {
  return GoRouter(
    initialLocation: '/locations/place_west_lake_alley',
    routes: <RouteBase>[
      GoRoute(
        path: '/locations/:placeId',
        builder: (context, state) => LocationPlaceLandingPage(
          placeId: 'place_west_lake_alley',
          placeName: '西湖旁断桥小巷',
          address: '杭州 · 西湖区',
          referralSource: ReferralSource.search,
          locationPlaceReadQuery: locationPlaceReadQuery,
          journeyEventTracker: journeyEventTracker,
        ),
      ),
      GoRoute(
        path: '/homepages/suggest',
        builder: (context, state) => Text(
          'SUGGEST_PROBE:${state.uri.queryParameters['query'] ?? ''}:'
          '${state.uri.queryParameters['sourcePlaceId'] ?? ''}',
        ),
      ),
      GoRoute(
        path: '/homepages/:id',
        builder: (context, state) =>
            Text('HOMEPAGE_PROBE:${state.pathParameters['id']}'),
      ),
    ],
  );
}

GoRouter _buildRecoveryRouter({
  required LocationPlaceReadQuery locationPlaceReadQuery,
  required JourneyEventTracker journeyEventTracker,
}) {
  return GoRouter(
    initialLocation: '/locations/place_west_lake_alley',
    routes: <RouteBase>[
      GoRoute(
        path: '/locations/:placeId',
        builder: (context, state) => LocationPlaceLandingPage(
          placeId: state.pathParameters['placeId']!,
          requiresCanonicalRead: true,
          locationPlaceReadQuery: locationPlaceReadQuery,
          journeyEventTracker: journeyEventTracker,
        ),
      ),
      GoRoute(
        path: '/homepages/:id',
        builder: (context, state) =>
            Text('HOMEPAGE_PROBE:${state.pathParameters['id']}'),
      ),
    ],
  );
}

Future<void> _pumpLanding(
  WidgetTester tester,
  RecordingAppTelemetryRecorder ops,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [appTelemetryReporterProvider.overrideWithValue(ops)],
      child: CupertinoApp.router(
        routerConfig: _buildRouter(
          locationPlaceReadQuery: const _LocationReadQuery(
            LocationPlaceReadUnavailable(),
          ),
          journeyEventTracker: JourneyEventTracker(telemetryReporter: ops),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

final class _LocationReadQuery implements LocationPlaceReadQuery {
  const _LocationReadQuery(this.result);

  final LocationPlaceReadResult result;

  @override
  Future<LocationPlaceReadResult> readById(String placeId) async => result;
}

void main() {
  testWidgets('临时地点卡渲染名称/地址/临时徽标/提升 CTA', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLanding(tester, ops);

    expect(find.byKey(TestKeys.locationPlaceLandingPage), findsOneWidget);
    expect(find.text('西湖旁断桥小巷'), findsOneWidget);
    expect(find.text('杭州 · 西湖区'), findsOneWidget);
    expect(
      find.text(CreationText.locationPlaceLandingTempBadge),
      findsOneWidget,
    );
    expect(
      find.byKey(TestKeys.locationPlaceLandingPromoteButton),
      findsOneWidget,
    );
  });

  testWidgets('提升为实体主页 CTA 跳转 suggestHomepage 并带地点名', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLanding(tester, ops);

    await tester.tap(find.byKey(TestKeys.locationPlaceLandingPromoteButton));
    await tester.pumpAndSettle();

    expect(
      find.text('SUGGEST_PROBE:西湖旁断桥小巷:place_west_lake_alley'),
      findsOneWidget,
    );
  });

  testWidgets('进入页面上报 enter 曝光事件，CTA 上报 promote_click', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLanding(tester, ops);

    expect(ops.recorded.any((e) => e.action == 'enter'), isTrue);

    await tester.tap(find.byKey(TestKeys.locationPlaceLandingPromoteButton));
    await tester.pumpAndSettle();

    expect(ops.recorded.any((e) => e.action == 'promote_click'), isTrue);
  });

  testWidgets('无 extra 的恢复路由按 placeId 读取同一强类型地点视图', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appTelemetryReporterProvider.overrideWithValue(ops)],
        child: CupertinoApp.router(
          routerConfig: _buildRecoveryRouter(
            locationPlaceReadQuery: const _LocationReadQuery(
              LocationPlaceReadFound(
                SearchLocationPlaceHitView(
                  placeId: 'place_west_lake_alley',
                  name: '西湖旁断桥小巷',
                  address: '杭州 · 西湖区',
                ),
              ),
            ),
            journeyEventTracker: JourneyEventTracker(telemetryReporter: ops),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('西湖旁断桥小巷'), findsOneWidget);
    expect(find.text('杭州 · 西湖区'), findsOneWidget);
  });

  testWidgets('已提升地点恢复时跳转实体主页', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appTelemetryReporterProvider.overrideWithValue(ops)],
        child: CupertinoApp.router(
          routerConfig: _buildRecoveryRouter(
            locationPlaceReadQuery: const _LocationReadQuery(
              LocationPlaceReadHomepageRedirect(
                homepageId: 'homepage_west_lake',
              ),
            ),
            journeyEventTracker: JourneyEventTracker(telemetryReporter: ops),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('HOMEPAGE_PROBE:homepage_west_lake'), findsOneWidget);
  });

  testWidgets('不存在地点恢复时显示结构化可返回状态', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appTelemetryReporterProvider.overrideWithValue(ops)],
        child: CupertinoApp.router(
          routerConfig: _buildRecoveryRouter(
            locationPlaceReadQuery: const _LocationReadQuery(
              LocationPlaceReadUnavailable(),
            ),
            journeyEventTracker: JourneyEventTracker(telemetryReporter: ops),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(SearchText.recoveryContentUnavailableTitle), findsWidgets);
    expect(find.text(SearchText.recoveryReturnAction), findsOneWidget);
  });
}
