import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';

/// A4：内容卡交集理由位 / post 作者信任徽标口径一致（最强证据组短句 + 计数）。
Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

IntersectionReason _reason({
  required String label,
  required int count,
  String pointClass = 'fact',
}) {
  return IntersectionReason(
    dimension: 'relationship',
    source: 'relationship',
    intersectionPoints: <IntersectionPoint>[
      IntersectionPoint(
        pointId: label,
        pointClass: pointClass,
        dimension: 'relationship',
        label: label,
        displayText: label,
        count: count,
      ),
    ],
  );
}

void main() {
  group('IntersectionReasonChip.primaryText 唯一口径（最强证据组）', () {
    test('取首条理由最强证据组短句 + 计数（共同关注 4）', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          _reason(label: '共同关注', count: 4),
        ]),
        '共同关注 4',
      );
    });

    test('count 为 0 → 仅短句，不带空数字', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          _reason(label: '互相关注', count: 0),
        ]),
        '互相关注',
      );
    });

    test('零内部词：不再出现「个交集点」', () {
      final text = IntersectionReasonChip.primaryText(<IntersectionReason>[
        _reason(label: '共看内容', count: 8),
      ]);
      expect(text, isNotNull);
      expect(text!.contains('个交集点'), isFalse);
    });

    test('null / 空列表 → null（不展示）', () {
      expect(IntersectionReasonChip.primaryText(null), isNull);
      expect(
        IntersectionReasonChip.primaryText(const <IntersectionReason>[]),
        isNull,
      );
    });

    test('无可展示证据组 → null（不展示）', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          IntersectionReason(dimension: 'relationship'),
        ]),
        isNull,
      );
    });
  });

  group('IntersectionReasonChip.fromReasons 构造口径', () {
    testWidgets('有证据组 → 渲染最强证据短句 + 计数', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(label: '共同关注', count: 4),
      ], isDark: false);
      expect(widget, isNotNull);
      await tester.pumpWidget(_wrap(widget!));
      expect(find.text('共同关注 4'), findsOneWidget);
    });

    test('无来源 → 返回 null（调用方不插入，保证四口径一致）', () {
      expect(IntersectionReasonChip.fromReasons(null, isDark: false), isNull);
    });
  });

  testWidgets('双主题均渲染只读文案', (tester) async {
    for (final isDark in const <bool>[false, true]) {
      await tester.pumpWidget(
        _wrap(IntersectionReasonChip(text: '共同关注 4', isDark: isDark)),
      );
      expect(tester.takeException(), isNull);
      expect(find.text('共同关注 4'), findsOneWidget);
    }
  });
}
