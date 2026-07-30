import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_relation_edge.g.dart';
import 'package:quwoquan_app/components/object_page/object_page_sections.dart';
import 'package:quwoquan_app/core/models/object_relation_edge_type.dart';

/// 关系边类型收敛为闭集之前，服务侧只写 semantic_co_mention/tag_overlap/geo_proximity，
/// 端侧只认 author_of/posted_to_circle/...，两个半边互不相交却都不报错。这里钉住
/// 收敛后的行为：闭集内可解析、闭集外不渲染、四类空间边与计算型 geo_proximity 语义分开。
void main() {
  ObjectRelationEdge edgeOf(String edgeType) => ObjectRelationEdge(
    edgeId: 'edge_$edgeType',
    edgeType: edgeType,
    sourceObjectType: 'post',
    sourceObjectId: 'p1',
    targetObjectType: 'entity',
    targetObjectId: 'e1',
  );

  group('闭集解析', () {
    test('服务侧物化的三类计算边都能被端侧解析', () {
      for (final wire in <String>[
        'semantic_co_mention',
        'tag_overlap',
        'geo_proximity',
      ]) {
        expect(
          ObjectRelationEdgeType.tryParse(wire)?.wire,
          wire,
          reason: '物化器写入的 $wire 必须能被端侧识别',
        );
      }
    });

    test('新增四类空间边在闭集内且被判定为空间关系', () {
      const spatial = <ObjectRelationEdgeType>[
        ObjectRelationEdgeType.locatedIn,
        ObjectRelationEdgeType.partOf,
        ObjectRelationEdgeType.near,
        ObjectRelationEdgeType.routeStop,
      ];
      for (final type in spatial) {
        expect(ObjectRelationEdgeType.tryParse(type.wire), type);
        expect(type.isSpatial, isTrue);
      }
    });

    test('geo_proximity 是共现信号，不是空间断言', () {
      expect(ObjectRelationEdgeType.geoProximity.isSpatial, isFalse);
    });

    test('闭集外取值返回 null 而不是回落到某个默认类型', () {
      for (final raw in <String?>[
        null,
        '',
        '   ',
        'co_tagged',
        'GEO_PROXIMITY',
        'located-in',
      ]) {
        expect(
          ObjectRelationEdgeType.tryParse(raw),
          isNull,
          reason: '未登记的 $raw 不得被当作合法关系类型',
        );
      }
    });

    test('wire 取值唯一，避免同一关系出现两个名字', () {
      final wires = ObjectRelationEdgeType.values
          .map((type) => type.wire)
          .toList(growable: false);
      expect(wires.toSet().length, wires.length);
    });
  });

  group('关系条渲染', () {
    Future<void> pumpRibbon(WidgetTester tester, List<ObjectRelationEdge> edges) {
      return tester.pumpWidget(
        CupertinoApp(
          home: CupertinoPageScaffold(
            child: ObjectRelationRibbon(edges: edges, isDark: false),
          ),
        ),
      );
    }

    testWidgets('空间边渲染出对应的中文关系措辞', (tester) async {
      await pumpRibbon(tester, <ObjectRelationEdge>[edgeOf('located_in')]);

      expect(find.textContaining('位于'), findsOneWidget);
    });

    testWidgets('未登记类型整条不展示，而不是把裸 wire 字符串给用户', (tester) async {
      await pumpRibbon(tester, <ObjectRelationEdge>[edgeOf('mystery_relation')]);

      expect(find.textContaining('mystery_relation'), findsNothing);
      // 全部边都不可识别时整个组件收起，避免出现只有标题的空壳。
      expect(find.byType(ObjectRelationRibbon), findsOneWidget);
      expect(find.textContaining('与你相关'), findsNothing);
    });

    testWidgets('可识别边与不可识别边混排时只渲染可识别的那些', (tester) async {
      await pumpRibbon(tester, <ObjectRelationEdge>[
        edgeOf('route_stop'),
        edgeOf('mystery_relation'),
        edgeOf('near'),
      ]);

      expect(find.textContaining('是路线上的一站'), findsOneWidget);
      expect(find.textContaining('就在附近'), findsOneWidget);
      expect(find.textContaining('mystery_relation'), findsNothing);
    });
  });
}
