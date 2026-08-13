// 关注 pill 的 a11y 闭集断言（可点目标语义标签，双主题双变体）。
//
// iOSTapTargetGuideline 当前为红：pill 可点区域 56x28 低于 44x44 设计系统
// 下限（`CupertinoButton.minimumSize: Size.zero` + `buttonHeightXs`），
// 修复需与消费方布局协同（feed 作者栏 / 沉浸式 toolbar 行高），缺口登记于
// specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#open-003；
// 热区修复后在此补该 guideline 断言。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/actions/app_follow_button.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

Widget _host({
  required Brightness brightness,
  required AppFollowButtonStyle style,
  required bool isFollowing,
}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: CupertinoPageScaffold(
      child: Center(
        child: AppFollowButton(
          isFollowing: isFollowing,
          onPressed: () {},
          style: style,
        ),
      ),
    ),
  );
}

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    for (final style in AppFollowButtonStyle.values) {
      testWidgets(
        'AppFollowButton ${style.name} ${brightness.name} 满足语义标签闭集',
        (tester) async {
          final semantics = tester.ensureSemantics();

          await tester.pumpWidget(
            _host(brightness: brightness, style: style, isFollowing: false),
          );
          await tester.pump();

          // 可点目标必须携带可读语义标签（关注/已关注文案即标签）。
          await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
          expect(
            find.bySemanticsLabel(FoundationText.follow),
            findsOneWidget,
            reason: '关注 pill 的语义标签必须与可见文案同源',
          );
          semantics.dispose();
        },
      );
    }
  }
}
