// 请求反馈组件的 a11y 闭集断言（等待语义可被辅助技术感知 / 文本对比度，双主题）。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

Widget _host({required Brightness brightness, required Widget child}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppRequestFeedback ${brightness.name} 满足 a11y 闭集', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      await tester.pumpWidget(
        _host(
          brightness: brightness,
          child: AppRequestFeedback.page(showSlowHint: true),
        ),
      );
      await tester.pump();

      // 等待慢提示文本必须可被辅助技术读到。
      expect(
        find.bySemanticsLabel(FoundationText.requestWaitSlow),
        findsOneWidget,
      );
      await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      semantics.dispose();
    });
  }
}
