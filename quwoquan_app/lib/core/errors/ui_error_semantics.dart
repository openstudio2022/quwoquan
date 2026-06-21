import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/chat/generated/chat_errors.g.dart';
import 'package:quwoquan_app/cloud/circle/generated/circle_errors.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
import 'package:quwoquan_app/cloud/rtc/generated/rtc_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
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

enum UiErrorScope { page, section, dialog, global, inlineField }

enum UiErrorPresentation {
  transientNotice,
  appendFooter,
  emptyPage,
  sectionSoftCard,
  actionDialog,
  gateCard,
  inlineField,
}

enum UiErrorTone { neutral, info, caution, critical }

enum UiErrorActionType { retry, login, openSettings, back, dismiss, resubmit }

class UiErrorAction {
  const UiErrorAction({required this.type, required this.label});

  final UiErrorActionType type;
  final String label;
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
}

class UiErrorSemanticResolver {
  const UiErrorSemanticResolver._();

  static AppLocalizations? _maybeL10n(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static String _retryLabel(BuildContext context) {
    return UITextConstants.tryAgain;
  }

  static String _confirmLabel(BuildContext context) {
    return _maybeL10n(context)?.confirm ?? UITextConstants.confirm;
  }

  static String _openSettingsLabel(BuildContext context) {
    return _maybeL10n(context)?.locationOpenSettings ?? '去设置';
  }

  static UiErrorSemantic resolve(
    BuildContext context, {
    required Object error,
    required UiErrorCategory category,
    required UiErrorScope scope,
    AuthGateReason? authGateReason,
    AuthContinuation? continuation,
    bool allowRetry = true,
    bool allowOpenSettings = false,
    UiErrorPresentation? presentation,
    UiErrorTone? tone,
  }) {
    final failure = _runtimeFailureFromError(error);
    final recoveryAction = _deriveRecoveryAction(
      error,
      failure,
      category: category,
      allowRetry: allowRetry,
      allowOpenSettings: allowOpenSettings,
    );
    final domainMessage = _domainMessage(context, error, category: category);
    final fallbackMessage = _fallbackMessage(
      context,
      error: error,
      category: category,
      failure: failure,
      authGateReason: authGateReason,
      allowOpenSettings: allowOpenSettings,
    );
    final message = domainMessage ?? fallbackMessage;
    final sourceCode = _sourceCode(error, failure);
    final copyKey = _copyKey(
      error,
      failure,
      category: category,
      allowOpenSettings: allowOpenSettings,
    );
    final title = _title(
      error: error,
      category: category,
      authGateReason: authGateReason,
      failure: failure,
      allowOpenSettings: allowOpenSettings,
    );
    final secondaryMessage = _secondaryMessage(
      authGateReason: authGateReason,
      continuation: continuation,
      failure: failure,
    );
    return UiErrorSemantic(
      category: category,
      scope: scope,
      title: title,
      message: message,
      secondaryMessage: secondaryMessage,
      primaryAction: _primaryAction(
        context,
        category: category,
        recoveryAction: recoveryAction,
        authGateReason: authGateReason,
        failure: failure,
        allowRetry: allowRetry,
        allowOpenSettings: allowOpenSettings,
      ),
      secondaryAction: _secondaryAction(category: category, scope: scope),
      dismissible: scope == UiErrorScope.global || scope == UiErrorScope.dialog,
      sourceCode: sourceCode,
      failureKind: failure?.kind,
      copyKey: copyKey,
      recoveryAction: recoveryAction,
      presentation:
          presentation ?? _presentationFor(category: category, scope: scope),
      tone:
          tone ??
          _toneFor(
            category: category,
            failure: failure,
            allowOpenSettings: allowOpenSettings,
          ),
    );
  }

  static UiErrorSemantic authRequired(
    BuildContext context, {
    required AuthGateReason reason,
    AuthContinuation? continuation,
    UiErrorScope scope = UiErrorScope.global,
  }) {
    return UiErrorSemantic(
      category: UiErrorCategory.authRequired,
      scope: scope,
      title: reason.title,
      message: reason.prompt,
      secondaryMessage: _secondaryMessage(
        authGateReason: reason,
        continuation: continuation,
        failure: null,
      ),
      primaryAction: UiErrorAction(
        type: UiErrorActionType.login,
        label: UITextConstants.login,
      ),
      secondaryAction: UiErrorAction(
        type: UiErrorActionType.dismiss,
        label: UITextConstants.loginLater,
      ),
      dismissible: true,
      copyKey: 'authRequired',
      recoveryAction: RuntimeRecoveryAction.surface,
      presentation: UiErrorPresentation.gateCard,
      tone: UiErrorTone.info,
    );
  }

  static UiErrorPresentation _presentationFor({
    required UiErrorCategory category,
    required UiErrorScope scope,
  }) {
    if (scope == UiErrorScope.inlineField) {
      return UiErrorPresentation.inlineField;
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

  static UiErrorTone _toneFor({
    required UiErrorCategory category,
    required RuntimeFailureBase? failure,
    required bool allowOpenSettings,
  }) {
    if (category == UiErrorCategory.authRequired ||
        category == UiErrorCategory.permissionRequired ||
        allowOpenSettings) {
      return UiErrorTone.info;
    }
    if (category == UiErrorCategory.validation ||
        category == UiErrorCategory.rateLimited ||
        failure?.kind == RuntimeFailureKind.validation ||
        failure?.kind == RuntimeFailureKind.rateLimited) {
      return UiErrorTone.caution;
    }
    return UiErrorTone.neutral;
  }

  static RuntimeRecoveryAction _deriveRecoveryAction(
    Object error,
    RuntimeFailureBase? failure, {
    required UiErrorCategory category,
    required bool allowRetry,
    required bool allowOpenSettings,
  }) {
    if (allowOpenSettings ||
        category == UiErrorCategory.permissionRequired ||
        failure?.nature == RuntimeFailureNature.requiresPermission) {
      return RuntimeRecoveryAction.surface;
    }
    if (category == UiErrorCategory.authRequired ||
        failure?.kind == RuntimeFailureKind.auth ||
        (error is CloudException &&
            error.type == CloudErrorType.unauthorized)) {
      return RuntimeRecoveryAction.surface;
    }
    if (failure?.kind == RuntimeFailureKind.validation ||
        category == UiErrorCategory.validation) {
      return category == UiErrorCategory.submit
          ? RuntimeRecoveryAction.compensate
          : RuntimeRecoveryAction.surface;
    }
    if (error is CloudException) {
      final retryableCloud =
          error.type == CloudErrorType.timeout ||
          error.type == CloudErrorType.network ||
          error.type == CloudErrorType.server ||
          error.type == CloudErrorType.invalidResponse ||
          error.type == CloudErrorType.unknown;
      if (allowRetry && retryableCloud) {
        return RuntimeRecoveryAction.retry;
      }
      if (error.type == CloudErrorType.notFound ||
          error.type == CloudErrorType.forbidden) {
        return RuntimeRecoveryAction.surface;
      }
    }
    if (allowRetry &&
        (failure?.nature == RuntimeFailureNature.transient ||
            failure?.kind == RuntimeFailureKind.timeout ||
            failure?.kind == RuntimeFailureKind.network ||
            failure?.kind == RuntimeFailureKind.unavailable ||
            failure?.kind == RuntimeFailureKind.rateLimited)) {
      return RuntimeRecoveryAction.retry;
    }
    if (allowRetry && failure == null) {
      return RuntimeRecoveryAction.retry;
    }
    return RuntimeRecoveryAction.surface;
  }

  static String? _sourceCode(Object error, RuntimeFailureBase? failure) {
    if (error is CloudException && (error.code?.trim().isNotEmpty ?? false)) {
      return error.code!.trim();
    }
    final code = failure?.code.trim() ?? '';
    return code.isEmpty ? null : code;
  }

  static String? _domainMessage(
    BuildContext context,
    Object error, {
    required UiErrorCategory category,
  }) {
    if (category == UiErrorCategory.listAppend ||
        category == UiErrorCategory.backgroundAction) {
      return null;
    }
    final l10n = _maybeL10n(context);
    if (error is CloudException) {
      final userMessage = error.userMessage?.trim() ?? '';
      if (userMessage.isNotEmpty) {
        return userMessage;
      }
      final code = error.code?.trim() ?? '';
      if (code.isEmpty) {
        final localMessage = error.message.trim();
        if (error.statusCode == null && localMessage.isNotEmpty) {
          return localMessage;
        }
        return null;
      }
      if (category == UiErrorCategory.pageLoad ||
          category == UiErrorCategory.sectionLoad) {
        return null;
      }
      if (code.startsWith('CONTENT.')) {
        final contentError = ContentErrorCode.fromCode(code);
        if (contentError != ContentErrorCode.unknown) {
          if (l10n != null) {
            return _localizedContentMessage(l10n, contentError);
          }
          return ContentErrorMessages.zh[contentError] ??
              UITextConstants.contentUnavailableReason;
        }
      }
      if (code.startsWith('ENTITY.')) {
        final entityError = EntityErrorCode.fromCode(code);
        if (entityError != EntityErrorCode.unknown) {
          if (l10n != null) {
            return _localizedDefaultMessage(
              l10n,
              zh:
                  EntityErrorMessages.zh[entityError] ??
                  entityError.defaultMessage,
              en:
                  EntityErrorMessages.en[entityError] ??
                  entityError.defaultMessage,
            );
          }
          return EntityErrorMessages.zh[entityError] ??
              entityError.defaultMessage;
        }
      }
      if (code.startsWith('CIRCLE.')) {
        final circleError = CircleErrorCode.fromCode(code);
        if (circleError != CircleErrorCode.unknown) {
          if (l10n != null) {
            return _localizedDefaultMessage(
              l10n,
              zh:
                  CircleErrorMessages.zh[circleError] ??
                  circleError.defaultMessage,
              en:
                  CircleErrorMessages.en[circleError] ??
                  circleError.defaultMessage,
            );
          }
          return CircleErrorMessages.zh[circleError] ??
              circleError.defaultMessage;
        }
      }
      if (code.startsWith('CHAT.')) {
        final chatError = ChatErrorCode.fromCode(code);
        if (chatError != ChatErrorCode.unknown) {
          if (l10n != null) {
            return _localizedDefaultMessage(
              l10n,
              zh: chatError.defaultMessage,
              en: chatError.defaultMessage,
            );
          }
          return chatError.defaultMessage;
        }
      }
      if (code.startsWith('USER.')) {
        final userError = UserErrorCode.fromCode(code);
        if (userError != null) {
          if (l10n != null) {
            return _localizedDefaultMessage(
              l10n,
              zh: userError.defaultMessage,
              en: userError.defaultMessage,
            );
          }
          return userError.defaultMessage;
        }
      }
      if (code.startsWith('RTC.')) {
        final rtcError = RtcErrorCode.fromCode(code);
        if (rtcError != null) {
          if (l10n != null) {
            return _localizedDefaultMessage(
              l10n,
              zh: rtcError.defaultMessage,
              en: rtcError.defaultMessage,
            );
          }
          return rtcError.defaultMessage;
        }
      }
      if (code.startsWith('INTEGRATION.')) {
        final integrationError = IntegrationLocationErrorCode.fromCode(code);
        if (integrationError != IntegrationLocationErrorCode.unknown) {
          if (l10n != null) {
            return integrationError.toDisplayMessage(l10n);
          }
          return IntegrationLocationErrorMessages.zh[integrationError] ??
              UITextConstants.contentLoadSoftFailed;
        }
      }
    }
    return null;
  }

  static String _fallbackMessage(
    BuildContext context, {
    required Object error,
    required UiErrorCategory category,
    required RuntimeFailureBase? failure,
    AuthGateReason? authGateReason,
    required bool allowOpenSettings,
  }) {
    final failureKind = _effectiveFailureKind(error, failure);
    if (category == UiErrorCategory.authRequired && authGateReason != null) {
      return authGateReason.prompt;
    }
    if (allowOpenSettings ||
        category == UiErrorCategory.permissionRequired ||
        failure?.nature == RuntimeFailureNature.requiresPermission) {
      return UITextConstants.authPermissionDenied;
    }
    return switch (category) {
      UiErrorCategory.pageLoad ||
      UiErrorCategory.sectionLoad => switch (failureKind) {
        RuntimeFailureKind.auth => UITextConstants.needLogin,
        RuntimeFailureKind.notFound => _notFoundMessage(error, failure),
        RuntimeFailureKind.network ||
        RuntimeFailureKind.timeout ||
        RuntimeFailureKind.unavailable => UITextConstants.pageLoadFailedMessage,
        _ => UITextConstants.pageLoadFailedMessage,
      },
      UiErrorCategory.listAppend => UITextConstants.appendFailedRetry,
      UiErrorCategory.submit => switch (failure?.kind) {
        RuntimeFailureKind.validation => UITextConstants.validationCheckFields,
        RuntimeFailureKind.auth =>
          authGateReason?.prompt ?? UITextConstants.loginThenRetry,
        RuntimeFailureKind.rateLimited => UITextConstants.rateLimitedRetryLater,
        _ => UITextConstants.operationFailedRetry,
      },
      UiErrorCategory.validation => UITextConstants.validationCheckFields,
      UiErrorCategory.notFound => _notFoundMessage(error, failure),
      UiErrorCategory.rateLimited => UITextConstants.rateLimitedRetryLater,
      UiErrorCategory.backgroundAction => UITextConstants.operationFailedRetry,
      UiErrorCategory.authRequired =>
        authGateReason?.prompt ?? UITextConstants.loginThenRetry,
      UiErrorCategory.permissionRequired =>
        UITextConstants.authPermissionDenied,
    };
  }

  static String _title({
    required Object error,
    required UiErrorCategory category,
    required AuthGateReason? authGateReason,
    required RuntimeFailureBase? failure,
    required bool allowOpenSettings,
  }) {
    final failureKind = _effectiveFailureKind(error, failure);
    if (category == UiErrorCategory.authRequired && authGateReason != null) {
      return authGateReason.title;
    }
    if (allowOpenSettings ||
        category == UiErrorCategory.permissionRequired ||
        failure?.nature == RuntimeFailureNature.requiresPermission) {
      return UITextConstants.permissionRequiredTitle;
    }
    return switch (category) {
      UiErrorCategory.pageLoad => switch (failureKind) {
        RuntimeFailureKind.notFound => _pageLoadTitle(error, failure),
        RuntimeFailureKind.network ||
        RuntimeFailureKind.timeout ||
        RuntimeFailureKind.unavailable => _pageLoadTitle(error, failure),
        _ => _pageLoadTitle(error, failure),
      },
      UiErrorCategory.sectionLoad => _sectionLoadTitle(error, failure),
      UiErrorCategory.listAppend => UITextConstants.appendFailedTitle,
      UiErrorCategory.submit => UITextConstants.submitNotCompleted,
      UiErrorCategory.authRequired => UITextConstants.needLogin,
      UiErrorCategory.permissionRequired =>
        UITextConstants.permissionRequiredTitle,
      UiErrorCategory.validation => UITextConstants.checkFieldsTitle,
      UiErrorCategory.notFound => UITextConstants.contentUnavailable,
      UiErrorCategory.rateLimited => UITextConstants.rateLimitedRetryLater,
      UiErrorCategory.backgroundAction => UITextConstants.operationFailed,
    };
  }

  static String _pageLoadTitle(Object error, RuntimeFailureBase? failure) {
    final code = _sourceCode(error, failure) ?? '';
    if (code.startsWith('CONTENT.')) {
      return UITextConstants.workOpenFailedTitle;
    }
    if (code.startsWith('CHAT.')) {
      return UITextConstants.chatOpenFailedTitle;
    }
    if (code.startsWith('ENTITY.')) {
      return UITextConstants.homepageLoadFailedTitle;
    }
    if (code.startsWith('USER.')) {
      return UITextConstants.userProfileLoadFailedTitle;
    }
    if (code.startsWith('CIRCLE.')) {
      return UITextConstants.circleLoadFailedTitle;
    }
    return UITextConstants.pageLoadFailedTitle;
  }

  static String _sectionLoadTitle(Object error, RuntimeFailureBase? failure) {
    final code = _sourceCode(error, failure) ?? '';
    if (code.startsWith('CONTENT.') && code.contains('comment')) {
      return UITextConstants.commentLoadFailedTitle;
    }
    if (code.startsWith('CIRCLE.')) {
      return UITextConstants.sectionLoadFailedTitleDefault;
    }
    return UITextConstants.sectionLoadFailedTitleDefault;
  }

  static String _notFoundMessage(Object error, RuntimeFailureBase? failure) {
    final code = _sourceCode(error, failure) ?? '';
    if (code.startsWith('CHAT.')) {
      return UITextConstants.chatOpenFailedMessage;
    }
    return UITextConstants.contentUnavailableReason;
  }

  static String? _secondaryMessage({
    required AuthGateReason? authGateReason,
    required AuthContinuation? continuation,
    required RuntimeFailureBase? failure,
  }) {
    if (authGateReason == null && continuation == null) {
      return failure?.kind == RuntimeFailureKind.auth
          ? UITextConstants.loginToContinue
          : null;
    }
    if (continuation is SubmitCommentContinuation) {
      return '登录后将继续提交刚刚输入的评论';
    }
    if (continuation is FollowProfileContinuation) {
      return '登录后将继续关注当前对象';
    }
    if (continuation is GreetProfileContinuation) {
      return '登录后将继续向当前对象发送打招呼';
    }
    if (continuation is OpenDirectConversationContinuation) {
      return '登录后将继续打开正式私信会话';
    }
    if (continuation is StartDirectCallContinuation) {
      return switch (continuation.callType) {
        'video' => '登录后将继续发起视频通话',
        _ => '登录后将继续发起语音通话',
      };
    }
    if (continuation is JoinCircleContinuation) {
      return '登录后将继续加入当前圈子';
    }
    if (continuation is OpenSheetContinuation) {
      return switch (continuation.sheet) {
        AuthContinuationSheet.addContact => '登录后将继续打开添加联系人流程',
        AuthContinuationSheet.startGroupChat => '登录后将继续打开发起讨论流程',
        AuthContinuationSheet.createCircle => '登录后将继续打开建圈流程',
      };
    }
    return authGateReason?.prompt;
  }

  static String _copyKey(
    Object error,
    RuntimeFailureBase? failure, {
    required UiErrorCategory category,
    required bool allowOpenSettings,
  }) {
    if (allowOpenSettings || category == UiErrorCategory.permissionRequired) {
      return 'permissionRequiredTitle';
    }
    if (category == UiErrorCategory.listAppend) {
      return 'appendFailedRetry';
    }
    if (category == UiErrorCategory.backgroundAction) {
      return 'operationFailedRetry';
    }
    if (category == UiErrorCategory.submit) {
      return 'submitNotCompleted';
    }
    final code = _sourceCode(error, failure) ?? '';
    if (code.startsWith('CHAT.')) {
      return 'chatOpenFailedTitle';
    }
    if (code.startsWith('CONTENT.')) {
      if (code.contains('comment')) {
        return 'commentLoadFailedTitle';
      }
      return 'workOpenFailedTitle';
    }
    if (code.startsWith('ENTITY.')) {
      return 'homepageLoadFailedTitle';
    }
    if (code.startsWith('USER.')) {
      return 'userProfileLoadFailedTitle';
    }
    if (code.startsWith('CIRCLE.')) {
      return 'circleLoadFailedTitle';
    }
    if (category == UiErrorCategory.pageLoad) {
      return 'pageLoadFailedTitle';
    }
    if (category == UiErrorCategory.sectionLoad) {
      return 'sectionLoadFailedTitle';
    }
    return category.name;
  }

  static UiErrorAction? _primaryAction(
    BuildContext context, {
    required UiErrorCategory category,
    required RuntimeRecoveryAction recoveryAction,
    required AuthGateReason? authGateReason,
    required RuntimeFailureBase? failure,
    required bool allowRetry,
    required bool allowOpenSettings,
  }) {
    if (allowOpenSettings || category == UiErrorCategory.permissionRequired) {
      return UiErrorAction(
        type: UiErrorActionType.openSettings,
        label: _openSettingsLabel(context),
      );
    }
    if (category == UiErrorCategory.authRequired ||
        authGateReason != null ||
        failure?.kind == RuntimeFailureKind.auth) {
      return const UiErrorAction(
        type: UiErrorActionType.login,
        label: UITextConstants.login,
      );
    }
    if (category == UiErrorCategory.submit &&
        recoveryAction == RuntimeRecoveryAction.compensate) {
      return UiErrorAction(
        type: UiErrorActionType.resubmit,
        label: _confirmLabel(context),
      );
    }
    if (allowRetry && recoveryAction == RuntimeRecoveryAction.retry) {
      return UiErrorAction(
        type: UiErrorActionType.retry,
        label: _retryLabel(context),
      );
    }
    return null;
  }

  static UiErrorAction? _secondaryAction({
    required UiErrorCategory category,
    required UiErrorScope scope,
  }) {
    if (scope == UiErrorScope.dialog ||
        category == UiErrorCategory.authRequired) {
      return const UiErrorAction(
        type: UiErrorActionType.dismiss,
        label: UITextConstants.cancel,
      );
    }
    return null;
  }

  static String _localizedDefaultMessage(
    AppLocalizations l10n, {
    required String zh,
    required String en,
  }) {
    return l10n.localeName.startsWith('zh') ? zh : en;
  }

  static String _localizedContentMessage(
    AppLocalizations l10n,
    ContentErrorCode code,
  ) {
    final zh = ContentErrorMessages.zh[code];
    final en = ContentErrorMessages.en[code];
    if (zh == null || en == null) {
      return l10n.loadFailed;
    }
    return _localizedDefaultMessage(l10n, zh: zh, en: en);
  }

  static RuntimeFailureBase? _runtimeFailureFromError(Object error) {
    if (error is CloudException) {
      return error.runtimeFailure;
    }
    if (error is RuntimeFailureBase) {
      return error;
    }
    return null;
  }

  static RuntimeFailureKind? _effectiveFailureKind(
    Object error,
    RuntimeFailureBase? failure,
  ) {
    if (failure != null) {
      return failure.kind;
    }
    if (error is! CloudException) {
      return null;
    }
    return switch (error.type) {
      CloudErrorType.timeout => RuntimeFailureKind.timeout,
      CloudErrorType.network => RuntimeFailureKind.network,
      CloudErrorType.unauthorized => RuntimeFailureKind.auth,
      CloudErrorType.forbidden => RuntimeFailureKind.permission,
      CloudErrorType.notFound => RuntimeFailureKind.notFound,
      CloudErrorType.invalidResponse => RuntimeFailureKind.contract,
      CloudErrorType.server => RuntimeFailureKind.unavailable,
      CloudErrorType.unknown => RuntimeFailureKind.internal,
    };
  }
}
