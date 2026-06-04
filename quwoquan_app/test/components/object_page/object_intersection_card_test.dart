import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';

/// T2：对象页统一交集卡口径（V3 / 全局验收 G2）。
/// 无来源不展示、只读 displayText、不本地拼装。
void main() {
  group('ObjectIntersectionCard.fromReasons（G2 口径）', () {
    test('reasons 为 null → 返回 null（不展示）', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '你们的交集',
          reasons: null,
          isDark: false,
        ),
        isNull,
      );
    });

    test('reasons 为空 → 返回 null', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '你和这里的交集',
          reasons: const <IntersectionReason>[],
          isDark: false,
        ),
        isNull,
      );
    });

    test('displayText 全空白 → 返回 null（禁止空理由展示）', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '你们的交集',
          reasons: [IntersectionReason(displayText: '   ')],
          isDark: false,
        ),
        isNull,
      );
    });

    test('有真实 displayText → 返回交集卡', () {
      final w = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: [
          IntersectionReason(
            dimension: 'identity',
            displayText: '你们都是北大的',
            tagRefs: const ['Entity/机构/学校/北京大学'],
          ),
        ],
        isDark: false,
        sharedCount: 12,
      );
      expect(w, isA<ObjectIntersectionCard>());
    });

    testWidgets('对象页交集以证据胶囊摘要呈现，而不是逐条大行列表', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: [
          IntersectionReason(
            dimension: 'identity',
            displayText: '北京大学',
            tagRefs: const ['Entity/机构/学校/北京大学'],
            intersectionPoints: <IntersectionPoint>[
              IntersectionPoint(
                pointId: 'id_1',
                pointClass: 'fact',
                dimension: 'identity',
                displayText: '北京大学',
              ),
            ],
            totalPointCount: 1,
            factPointCount: 1,
          ),
          IntersectionReason(
            dimension: 'interest',
            intersectionClass: 'affinity',
            displayText: '摄影',
            tagRefs: const ['Topic/摄影'],
            intersectionPoints: <IntersectionPoint>[
              IntersectionPoint(
                pointId: 'int_1',
                pointClass: 'recommended',
                dimension: 'interest',
                displayText: '摄影',
              ),
            ],
            totalPointCount: 1,
            recommendedPointCount: 1,
            pointClassLabel: '推荐交集',
          ),
          IntersectionReason(
            dimension: 'interest',
            intersectionClass: 'affinity',
            displayText: '旅行',
            tagRefs: const ['Topic/旅行'],
            intersectionPoints: <IntersectionPoint>[
              IntersectionPoint(
                pointId: 'int_2',
                pointClass: 'recommended',
                dimension: 'interest',
                displayText: '旅行',
              ),
            ],
            totalPointCount: 1,
            recommendedPointCount: 1,
            pointClassLabel: '推荐交集',
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.text('你们的交集'), findsOneWidget);
      expect(find.text('3'), findsOneWidget);
      expect(find.text('北京大学 · 摄影 · 旅行'), findsOneWidget);
      expect(find.text('身份 1 个交集点 北京大学'), findsOneWidget);
      expect(find.text('推荐交集 1 个推荐交集点 摄影'), findsOneWidget);
      expect(find.text('推荐交集 1 个推荐交集点 旅行'), findsOneWidget);
    });
  });
}
