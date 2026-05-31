import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';

/// A4：内容卡交集理由位口径一致（单列/多列/沉浸/转发/详情同源）。
Widget _wrap(Widget child) {
  return CupertinoApp(home: CupertinoPageScaffold(child: Center(child: child)));
}

IntersectionReason _reason(String displayText) {
  return IntersectionReason(
    dimension: 'identity',
    displayText: displayText,
    sharedCount: 1,
    source: 'identity',
  );
}

void main() {
  group('IntersectionReasonChip.primaryText 唯一口径', () {
    test('取首条 displayText（trim）', () {
      final reasons = <IntersectionReason>[
        _reason('  你和 TA 都来自同一校园  '),
        _reason('你们都在关注 黄金投资'),
      ];
      expect(
        IntersectionReasonChip.primaryText(reasons),
        '你和 TA 都来自同一校园',
      );
    });

    test('null / 空列表 → null（不展示）', () {
      expect(IntersectionReasonChip.primaryText(null), isNull);
      expect(
        IntersectionReasonChip.primaryText(const <IntersectionReason>[]),
        isNull,
      );
    });

    test('首条 displayText 为空白 → null（不展示）', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[_reason('   ')]),
        isNull,
      );
    });
  });

  group('IntersectionReasonChip.fromReasons 构造口径', () {
    testWidgets('有来源 → 渲染同一 chip 文案', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(
        <IntersectionReason>[_reason('你和 TA 都去过 西湖')],
        isDark: false,
      );
      expect(widget, isNotNull);
      await tester.pumpWidget(_wrap(widget!));
      expect(find.text('你和 TA 都去过 西湖'), findsOneWidget);
    });

    test('无来源 → 返回 null（调用方不插入，保证四口径一致）', () {
      expect(
        IntersectionReasonChip.fromReasons(null, isDark: false),
        isNull,
      );
    });
  });

  testWidgets('双主题均渲染只读 displayText', (tester) async {
    for (final isDark in const <bool>[false, true]) {
      await tester.pumpWidget(
        _wrap(
          IntersectionReasonChip(text: '你和 TA 的交集', isDark: isDark),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(find.text('你和 TA 的交集'), findsOneWidget);
    }
  });
}
