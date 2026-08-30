@Tags(<String>['serial', 'visual'])
library;

// 页面错误态组件标准形态的双主题视觉基线。
//
// 基线更新规范：仅在对应 UI 有意变更的同一变更集内以
// `flutter test --update-goldens <本文件>` 重建，禁止孤立刷基线。
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
    home: RepaintBoundary(
      key: ValueKey<String>('error-state-${brightness.name}'),
      child: CupertinoPageScaffold(
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
    ),
  );
}

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppPageErrorState ${brightness.name} 视觉基线', (tester) async {
      tester.view.physicalSize = const Size(780, 1200);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_host(brightness: brightness));
      await tester.pump();

      await expectLater(
        find.byKey(ValueKey<String>('error-state-${brightness.name}')),
        matchesGoldenFile(
          'goldens/app_page_error_state_${brightness.name}.png',
        ),
      );
    });
  }
}
