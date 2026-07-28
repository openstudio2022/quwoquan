import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_appearance.dart';
import 'package:quwoquan_app/core/errors/ui_error_models.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 一个恢复组对应唯一一套用户可见语义。
final class AppUserRecoveryContract {
  const AppUserRecoveryContract._();

  static AppUserRecoveryGroup classify({
    required Object error,
    required RuntimeFailureBase? failure,
    required UiErrorCategory category,
    bool allowOpenSettings = false,
    bool verifiedUpdateAvailable = false,
  }) {
    final status = error is CloudException
        ? error.statusCode
        : failure?.transportStatus;
    final code = _sourceCode(error, failure);

    if (verifiedUpdateAvailable) {
      return AppUserRecoveryGroup.updateApp;
    }
    if (allowOpenSettings ||
        category == UiErrorCategory.permissionRequired ||
        failure?.nature == RuntimeFailureNature.requiresPermission) {
      return AppUserRecoveryGroup.enablePermission;
    }
    if (category == UiErrorCategory.authRequired ||
        failure?.kind == RuntimeFailureKind.auth ||
        status == 401 ||
        (error is CloudException &&
            error.type == CloudErrorType.unauthorized)) {
      return AppUserRecoveryGroup.loginAgain;
    }
    if (code == RuntimeFailureCodes.appNetworkOffline) {
      return AppUserRecoveryGroup.connectNetwork;
    }
    if (status == 429 ||
        failure?.kind == RuntimeFailureKind.rateLimited ||
        (error is CloudException && error.type == CloudErrorType.rateLimited)) {
      return AppUserRecoveryGroup.waitThenReload;
    }
    if (_isExplicitlyGone(code: code, status: status)) {
      return AppUserRecoveryGroup.contentGone;
    }
    if (status == 403 ||
        (error is CloudException && error.type == CloudErrorType.forbidden)) {
      return AppUserRecoveryGroup.noAccess;
    }
    if (status == 404 ||
        failure?.kind == RuntimeFailureKind.notFound ||
        failure?.kind == RuntimeFailureKind.unsupported ||
        (error is CloudException && error.type == CloudErrorType.notFound)) {
      return AppUserRecoveryGroup.contentUnavailable;
    }
    return AppUserRecoveryGroup.reloadLater;
  }

  static AppUserRecoveryCopy copyFor(
    AppUserRecoveryGroup group, {
    int retryAfterSeconds = 0,
  }) {
    return switch (group) {
      AppUserRecoveryGroup.connectNetwork => const AppUserRecoveryCopy(
        title: SearchText.recoveryConnectNetworkTitle,
        message: SearchText.recoveryConnectNetworkMessage,
        action: UiErrorAction(
          type: UiErrorActionType.retry,
          label: SearchText.reload,
        ),
        recoveryAction: RuntimeRecoveryAction.retry,
      ),
      AppUserRecoveryGroup.reloadLater => const AppUserRecoveryCopy(
        title: SearchText.recoveryReloadLaterTitle,
        message: SearchText.recoveryReloadLaterMessage,
        action: UiErrorAction(
          type: UiErrorActionType.retry,
          label: SearchText.reload,
        ),
        recoveryAction: RuntimeRecoveryAction.retry,
      ),
      AppUserRecoveryGroup.loginAgain => const AppUserRecoveryCopy(
        title: SearchText.recoveryLoginAgainTitle,
        message: SearchText.recoveryLoginAgainMessage,
        action: UiErrorAction(
          type: UiErrorActionType.login,
          label: SearchText.recoveryLoginAgainAction,
        ),
        recoveryAction: RuntimeRecoveryAction.surface,
      ),
      AppUserRecoveryGroup.enablePermission => const AppUserRecoveryCopy(
        title: SearchText.recoveryEnablePermissionTitle,
        message: SearchText.recoveryEnablePermissionMessage,
        action: UiErrorAction(
          type: UiErrorActionType.openSettings,
          label: SearchText.recoveryEnablePermissionAction,
        ),
        recoveryAction: RuntimeRecoveryAction.surface,
      ),
      AppUserRecoveryGroup.waitThenReload => AppUserRecoveryCopy(
        title: SearchText.recoveryWaitThenReloadTitle,
        message: SearchText.recoveryWaitThenReloadMessage(retryAfterSeconds),
        action: UiErrorAction(
          type: UiErrorActionType.retry,
          label: SearchText.reload,
          availableAfterSeconds: retryAfterSeconds,
        ),
        recoveryAction: RuntimeRecoveryAction.retry,
      ),
      AppUserRecoveryGroup.updateApp => const AppUserRecoveryCopy(
        title: SearchText.recoveryUpdateAppTitle,
        message: SearchText.recoveryUpdateAppMessage,
        action: UiErrorAction(
          type: UiErrorActionType.openUpdate,
          label: SearchText.recoveryUpdateAppAction,
        ),
        recoveryAction: RuntimeRecoveryAction.surface,
      ),
      AppUserRecoveryGroup.noAccess => const AppUserRecoveryCopy(
        title: SearchText.recoveryNoAccessTitle,
        message: SearchText.recoveryNoAccessMessage,
        action: UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: SearchText.recoveryReturnAction,
        ),
        recoveryAction: RuntimeRecoveryAction.surface,
      ),
      AppUserRecoveryGroup.contentGone => const AppUserRecoveryCopy(
        title: SearchText.recoveryContentGoneTitle,
        message: SearchText.recoveryContentGoneMessage,
        action: UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: SearchText.recoveryReturnAction,
        ),
        recoveryAction: RuntimeRecoveryAction.surface,
      ),
      AppUserRecoveryGroup.contentUnavailable => const AppUserRecoveryCopy(
        title: SearchText.recoveryContentUnavailableTitle,
        message: SearchText.recoveryContentUnavailableMessage,
        action: UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: SearchText.recoveryReturnAction,
        ),
        recoveryAction: RuntimeRecoveryAction.surface,
      ),
    };
  }

  /// 从恢复组直接生成唯一可见语义，供没有原始异常对象的已确认页面事实使用。
  static UiErrorSemantic semanticFor({
    required AppUserRecoveryGroup group,
    required UiErrorCategory category,
    required UiErrorScope scope,
    int retryAfterSeconds = 0,
    UiErrorPresentation? presentation,
    UiErrorTone? tone,
    UiErrorAppearanceMode appearanceMode = UiErrorAppearanceMode.inherit,
    String? sourceCode,
    RuntimeFailureKind? failureKind,
    String? sourceRouteId,
    String? sourceSurfaceId,
    String? sourceOperationId,
    String? requestId,
    String? traceId,
  }) {
    final copy = copyFor(group, retryAfterSeconds: retryAfterSeconds);
    return UiErrorSemantic(
      category: category,
      scope: scope,
      title: copy.title,
      message: copy.message,
      primaryAction: copy.action,
      dismissible:
          scope == UiErrorScope.global ||
          scope == UiErrorScope.dialog ||
          group == AppUserRecoveryGroup.noAccess ||
          group == AppUserRecoveryGroup.contentGone ||
          group == AppUserRecoveryGroup.contentUnavailable,
      sourceCode: sourceCode,
      failureKind: failureKind,
      copyKey: 'recovery.${group.name}',
      recoveryAction: copy.recoveryAction,
      presentation:
          presentation ?? _presentationFor(category: category, scope: scope),
      tone: tone ?? _toneFor(group),
      appearanceMode: appearanceMode,
      sourceRouteId: sourceRouteId,
      sourceSurfaceId: sourceSurfaceId,
      sourceOperationId: sourceOperationId,
      requestId: requestId,
      traceId: traceId,
      userRecoveryGroup: group,
    );
  }

  static UiErrorPresentation _presentationFor({
    required UiErrorCategory category,
    required UiErrorScope scope,
  }) {
    if (scope == UiErrorScope.inlineField) {
      return UiErrorPresentation.inlineField;
    }
    if (scope == UiErrorScope.form) {
      return UiErrorPresentation.formInlineCard;
    }
    if (category == UiErrorCategory.authRequired ||
        category == UiErrorCategory.permissionRequired) {
      return UiErrorPresentation.gateCard;
    }
    if (category == UiErrorCategory.listAppend) {
      return UiErrorPresentation.appendFooter;
    }
    if (category == UiErrorCategory.backgroundAction) {
      return UiErrorPresentation.transientNotice;
    }
    if (scope == UiErrorScope.dialog ||
        scope == UiErrorScope.global ||
        category == UiErrorCategory.submit ||
        category == UiErrorCategory.rateLimited) {
      return UiErrorPresentation.actionDialog;
    }
    if (scope == UiErrorScope.section ||
        category == UiErrorCategory.sectionLoad) {
      return UiErrorPresentation.sectionSoftCard;
    }
    return UiErrorPresentation.emptyPage;
  }

  static UiErrorTone _toneFor(AppUserRecoveryGroup group) {
    return switch (group) {
      AppUserRecoveryGroup.loginAgain ||
      AppUserRecoveryGroup.enablePermission ||
      AppUserRecoveryGroup.updateApp => UiErrorTone.info,
      AppUserRecoveryGroup.waitThenReload => UiErrorTone.caution,
      _ => UiErrorTone.neutral,
    };
  }

  static int retryAfterSeconds(Object error) {
    if (error is! CloudException) return 0;
    final seconds = error.retryAfter?.inSeconds ?? 0;
    return seconds > 0 ? seconds : 0;
  }

  static String _sourceCode(Object error, RuntimeFailureBase? failure) {
    if (error is CloudException) {
      final code = error.code?.trim() ?? '';
      if (code.isNotEmpty) return code;
    }
    return failure?.code.trim() ?? '';
  }

  static bool _isExplicitlyGone({required String code, required int? status}) {
    return code == ContentErrorCode.contentDeleted.code && status == 410;
  }
}

final class AppUserRecoveryCopy {
  const AppUserRecoveryCopy({
    required this.title,
    required this.message,
    required this.action,
    required this.recoveryAction,
  });

  final String title;
  final String message;
  final UiErrorAction action;
  final RuntimeRecoveryAction recoveryAction;
}
