import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_error_view.dart';

class AssistantSessionInlineError extends StatelessWidget {
  const AssistantSessionInlineError({
    super.key,
    required this.state,
    required this.onRetry,
    required this.onOpenSettings,
    required this.onDismiss,
  });

  final AssistantSessionErrorView state;
  final Future<void> Function() onRetry;
  final Future<void> Function() onOpenSettings;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return AppSectionErrorCard(
      margin: EdgeInsets.zero,
      semantic: _retrySemantic(context),
      onAction: (action) async {
        switch (action.type) {
          case UiErrorActionType.retry:
          case UiErrorActionType.resubmit:
            return onRetry();
          case UiErrorActionType.openSettings:
            return onOpenSettings();
          case UiErrorActionType.dismiss:
            onDismiss();
            return;
          case UiErrorActionType.login:
          case UiErrorActionType.openUpdate:
            // 找私助入口自身已受登录门保护，此处不会消费新的登录 continuation。
            return;
        }
      },
    );
  }

  UiErrorSemantic _retrySemantic(BuildContext context) {
    const retryAction = UiErrorAction(
      type: UiErrorActionType.retry,
      label: ContentText.tryAgain,
    );
    final failure = state.errorFailure;
    if (failure == null) {
      return UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.section,
        title: ContentText.submitNotCompleted,
        message: state.errorMessage,
        primaryAction: retryAction,
        presentation: UiErrorPresentation.sectionSoftCard,
        tone: UiErrorTone.caution,
      );
    }
    final resolved = runtimeErrorSemantic(
      context,
      error: failure,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.section,
      allowOpenSettings: true,
      presentation: UiErrorPresentation.sectionSoftCard,
    );
    final hasRetry =
        resolved.primaryAction?.type == UiErrorActionType.retry ||
        resolved.primaryAction?.type == UiErrorActionType.resubmit ||
        resolved.secondaryAction?.type == UiErrorActionType.retry ||
        resolved.secondaryAction?.type == UiErrorActionType.resubmit;
    return UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: resolved.title,
      message: resolved.message,
      secondaryMessage: resolved.secondaryMessage,
      primaryAction: resolved.primaryAction ?? retryAction,
      secondaryAction: hasRetry || resolved.primaryAction == null
          ? resolved.secondaryAction
          : retryAction,
      dismissible: resolved.dismissible,
      sourceCode: resolved.sourceCode,
      failureKind: resolved.failureKind,
      copyKey: resolved.copyKey,
      recoveryAction: resolved.recoveryAction,
      presentation: UiErrorPresentation.sectionSoftCard,
      tone: resolved.tone,
      appearanceMode: resolved.appearanceMode,
      sourceRouteId: resolved.sourceRouteId,
      sourceSurfaceId: resolved.sourceSurfaceId,
    );
  }
}
