// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-014
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/services/app_page_load_arbiter.dart';

void main() {
  test('关键首屏无内容时只显示一个整页错误', () {
    final decision = AppPageLoadArbiter.decide(<AppPageLoadSlice>[
      AppPageLoadSlice(
        id: 'identity',
        isCritical: true,
        phase: AppPageLoadPhase.failure,
        semantic: _semantic(AppUserRecoveryGroup.reloadLater),
      ),
      AppPageLoadSlice(id: 'works', phase: AppPageLoadPhase.loading),
    ]);

    expect(decision.kind, AppPageLoadDecisionKind.blockingFailure);
    expect(
      decision.semantic?.userRecoveryGroup,
      AppUserRecoveryGroup.reloadLater,
    );
    expect(decision.suppresses('works'), isTrue);
  });

  test('单个可选区块失败仍由区块自己展示', () {
    final decision = AppPageLoadArbiter.decide(<AppPageLoadSlice>[
      const AppPageLoadSlice(
        id: 'identity',
        isCritical: true,
        phase: AppPageLoadPhase.content,
        hasUsableContent: true,
      ),
      AppPageLoadSlice(
        id: 'works',
        phase: AppPageLoadPhase.failure,
        semantic: _semantic(AppUserRecoveryGroup.reloadLater),
      ),
    ]);

    expect(decision.kind, AppPageLoadDecisionKind.content);
    expect(decision.sectionOwnedFailureIds, <String>{'works'});
  });

  test('两个区块失败合并为一个页面提示并按固定优先级裁决', () {
    final decision = AppPageLoadArbiter.decide(<AppPageLoadSlice>[
      const AppPageLoadSlice(
        id: 'identity',
        isCritical: true,
        phase: AppPageLoadPhase.content,
        hasUsableContent: true,
      ),
      AppPageLoadSlice(
        id: 'works',
        phase: AppPageLoadPhase.failure,
        semantic: _semantic(AppUserRecoveryGroup.reloadLater),
      ),
      AppPageLoadSlice(
        id: 'impact',
        phase: AppPageLoadPhase.failure,
        semantic: _semantic(AppUserRecoveryGroup.loginAgain),
      ),
    ]);

    expect(decision.kind, AppPageLoadDecisionKind.contentWithNotice);
    expect(
      decision.semantic?.userRecoveryGroup,
      AppUserRecoveryGroup.loginAgain,
    );
    expect(decision.suppressedSliceIds, <String>{'works', 'impact'});
  });
}

UiErrorSemantic _semantic(AppUserRecoveryGroup group) {
  final copy = AppUserRecoveryContract.copyFor(group);
  return UiErrorSemantic(
    category: UiErrorCategory.sectionLoad,
    scope: UiErrorScope.section,
    title: copy.title,
    message: copy.message,
    primaryAction: copy.action,
    copyKey: 'recovery.${group.name}',
    recoveryAction: copy.recoveryAction,
    userRecoveryGroup: group,
  );
}
