// 动作面板（创作入口/更多操作底座）的 a11y 闭集断言：
// 触控目标尺寸与可点目标语义标签在明暗两主题下达标。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-006
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppActionSheet ${brightness.name} 主题满足 a11y 闭集', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      await tester.pumpWidget(
        CupertinoApp(
          theme: CupertinoThemeData(brightness: brightness),
          home: CupertinoPageScaffold(
            child: Center(
              child: Builder(
                builder: (context) => CupertinoButton(
                  onPressed: () {
                    showAppActionSheet<String>(
                      context,
                      title: '发布内容',
                      sections: const [
                        AppActionSheetSection<String>(
                          items: [
                            AppActionSheetItem<String>(
                              label: '写文章',
                              value: 'article',
                            ),
                            AppActionSheetItem<String>(
                              label: '发图片',
                              value: 'photo',
                            ),
                          ],
                        ),
                      ],
                    );
                  },
                  child: const Text('打开动作面板'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('打开动作面板'));
      await tester.pumpAndSettle();

      expect(find.text('写文章'), findsOneWidget);
      await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      semantics.dispose();
    });
  }
}
