import 'package:flutter/cupertino.dart';
import '../../../../support/fixtures/intersection_fixtures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
import 'package:quwoquan_app/components/object_page/intersection_lifecycle_badge.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_cover.dart';
import 'package:quwoquan_app/components/object_page/intersection_propagation_view.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

Widget _host(Widget child) => CupertinoApp(
  home: CupertinoPageScaffold(child: Center(child: child)),
);

void main() {
  group('槽④ IntersectionLifecycleBadge（生命周期弱标，真相源 lifecycleState）', () {
    testWidgets('stable / weakened / 未知 → 不渲染（零尺寸，无文字）', (tester) async {
      for (final state in const <String>['stable', 'weakened', 'unknown', '']) {
        await tester.pumpWidget(
          _host(IntersectionLifecycleBadge(lifecycleState: state)),
        );
        expect(
          find.descendant(
            of: find.byType(IntersectionLifecycleBadge),
            matching: find.byType(Text),
          ),
          findsNothing,
          reason: 'state=$state 不应渲染弱标文字',
        );
      }
    });

    testWidgets('new 默认渲染「新」文字标', (tester) async {
      await tester.pumpWidget(
        _host(const IntersectionLifecycleBadge(lifecycleState: 'new')),
      );
      expect(
        find.text(DiscoveryFeedText.intersectionLifecycleNew),
        findsOneWidget,
      );
    });

    testWidgets('new + dotOnlyForNew → 仅红点、无文字（紧凑面）', (tester) async {
      await tester.pumpWidget(
        _host(
          const IntersectionLifecycleBadge(
            lifecycleState: 'new',
            dotOnlyForNew: true,
          ),
        ),
      );
      expect(
        find.text(DiscoveryFeedText.intersectionLifecycleNew),
        findsNothing,
      );
      expect(
        find.descendant(
          of: find.byType(IntersectionLifecycleBadge),
          matching: find.byType(Container),
        ),
        findsOneWidget,
      );
    });

    testWidgets('strengthened + strengthDelta>0 → 「增强 +N」', (tester) async {
      await tester.pumpWidget(
        _host(
          const IntersectionLifecycleBadge(
            lifecycleState: 'strengthened',
            strengthDelta: 3,
          ),
        ),
      );
      expect(
        find.text('${DiscoveryFeedText.intersectionLifecycleStrengthened} +3'),
        findsOneWidget,
      );
    });

    testWidgets('reactivated → 「重新活跃」', (tester) async {
      await tester.pumpWidget(
        _host(const IntersectionLifecycleBadge(lifecycleState: 'reactivated')),
      );
      expect(
        find.text(DiscoveryFeedText.intersectionLifecycleReactivated),
        findsOneWidget,
      );
    });
  });

  group(
    '槽① IntersectionIconResolver 降级链（iconKey → sourceRef → dimension → 占位）',
    () {
      test('iconKey 直命中闭集', () {
        expect(
          IntersectionIconResolver.resolve(iconKey: 'place'),
          CupertinoIcons.location_solid,
        );
        expect(
          IntersectionIconResolver.resolve(iconKey: 'connect'),
          CupertinoIcons.link,
        );
      });

      test('iconKey 缺省 → 回退 sourceRef', () {
        expect(
          IntersectionIconResolver.resolve(sourceRef: 'sharedCircle'),
          CupertinoIcons.person_3_fill,
        );
        expect(
          IntersectionIconResolver.resolve(sourceRef: 'sameIndustry'),
          CupertinoIcons.briefcase_fill,
        );
      });

      test('iconKey + sourceRef 缺省 → 回退 dimension', () {
        expect(
          IntersectionIconResolver.resolve(dimension: 'identity'),
          CupertinoIcons.book_solid,
        );
        expect(
          IntersectionIconResolver.resolve(dimension: 'location'),
          CupertinoIcons.location_solid,
        );
      });

      test('全缺省 → 通用占位 link', () {
        expect(IntersectionIconResolver.resolve(), CupertinoIcons.link);
      });

      testWidgets('IntersectionTypeIcon 渲染解析后的图标', (tester) async {
        await tester.pumpWidget(
          _host(const IntersectionTypeIcon(iconKey: 'alumni')),
        );
        expect(find.byIcon(CupertinoIcons.book_solid), findsOneWidget);
      });
    },
  );

  group('槽③ IntersectionObjectCover（对象封面/缩略图，objectVisual 真相源）', () {
    testWidgets('cover 无图 → 回退照片占位图标', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionObjectCover(
            visual: intersectionVisualFixture(
              assetKind: 'cover',
              displayName: '黄金投资圈',
            ),
          ),
        ),
      );
      expect(find.byIcon(CupertinoIcons.photo_fill), findsOneWidget);
    });

    testWidgets('circleAvatar 无图 → 回退圈子占位图标', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionObjectCover(
            visual: intersectionVisualFixture(
              assetKind: 'circleAvatar',
              displayName: '同好圈',
            ),
          ),
        ),
      );
      expect(find.byIcon(CupertinoIcons.person_3_fill), findsOneWidget);
    });

    testWidgets('叠加 lifecycleBadge → overlay 弱标可见', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionObjectCover(
            visual: intersectionVisualFixture(
              assetKind: 'cover',
              displayName: 'x',
            ),
            lifecycleBadge: const IntersectionLifecycleBadge(
              lifecycleState: 'new',
            ),
          ),
        ),
      );
      expect(
        find.text(DiscoveryFeedText.intersectionLifecycleNew),
        findsOneWidget,
      );
    });

    testWidgets('提供 onTap → 命中分发', (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        _host(
          IntersectionObjectCover(
            visual: intersectionVisualFixture(
              assetKind: 'cover',
              displayName: 'x',
            ),
            onTap: () => taps++,
          ),
        ),
      );
      await tester.tap(find.byType(IntersectionObjectCover));
      expect(taps, 1);
    });
  });

  group('传播视图 IntersectionPropagationView（§21.4 可证绝对计数 + 路径节点）', () {
    testWidgets('summaryText 为空 → 隐藏', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionPropagationView(
            path: intersectionPropagationPathFixture(
              pathKind: 'personToPerson',
            ),
          ),
        ),
      );
      expect(
        find.descendant(
          of: find.byType(IntersectionPropagationView),
          matching: find.byType(Text),
        ),
        findsNothing,
      );
    });

    testWidgets('summaryText 非空 → 渲染结论句 + 路径类型图标', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionPropagationView(
            path: intersectionPropagationPathFixture(
              pathKind: 'personToPerson',
              summaryText: '8人通过你建立了新连接',
            ),
          ),
        ),
      );
      expect(find.text('8人通过你建立了新连接'), findsOneWidget);
      expect(find.byType(IntersectionTypeIcon), findsOneWidget);
    });

    testWidgets('secondarySpreadCount>0 → 「再传播 N」弱标', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionPropagationView(
            path: intersectionPropagationPathFixture(
              pathKind: 'personToContentToPerson',
              summaryText: '你的分享带来 12 次再阅读',
              secondarySpreadCount: 12,
            ),
          ),
        ),
      );
      expect(
        find.text(
          '${DiscoveryFeedText.intersectionPropagationSecondarySpreadPrefix} 12',
        ),
        findsOneWidget,
      );
    });

    testWidgets('nodes 非空 → 渲染路径节点视觉簇', (tester) async {
      await tester.pumpWidget(
        _host(
          IntersectionPropagationView(
            path: intersectionPropagationPathFixture(
              pathKind: 'personToPerson',
              summaryText: '8人通过你建立了新连接',
              nodes: <IntersectionVisual>[
                intersectionVisualFixture(
                  assetKind: 'avatar',
                  displayName: '甲',
                ),
                intersectionVisualFixture(
                  assetKind: 'avatar',
                  displayName: '乙',
                ),
              ],
            ),
          ),
        ),
      );
      expect(find.byType(IntersectionVisualCluster), findsOneWidget);
    });

    testWidgets('提供 onSummaryTap → 命中结论句分发', (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        _host(
          IntersectionPropagationView(
            path: intersectionPropagationPathFixture(
              pathKind: 'personToPerson',
              summaryText: '8人通过你建立了新连接',
            ),
            onSummaryTap: () => taps++,
          ),
        ),
      );
      await tester.tap(find.text('8人通过你建立了新连接'));
      expect(taps, 1);
    });
  });
}
