@Tags(<String>['serial', 'visual'])
library;

import 'package:flutter/cupertino.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_intersection_card.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';

void main() {
  setUpAll(() async {
    final loader = FontLoader('Noto Sans SC')
      ..addFont(
        rootBundle.load('assets/fonts/noto_sans_sc/NotoSansSC[wght].ttf'),
      );
    await loader.load();
  });

  testWidgets('alpha host_plain 对象交集卡保持丰富态', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final reasons = await InMemoryIntersectionRepository()
        .getObjectIntersections(
          objectId: 'fixture_homepage_travel_route_erhai',
          objectType: 'entity',
        );
    final hostTarget = intersectionTargetFixture(
      objectType: 'homepage',
      objectId: 'fixture_homepage_travel_route_erhai',
      objectKind: 'route',
      routeId: 'homepageDetail',
    );
    const boundaryKey = ValueKey<String>('alpha-intersection-golden-boundary');

    await tester.pumpWidget(
      CupertinoApp(
        theme: const CupertinoThemeData(
          brightness: Brightness.light,
          textTheme: CupertinoTextThemeData(
            textStyle: TextStyle(fontFamily: 'Noto Sans SC'),
          ),
        ),
        home: CupertinoPageScaffold(
          child: RepaintBoundary(
            key: boundaryKey,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Align(
                  alignment: Alignment.topCenter,
                  child: ObjectIntersectionCard.fromReasons(
                    title: '你和这里的交集',
                    reasons: reasons,
                    isDark: false,
                    contextObjectTarget: hostTarget,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(ObjectIntersectionCard), findsOneWidget);
    await expectLater(
      find.byKey(boundaryKey),
      matchesGoldenFile('goldens/object_intersection_host_plain.png'),
    );
  });
}
