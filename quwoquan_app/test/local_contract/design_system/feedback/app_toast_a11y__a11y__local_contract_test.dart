// 全局 Toast（轻提示/错误提示高频载体）的 a11y 闭集断言：
// 文本对比度在明暗两主题下达标，且消息文本进入语义树可被读屏读出。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-006
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppToast ${brightness.name} 主题文本对比度达标且可被读屏', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      const hostKey = ValueKey<String>('toast-a11y-host');
      await tester.pumpWidget(
        CupertinoApp(
          theme: CupertinoThemeData(brightness: brightness),
          home: const CupertinoPageScaffold(
            child: Center(child: SizedBox(key: hostKey)),
          ),
        ),
      );
      // 直接经宿主 context 触发，脚手架不引入额外可点节点。
      AppToast.show(
        tester.element(find.byKey(hostKey)),
        '标签反馈已记录，稍后可在推荐里看到变化',
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('标签反馈已记录，稍后可在推荐里看到变化'), findsOneWidget);
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      semantics.dispose();
      // 让 toast 定时器走完，避免 pending timer 泄漏。
      await tester.pump(const Duration(seconds: 4));
    });
  }
}
