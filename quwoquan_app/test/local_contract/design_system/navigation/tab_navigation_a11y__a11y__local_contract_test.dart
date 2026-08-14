// 一级 Tab 导航（首页/发现页顶部导航）的 a11y 闭集断言：
// 触控目标尺寸与可点目标语义标签在明暗两主题下达标。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-006
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/navigation/tab_navigation.dart';

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('TabNavigationWidget ${brightness.name} 主题满足 a11y 闭集', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      await tester.pumpWidget(
        ProviderScope(
          child: CupertinoApp(
            theme: CupertinoThemeData(brightness: brightness),
            home: CupertinoPageScaffold(
              child: SafeArea(
                child: TabNavigationWidget(
                  activeTab: 'recommended',
                  onTabChange: (_) {},
                  isDark: brightness == Brightness.dark,
                  tabs: TabNavigationWidget.discoveryTabs,
                ),
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
