// 二级 Tab 栏（页内分区导航）的 a11y 闭集断言：
// 触控目标尺寸与可点目标语义标签在明暗两主题下达标。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-006
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/navigation/secondary_tab_bar.dart';

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppSecondaryTabBar ${brightness.name} 主题满足 a11y 闭集', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      await tester.pumpWidget(
        CupertinoApp(
          theme: CupertinoThemeData(brightness: brightness),
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: AppSecondaryTabBar(
                tabs: const [
                  AppSecondaryTabItem(id: 'posts', label: '动态'),
                  AppSecondaryTabItem(id: 'interaction', label: '互动'),
                  AppSecondaryTabItem(id: 'about', label: '资料'),
                ],
                selectedId: 'posts',
                onSelected: (_) {},
                isDark: brightness == Brightness.dark,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      semantics.dispose();
    });
  }
}
