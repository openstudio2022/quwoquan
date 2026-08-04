import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import '../../../../support/fixtures/intersection_fixtures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/object_page/intersection_entity.dart';

void main() {
  test('聚集对象只接受 canonical gathering wire 值', () {
    expect(
      UnifiedObjectKind.fromWire('gathering'),
      UnifiedObjectKind.gathering,
    );
    expect(UnifiedObjectKind.fromWire('trip'), isNull);
    expect(UnifiedObjectKind.fromWire('meetup'), isNull);
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
              dimension: 'interest',
            ),
            isDark: false,
          ),
        ),
      ),
    );

    expect(find.byIcon(CupertinoIcons.person_2_fill), findsOneWidget);
  });
}
