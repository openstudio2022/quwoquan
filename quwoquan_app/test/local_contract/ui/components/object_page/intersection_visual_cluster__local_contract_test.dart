import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';

Widget _host(Widget child) =>
    CupertinoApp(home: CupertinoPageScaffold(child: Center(child: child)));

void main() {
  group('IntersectionVisualCluster 按 assetKind 渲染', () {
    testWidgets('visuals 为空 → 隐藏', (tester) async {
      await tester.pumpWidget(
        _host(IntersectionVisualCluster(visuals: <IntersectionVisual>[])),
      );

      expect(
        find.descendant(
          of: find.byType(IntersectionVisualCluster),
          matching: find.byType(Icon),
        ),
        findsNothing,
      );
    });

    testWidgets('avatar 无图回退圆形人像图标、cover 回退照片图标', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionVisualCluster(
            visuals: <IntersectionVisual>[
              IntersectionVisual(assetKind: 'avatar', displayName: '林清越'),
              IntersectionVisual(assetKind: 'cover', displayName: '黄金投资圈'),
            ],
          ),
        ),
      );

      expect(
        find.byIcon(CupertinoIcons.person_crop_circle_fill),
        findsOneWidget,
      );
      expect(find.byIcon(CupertinoIcons.photo_fill), findsOneWidget);
    });

    testWidgets('超过 maxVisuals → 末尾以「+N」计数收口', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionVisualCluster(
            maxVisuals: 2,
            visuals: <IntersectionVisual>[
              IntersectionVisual(assetKind: 'avatar', displayName: 'a'),
              IntersectionVisual(assetKind: 'avatar', displayName: 'b'),
              IntersectionVisual(assetKind: 'avatar', displayName: 'c'),
              IntersectionVisual(assetKind: 'avatar', displayName: 'd'),
            ],
          ),
        ),
      );

      expect(find.text('+2'), findsOneWidget);
    });

    testWidgets('携带 target 的视觉可点击，分发 onVisualTap', (tester) async {
      final tapped = <IntersectionVisual>[];
      await tester.pumpWidget(
        _host(
          IntersectionVisualCluster(
            onVisualTap: tapped.add,
            visuals: <IntersectionVisual>[
              IntersectionVisual(
                assetKind: 'avatar',
                displayName: '林清越',
                target: IntersectionTarget(
                  objectId: 'u_lin',
                  objectKind: 'person',
                  routeId: 'userProfile',
                ),
              ),
            ],
          ),
        ),
      );

      await tester.tap(find.bySemanticsLabel('林清越'));
      expect(tapped.single.displayName, '林清越');
    });
  });
}
