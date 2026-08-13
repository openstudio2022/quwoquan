// 页面错误态组件的 a11y 闭集断言（恢复按钮触控目标 / 语义标签 / 文本对比度，双主题）。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

Widget _host({required Brightness brightness}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: CupertinoPageScaffold(
      child: AppPageErrorState(
        semantic: const UiErrorSemantic(
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
          title: SearchText.recoveryConnectionUnavailableTitle,
          message: SearchText.recoveryConnectionUnavailableMessage,
          primaryAction: UiErrorAction(
            type: UiErrorActionType.retry,
            label: SearchText.reload,
          ),
        ),
        onRecovery: (_) async => UiRecoveryOutcome.stillBlocked,
      ),
    ),
  );
}

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppPageErrorState ${brightness.name} 满足 a11y 闭集', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      await tester.pumpWidget(_host(brightness: brightness));
      await tester.pump();

      await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      semantics.dispose();
    });
  }
}
