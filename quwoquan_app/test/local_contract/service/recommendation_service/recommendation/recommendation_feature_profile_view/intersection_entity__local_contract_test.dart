import 'package:flutter/cupertino.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_entity.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show IntersectionObjectKind;

void main() {
  test('聚集对象只接受 canonical gathering wire 值', () {
    expect(
      IntersectionObjectKind.fromWire('gathering', 'objectKind'),
      IntersectionObjectKind.gathering,
    );
    expect(
      () => IntersectionObjectKind.fromWire('trip', 'objectKind'),
      throwsFormatException,
    );
    expect(
      () => IntersectionObjectKind.fromWire('meetup', 'objectKind'),
      throwsFormatException,
    );
  });

  testWidgets('聚集对象使用统一聚集语义图标', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: IntersectionEntity(
            reason: intersectionReasonFixture(
              objectKind: 'gathering',
              displayName: '周末西湖摄影聚集',
              primaryText: '3 位同好计划同行',
            ),
            isDark: false,
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('周末西湖摄影聚集'), findsOneWidget);
    expect(find.text('3 位同好计划同行'), findsOneWidget);
  });
}
