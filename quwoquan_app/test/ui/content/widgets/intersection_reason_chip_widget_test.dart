import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';

/// A4：内容卡交集理由位 / post 作者信任徽标口径一致（云侧主结论句直出，G2 端不本地拼装）。
Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

IntersectionReason _reason({String primaryText = '', String displayText = ''}) {
  return IntersectionReason(
    dimension: 'relationship',
    source: 'relationship',
    primaryText: primaryText,
    displayText: displayText,
  );
}

void main() {
  group('IntersectionReasonChip.primaryText 唯一口径（云侧主结论句直出）', () {
    test('取首条理由的 primaryText（4位共同好友）', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          _reason(primaryText: '4位共同好友'),
        ]),
        '4位共同好友',
      );
    });

    test('primaryText 缺省 → 回退整句 displayText，不在端侧拼接计数', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          _reason(displayText: '你和 TA 都来自同一校园'),
        ]),
        '你和 TA 都来自同一校园',
      );
    });

    test('零内部词：不出现「个交集点」', () {
      final text = IntersectionReasonChip.primaryText(<IntersectionReason>[
        _reason(primaryText: '8人和你共看黄金内容'),
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

    test('无可展示结论句 → null（不展示）', () {
      expect(
        IntersectionReasonChip.primaryText(<IntersectionReason>[
          IntersectionReason(dimension: 'relationship'),
        ]),
        isNull,
      );
    });
  });

  group('IntersectionReasonChip.fromReasons 构造口径', () {
    testWidgets('有主结论句 → 渲染云侧 primaryText', (tester) async {
      final widget = IntersectionReasonChip.fromReasons(<IntersectionReason>[
        _reason(primaryText: '4位共同好友'),
      ], isDark: false);
      expect(widget, isNotNull);
      await tester.pumpWidget(_wrap(widget!));
      expect(find.text('4位共同好友'), findsOneWidget);
    });

    test('无来源 → 返回 null（调用方不插入，保证四口径一致）', () {
      expect(IntersectionReasonChip.fromReasons(null, isDark: false), isNull);
    });
  });

  testWidgets('双主题均渲染只读文案', (tester) async {
    for (final isDark in const <bool>[false, true]) {
      await tester.pumpWidget(
        _wrap(IntersectionReasonChip(text: '4位共同好友', isDark: isDark)),
      );
      expect(tester.takeException(), isNull);
      expect(find.text('4位共同好友'), findsOneWidget);
    }
  });
}
