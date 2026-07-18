part of 'app_router.dart';

class _RouterRecoveryPage extends StatelessWidget {
  const _RouterRecoveryPage({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      body: AppPageErrorState(
        semantic: UiErrorSemantic(
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.global,
          title: UITextConstants.startupRecoveryTitle,
          message:
              OpsEventRecordErrorCode.startupRouterUnavailable.defaultMessage,
          secondaryMessage: UITextConstants.startupRecoverySupportHint,
          sourceCode: OpsEventRecordErrorCode.startupRouterUnavailable.code,
          failureKind: RuntimeFailureKind.unavailable,
          recoveryAction: RuntimeRecoveryAction.retry,
          copyKey: 'startupRouterRecovery',
          presentation: UiErrorPresentation.emptyPage,
          tone: UiErrorTone.critical,
          primaryAction: UiErrorAction(
            type: UiErrorActionType.retry,
            label: UITextConstants.startupRecoveryRetry,
          ),
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry) {
            onRetry();
          }
        },
      ),
    );
  }
}
