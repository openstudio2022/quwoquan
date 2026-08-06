// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-009

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/design_system/layout/app_terminal_viewport.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';

void main() {
  testWidgets('AppPageErrorState 在扣除底部 chrome 后的可见内容区居中', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      CupertinoApp(
        home: AppViewportObstructionScope(
          obstruction: const EdgeInsets.only(bottom: 100),
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

    final titleRect = tester.getRect(
      find.text(SearchText.recoveryConnectionUnavailableTitle),
    );
    final actionRect = tester.getRect(
      find.ancestor(
        of: find.text(SearchText.reload),
        matching: find.byType(CupertinoButton),
      ),
    );

    expect(
      (titleRect.top + actionRect.bottom) / 2,
      moreOrLessEquals((844 - 100) / 2, epsilon: 1),
    );
  });
}
