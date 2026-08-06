import 'package:quwoquan_app/core/errors/ui_error_appearance.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum UiErrorCategory {
  pageLoad,
  sectionLoad,
  listAppend,
  submit,
  authRequired,
  permissionRequired,
  validation,
  notFound,
  rateLimited,
  backgroundAction,
}

enum UiErrorScope { page, section, form, dialog, global, inlineField }

enum UiErrorPresentation {
  transientNotice,
  appendFooter,
  emptyPage,
  sectionSoftCard,
  actionDialog,
  gateCard,
  formInlineCard,
  inlineField,
}

enum UiErrorTone { neutral, info, caution, critical }

/// 用户可理解、可执行的恢复分组。
///
/// 传输层和领域层仍保留精细错误码；用户界面只消费可执行的恢复分组，
/// 技术诊断仅进入脱敏日志和遥测。
enum AppUserRecoveryGroup {
  connectNetwork,
  connectionUnavailable,
  requestTimedOut,
  serviceUnavailable,
  invalidContent,
  guestSessionUnavailable,
  reloadLater,
  loginAgain,
  enablePermission,
  waitThenReload,
  updateApp,
  noAccess,
  contentGone,
  contentUnavailable,
}

enum UiErrorActionType {
  retry,
  login,
  openSettings,
  openUpdate,
  dismiss,
  resubmit,
}

class UiErrorAction {
  const UiErrorAction({
    required this.type,
    required this.label,
    this.availableAfterSeconds = 0,
  });

  final UiErrorActionType type;
  final String label;
  final int availableAfterSeconds;
}

class UiErrorSemantic {
  const UiErrorSemantic({
    required this.category,
    required this.scope,
    required this.title,
    required this.message,
    this.secondaryMessage,
    this.primaryAction,
    this.secondaryAction,
    this.dismissible = false,
    this.sourceCode,
    this.failureKind,
    this.copyKey,
    this.recoveryAction,
    this.presentation = UiErrorPresentation.emptyPage,
    this.tone = UiErrorTone.neutral,
    this.appearanceMode = UiErrorAppearanceMode.inherit,
    this.sourceRouteId,
    this.sourceSurfaceId,
    this.sourceOperationId,
    this.requestId,
    this.traceId,
    this.userRecoveryGroup,
  });

  final UiErrorCategory category;
  final UiErrorScope scope;
  final String title;
  final String message;
  final String? secondaryMessage;
  final UiErrorAction? primaryAction;
  final UiErrorAction? secondaryAction;
  final bool dismissible;
  final String? sourceCode;
  final RuntimeFailureKind? failureKind;
  final String? copyKey;
  final RuntimeRecoveryAction? recoveryAction;
  final UiErrorPresentation presentation;
  final UiErrorTone tone;
  final UiErrorAppearanceMode appearanceMode;
  final String? sourceRouteId;
  final String? sourceSurfaceId;
  final String? sourceOperationId;
  final String? requestId;
  final String? traceId;
  final AppUserRecoveryGroup? userRecoveryGroup;

  /// 只补充来源与外观上下文，不允许页面改写恢复组的可见文案和动作。
  UiErrorSemantic withSurfaceContext({
    UiErrorAppearanceMode? appearanceMode,
    String? sourceRouteId,
    String? sourceSurfaceId,
    String? sourceOperationId,
  }) {
    return UiErrorSemantic(
      category: category,
      scope: scope,
      title: title,
      message: message,
      secondaryMessage: secondaryMessage,
      primaryAction: primaryAction,
      secondaryAction: secondaryAction,
      dismissible: dismissible,
      sourceCode: sourceCode,
      failureKind: failureKind,
      copyKey: copyKey,
      recoveryAction: recoveryAction,
      presentation: presentation,
      tone: tone,
      appearanceMode: appearanceMode ?? this.appearanceMode,
      sourceRouteId: sourceRouteId ?? this.sourceRouteId,
      sourceSurfaceId: sourceSurfaceId ?? this.sourceSurfaceId,
      sourceOperationId: sourceOperationId ?? this.sourceOperationId,
      requestId: requestId,
      traceId: traceId,
      userRecoveryGroup: userRecoveryGroup,
    );
  }
}
