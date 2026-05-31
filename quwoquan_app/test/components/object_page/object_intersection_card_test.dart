import 'package:flutter_test/flutter_test.dart';
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
  });
}
