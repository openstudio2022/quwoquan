import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/search/pages/location_place_landing_page.dart';

import '../../../../support/recording_app_telemetry_recorder.dart';

GoRouter _buildRouter() {
  return GoRouter(
    initialLocation: '/locations/place_west_lake_alley',
    routes: <RouteBase>[
      GoRoute(
        path: '/locations/:placeId',
        builder: (context, state) => const LocationPlaceLandingPage(
          placeId: 'place_west_lake_alley',
          placeName: '西湖旁断桥小巷',
          address: '杭州 · 西湖区',
          referralSource: ReferralSource.search,
        ),
      ),
      GoRoute(
        path: '/homepages/suggest',
        builder: (context, state) =>
            Text('SUGGEST_PROBE:${state.uri.queryParameters['query'] ?? ''}'),
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
      child: CupertinoApp.router(routerConfig: _buildRouter()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('临时地点卡渲染名称/地址/临时徽标/提升 CTA', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLanding(tester, ops);

    expect(find.byKey(TestKeys.locationPlaceLandingPage), findsOneWidget);
    expect(find.text('西湖旁断桥小巷'), findsOneWidget);
    expect(find.text('杭州 · 西湖区'), findsOneWidget);
    expect(
      find.text(UITextConstants.locationPlaceLandingTempBadge),
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

    expect(find.text('SUGGEST_PROBE:西湖旁断桥小巷'), findsOneWidget);
  });

  testWidgets('进入页面上报 enter 曝光事件，CTA 上报 promote_click', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLanding(tester, ops);

    expect(ops.recorded.any((e) => e.action == 'enter'), isTrue);

    await tester.tap(find.byKey(TestKeys.locationPlaceLandingPromoteButton));
    await tester.pumpAndSettle();

    expect(ops.recorded.any((e) => e.action == 'promote_click'), isTrue);
  });
}
