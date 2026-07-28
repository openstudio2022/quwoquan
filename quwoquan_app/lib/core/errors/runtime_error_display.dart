import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

String runtimeErrorDisplayMessage(Object error) {
  final failure = runtimeFailureFromError(error);
  final group = AppUserRecoveryContract.classify(
    error: error,
    failure: failure,
    category: UiErrorCategory.backgroundAction,
  );
  return AppUserRecoveryContract.copyFor(
    group,
    retryAfterSeconds: AppUserRecoveryContract.retryAfterSeconds(error),
  ).message;
}

UiErrorSemantic runtimeErrorSemantic(
  BuildContext context, {
  required Object error,
  required UiErrorCategory category,
  required UiErrorScope scope,
  AuthGateReason? authGateReason,
  AuthContinuation? continuation,
  bool allowRetry = true,
  bool allowOpenSettings = false,
  bool verifiedUpdateAvailable = false,
  UiErrorPresentation? presentation,
  UiErrorAppearanceMode appearanceMode = UiErrorAppearanceMode.inherit,
  String? sourceRouteId,
  String? sourceSurfaceId,
  String? sourceOperationId,
}) {
  return UiErrorSemanticResolver.resolve(
    context,
    error: error,
    category: category,
    scope: scope,
    authGateReason: authGateReason,
    continuation: continuation,
    allowRetry: allowRetry,
    allowOpenSettings: allowOpenSettings,
    verifiedUpdateAvailable: verifiedUpdateAvailable,
    presentation: presentation,
    appearanceMode: appearanceMode,
    sourceRouteId: sourceRouteId,
    sourceSurfaceId: sourceSurfaceId,
    sourceOperationId: sourceOperationId,
  );
}

/// 为调用方确实持有 reload/invalidate 能力的区块补齐重试动作。
///
/// 已由统一 resolver 给出登录、设置或其它主动作时保持原语义；仅在没有任何
/// 主恢复动作时补充 retry，并保留错误码、trace 与展示信息。
UiErrorSemantic ensureRetryUiErrorSemantic(
  UiErrorSemantic resolved, {
  String retryLabel = ContentText.tryAgain,
}) {
  final secondaryIsRetry =
      resolved.secondaryAction?.type == UiErrorActionType.retry ||
      resolved.secondaryAction?.type == UiErrorActionType.resubmit;
  if (resolved.primaryAction != null || secondaryIsRetry) {
    return resolved;
  }
  return UiErrorSemantic(
    category: resolved.category,
    scope: resolved.scope,
    title: resolved.title,
    message: resolved.message,
    secondaryMessage: resolved.secondaryMessage,
    primaryAction: UiErrorAction(
      type: UiErrorActionType.retry,
      label: retryLabel,
    ),
    secondaryAction: resolved.secondaryAction,
    dismissible: resolved.dismissible,
    sourceCode: resolved.sourceCode,
    failureKind: resolved.failureKind,
    copyKey: resolved.copyKey,
    recoveryAction: RuntimeRecoveryAction.retry,
    presentation: resolved.presentation,
    tone: resolved.tone,
    appearanceMode: resolved.appearanceMode,
    sourceRouteId: resolved.sourceRouteId,
    sourceSurfaceId: resolved.sourceSurfaceId,
    sourceOperationId: resolved.sourceOperationId,
    requestId: resolved.requestId,
    traceId: resolved.traceId,
    userRecoveryGroup: resolved.userRecoveryGroup,
  );
}

RuntimeFailureBase? runtimeFailureFromError(Object error) {
  if (error is CloudException) return error.runtimeFailure;
  if (error is RuntimeFailureBase) return error;
  return CloudErrorMapper.runtimeFailureFromException(error);
}

String runtimeFailureDisplayMessage(RuntimeFailureBase failure) {
  final group = AppUserRecoveryContract.classify(
    error: failure,
    failure: failure,
    category: UiErrorCategory.backgroundAction,
  );
  return AppUserRecoveryContract.copyFor(group).message;
}
