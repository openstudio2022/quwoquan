import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/chat/generated/chat_errors.g.dart';
import 'package:quwoquan_app/cloud/circle/generated/circle_errors.g.dart';
import 'package:quwoquan_app/cloud/circle/generated/circle_membership_errors.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
import 'package:quwoquan_app/cloud/rtc/generated/rtc_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import 'app_user_recovery.dart';
import 'ui_error_appearance.dart';
import 'ui_error_models.dart';
export 'app_user_recovery.dart';
export 'ui_error_appearance.dart';
export 'ui_error_models.dart';

class UiErrorSemanticResolver {
  const UiErrorSemanticResolver._();

  static AppLocalizations? _maybeL10n(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static String _retryLabel(
    BuildContext context, {
    required UiErrorCategory category,
  }) {
    return category == UiErrorCategory.pageLoad
        ? SearchText.reload
        : ContentText.tryAgain;
  }

  static String _confirmLabel(BuildContext context) {
    return _maybeL10n(context)?.confirm ?? FoundationText.confirm;
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
    bool verifiedUpdateAvailable = false,
    UiErrorPresentation? presentation,
    UiErrorTone? tone,
    UiErrorAppearanceMode appearanceMode = UiErrorAppearanceMode.inherit,
    String? sourceRouteId,
    String? sourceSurfaceId,
    String? sourceOperationId,
  }) {
    final failure = _runtimeFailureFromError(error);
    final effectiveSourceOperationId =
        error is CloudException &&
            (error.sourceOperationId?.trim().isNotEmpty ?? false)
        ? error.sourceOperationId!.trim()
        : sourceOperationId;
    if (verifiedUpdateAvailable ||
        allowOpenSettings ||
        _usesUserRecoveryContract(category)) {
      final group = AppUserRecoveryContract.classify(
        error: error,
        failure: failure,
        category: category,
        allowOpenSettings: allowOpenSettings,
        verifiedUpdateAvailable: verifiedUpdateAvailable,
        sourceOperationId: effectiveSourceOperationId,
      );
      return AppUserRecoveryContract.semanticFor(
        group: group,
        category: category,
        scope: scope,
        retryAfterSeconds: AppUserRecoveryContract.retryAfterSeconds(error),
        sourceCode: _sourceCode(error, failure),
        failureKind: failure?.kind,
        presentation: presentation,
        tone: tone,
        appearanceMode: appearanceMode,
        sourceRouteId: sourceRouteId,
        sourceSurfaceId: sourceSurfaceId,
        sourceOperationId: effectiveSourceOperationId,
        requestId: error is CloudException ? error.requestId : null,
        traceId: error is CloudException ? error.traceId : null,
      );
    }
    final recoveryAction = _deriveRecoveryAction(
      error,
      failure,
      category: category,
      allowRetry: allowRetry,
      allowOpenSettings: allowOpenSettings,
    );
    final domainMessage = _domainMessage(
      context,
      error,
      failure: failure,
      category: category,
      sourceOperationId: effectiveSourceOperationId,
    );
    final fallbackMessage = _fallbackMessage(
      context,
      error: error,
      category: category,
      failure: failure,
      authGateReason: authGateReason,
      allowOpenSettings: allowOpenSettings,
      sourceOperationId: effectiveSourceOperationId,
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
      sourceOperationId: effectiveSourceOperationId,
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
        error: error,
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
      appearanceMode: appearanceMode,
      sourceRouteId: sourceRouteId,
      sourceSurfaceId: sourceSurfaceId,
      sourceOperationId: effectiveSourceOperationId,
      requestId: error is CloudException ? error.requestId : null,
      traceId: error is CloudException ? error.traceId : null,
    );
  }

  static UiErrorSemantic authRequired(
    BuildContext context, {
    required AuthGateReason reason,
    AuthContinuation? continuation,
    UiErrorScope scope = UiErrorScope.global,
  }) {
    const group = AppUserRecoveryGroup.loginAgain;
    final copy = AppUserRecoveryContract.copyFor(group);
    return UiErrorSemantic(
      category: UiErrorCategory.authRequired,
      scope: scope,
      title: copy.title,
      message: copy.message,
      primaryAction: copy.action,
      dismissible: true,
      copyKey: 'recovery.loginAgain',
      recoveryAction: copy.recoveryAction,
      presentation: UiErrorPresentation.gateCard,
      tone: UiErrorTone.info,
      userRecoveryGroup: group,
    );
  }

  static bool _usesUserRecoveryContract(UiErrorCategory category) {
    return switch (category) {
      UiErrorCategory.submit || UiErrorCategory.validation => false,
      _ => true,
    };
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
    if (_statusCode(error, failure) == 409 && allowRetry) {
      return RuntimeRecoveryAction.retry;
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
          (error.type == CloudErrorType.network &&
              failure?.nature == RuntimeFailureNature.transient) ||
          error.type == CloudErrorType.server ||
          error.type == CloudErrorType.rateLimited;
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
            failure?.kind == RuntimeFailureKind.unavailable ||
            failure?.kind == RuntimeFailureKind.rateLimited)) {
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
    required RuntimeFailureBase? failure,
    required UiErrorCategory category,
    String? sourceOperationId,
  }) {
    if (category == UiErrorCategory.listAppend ||
        category == UiErrorCategory.backgroundAction ||
        category == UiErrorCategory.sectionLoad) {
      return null;
    }
    final l10n = _maybeL10n(context);
    if (error is CloudException) {
      final code = error.code?.trim() ?? '';
      if (category == UiErrorCategory.pageLoad &&
          (_statusCode(error, failure) != null ||
              code.startsWith('APP.') ||
              sourceOperationId == 'GetFeed')) {
        // 页面级基础设施与 Feed 路由错误由统一语义表决定，禁止被服务端
        // 泛化 userMessage 或领域默认文案重新解释为其它原因。
        return null;
      }
      final userMessage = error.userMessage?.trim() ?? '';
      if (userMessage.isNotEmpty) {
        return userMessage;
      }
      if (code.isEmpty) {
        final localMessage = error.message.trim();
        if (category != UiErrorCategory.pageLoad && localMessage.isNotEmpty) {
          return localMessage;
        }
        return null;
      }
      if (code.startsWith('CONTENT.')) {
        final contentError = ContentErrorCode.fromCode(code);
        if (contentError != ContentErrorCode.unknown) {
          if (l10n != null) {
            return _localizedContentMessage(l10n, contentError);
          }
          return ContentErrorMessages.zh[contentError] ??
              ContentText.contentUnavailableReason;
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
        final membershipError = CircleMembershipErrorCode.fromCode(code);
        if (membershipError != CircleMembershipErrorCode.unknown) {
          if (l10n != null) {
            return _localizedDefaultMessage(
              l10n,
              zh:
                  CircleMembershipErrorMessages.zh[membershipError] ??
                  membershipError.defaultMessage,
              en:
                  CircleMembershipErrorMessages.en[membershipError] ??
                  membershipError.defaultMessage,
            );
          }
          return CircleMembershipErrorMessages.zh[membershipError] ??
              membershipError.defaultMessage;
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
            return _localizedDefaultMessage(
              l10n,
              zh:
                  IntegrationLocationErrorMessages.zh[integrationError] ??
                  FoundationText.contentLoadSoftFailed,
              en:
                  IntegrationLocationErrorMessages.en[integrationError] ??
                  FoundationText.contentLoadSoftFailed,
            );
          }
          return IntegrationLocationErrorMessages.zh[integrationError] ??
              FoundationText.contentLoadSoftFailed;
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
    String? sourceOperationId,
  }) {
    final failureKind = _effectiveFailureKind(error, failure);
    if (category == UiErrorCategory.authRequired && authGateReason != null) {
      return authGateReason.prompt;
    }
    if (allowOpenSettings ||
        category == UiErrorCategory.permissionRequired ||
        failure?.nature == RuntimeFailureNature.requiresPermission) {
      return FoundationText.authPermissionDenied;
    }
    return switch (category) {
      UiErrorCategory.pageLoad => _pageLoadMessage(
        error,
        failure,
        sourceOperationId: sourceOperationId,
      ),
      UiErrorCategory.sectionLoad => switch (failureKind) {
        RuntimeFailureKind.auth => FoundationText.needLogin,
        RuntimeFailureKind.notFound => _notFoundMessage(error, failure),
        RuntimeFailureKind.network ||
        RuntimeFailureKind.timeout ||
        RuntimeFailureKind.unavailable => SearchText.pageLoadFailedMessage,
        _ => SearchText.pageLoadFailedMessage,
      },
      UiErrorCategory.listAppend => FoundationText.appendFailedRetry,
      UiErrorCategory.submit => switch (failure?.kind) {
        RuntimeFailureKind.validation => ContentText.validationCheckFields,
        RuntimeFailureKind.auth =>
          authGateReason?.prompt ?? ContentText.loginThenRetry,
        RuntimeFailureKind.rateLimited => ContentText.rateLimitedRetryLater,
        _ => ContentText.operationFailedRetry,
      },
      UiErrorCategory.validation => ContentText.validationCheckFields,
      UiErrorCategory.notFound => _notFoundMessage(error, failure),
      UiErrorCategory.rateLimited => ContentText.rateLimitedRetryLater,
      UiErrorCategory.backgroundAction => ContentText.operationFailedRetry,
      UiErrorCategory.authRequired =>
        authGateReason?.prompt ?? ContentText.loginThenRetry,
      UiErrorCategory.permissionRequired => FoundationText.authPermissionDenied,
    };
  }

  static String _title({
    required Object error,
    required UiErrorCategory category,
    required AuthGateReason? authGateReason,
    required RuntimeFailureBase? failure,
    required bool allowOpenSettings,
    String? sourceOperationId,
  }) {
    if (category == UiErrorCategory.authRequired && authGateReason != null) {
      return authGateReason.title;
    }
    if (allowOpenSettings ||
        category == UiErrorCategory.permissionRequired ||
        failure?.nature == RuntimeFailureNature.requiresPermission) {
      return ContentText.permissionRequiredTitle;
    }
    return switch (category) {
      UiErrorCategory.pageLoad => _pageLoadTitle(
        error,
        failure,
        sourceOperationId: sourceOperationId,
      ),
      UiErrorCategory.sectionLoad => _sectionLoadTitle(error, failure),
      UiErrorCategory.listAppend => SearchText.appendFailedTitle,
      UiErrorCategory.submit => ContentText.submitNotCompleted,
      UiErrorCategory.authRequired => FoundationText.needLogin,
      UiErrorCategory.permissionRequired => ContentText.permissionRequiredTitle,
      UiErrorCategory.validation => ContentText.checkFieldsTitle,
      UiErrorCategory.notFound => ContentText.contentUnavailable,
      UiErrorCategory.rateLimited => ContentText.rateLimitedRetryLater,
      UiErrorCategory.backgroundAction => CreationText.operationFailed,
    };
  }

  static String _pageLoadTitle(
    Object error,
    RuntimeFailureBase? failure, {
    String? sourceOperationId,
  }) {
    final code = _sourceCode(error, failure) ?? '';
    final status = _statusCode(error, failure);
    if (code == RuntimeFailureCodes.appNetworkOffline) {
      return SearchText.deviceOfflineTitle;
    }
    if (code == RuntimeFailureCodes.appNetworkNameResolutionFailed) {
      return SearchText.serviceNameResolutionTitle;
    }
    if (code == RuntimeFailureCodes.appNetworkConnectionRefused ||
        code == RuntimeFailureCodes.appNetworkConnectionFailed) {
      return SearchText.serviceConnectionTitle;
    }
    if (code == RuntimeFailureCodes.appNetworkSecureConnectionFailed) {
      return SearchText.secureConnectionTitle;
    }
    if (code == RuntimeFailureCodes.appTimeoutRequestTimeout) {
      return SearchText.contentLoadTimeoutTitle;
    }
    if (status == 401) return SearchText.sessionExpiredTitle;
    if (status == 403) return SearchText.contentForbiddenTitle;
    if (status == 410 && code == ContentErrorCode.contentDeleted.code) {
      return SearchText.recoveryContentGoneTitle;
    }
    if (status == 404) {
      return sourceOperationId == 'GetFeed'
          ? SearchText.feedVersionMismatchTitle
          : SearchText.contentMissingTitle;
    }
    if (status == 400 || status == 422) {
      return SearchText.contentRequestInvalidTitle;
    }
    if (status == 409) return SearchText.contentConflictTitle;
    if (status == 429) return SearchText.contentRateLimitedTitle;
    if (_isContentUpstreamTimeout(status: status, code: code)) {
      return SearchText.contentServiceTimeoutTitle;
    }
    if (_isContentDependencyUnavailable(status: status, code: code)) {
      return SearchText.contentServiceUnavailableTitle;
    }
    if (status != null && status >= 500) {
      return SearchText.contentServiceFailedTitle;
    }
    if (code == RuntimeFailureCodes.appContractInvalidJson ||
        code == RuntimeFailureCodes.appContractInvalidResponse) {
      return SearchText.invalidContentResponseTitle;
    }
    if (code.startsWith('ENTITY.')) {
      return ContentText.homepageLoadFailedTitle;
    }
    if (code.startsWith('USER.')) {
      return ContentText.userProfileLoadFailedTitle;
    }
    if (code.startsWith('CIRCLE.')) {
      return ContentText.circleLoadFailedTitle;
    }
    if (code.startsWith('CHAT.')) {
      return ChatText.chatOpenFailedTitle;
    }
    if (code.startsWith('CONTENT.')) {
      return ContentText.workOpenFailedTitle;
    }
    return SearchText.pageLoadFailedTitle;
  }

  static String _pageLoadMessage(
    Object error,
    RuntimeFailureBase? failure, {
    String? sourceOperationId,
  }) {
    final code = _sourceCode(error, failure) ?? '';
    final status = _statusCode(error, failure);
    if (code == RuntimeFailureCodes.appNetworkOffline) {
      return SearchText.deviceOfflineMessage;
    }
    if (code == RuntimeFailureCodes.appNetworkNameResolutionFailed) {
      return SearchText.serviceNameResolutionMessage;
    }
    if (code == RuntimeFailureCodes.appNetworkConnectionRefused ||
        code == RuntimeFailureCodes.appNetworkConnectionFailed) {
      return SearchText.serviceConnectionMessage;
    }
    if (code == RuntimeFailureCodes.appNetworkSecureConnectionFailed) {
      return SearchText.secureConnectionMessage;
    }
    if (code == RuntimeFailureCodes.appTimeoutRequestTimeout) {
      return SearchText.contentLoadTimeoutMessage;
    }
    if (status == 401) return SearchText.sessionExpiredMessage;
    if (status == 403) return SearchText.contentForbiddenMessage;
    if (status == 410 && code == ContentErrorCode.contentDeleted.code) {
      return SearchText.recoveryContentGoneMessage;
    }
    if (status == 404) {
      return sourceOperationId == 'GetFeed'
          ? SearchText.feedVersionMismatchMessage
          : SearchText.contentMissingMessage;
    }
    if (status == 400 || status == 422) {
      return SearchText.contentRequestInvalidMessage;
    }
    if (status == 409) return SearchText.contentConflictMessage;
    if (status == 429) {
      final seconds = error is CloudException
          ? error.retryAfter?.inSeconds
          : null;
      return SearchText.contentRateLimitedMessageFor(seconds ?? 0);
    }
    if (_isContentUpstreamTimeout(status: status, code: code)) {
      return SearchText.contentServiceTimeoutMessage;
    }
    if (_isContentDependencyUnavailable(status: status, code: code)) {
      return SearchText.contentServiceUnavailableMessage;
    }
    if (status != null && status >= 500) {
      return SearchText.contentServiceFailedMessage;
    }
    if (code == RuntimeFailureCodes.appContractInvalidJson ||
        code == RuntimeFailureCodes.appContractInvalidResponse) {
      return SearchText.invalidContentResponseMessage;
    }
    return SearchText.pageLoadFailedMessage;
  }

  static String _sectionLoadTitle(Object error, RuntimeFailureBase? failure) {
    final code = _sourceCode(error, failure) ?? '';
    if (code.startsWith('CONTENT.') && code.contains('comment')) {
      return ContentText.commentLoadFailedTitle;
    }
    if (code.startsWith('CIRCLE.')) {
      return ContentText.sectionLoadFailedTitleDefault;
    }
    return ContentText.sectionLoadFailedTitleDefault;
  }

  static String _notFoundMessage(Object error, RuntimeFailureBase? failure) {
    final code = _sourceCode(error, failure) ?? '';
    if (code.startsWith('CHAT.')) {
      return ChatText.chatOpenFailedMessage;
    }
    return ContentText.contentUnavailableReason;
  }

  static String? _secondaryMessage({
    required AuthGateReason? authGateReason,
    required AuthContinuation? continuation,
    required RuntimeFailureBase? failure,
  }) {
    if (authGateReason == null && continuation == null) {
      return failure?.kind == RuntimeFailureKind.auth
          ? ContentText.loginToContinue
          : null;
    }
    if (continuation is SubmitCommentContinuation) {
      return '登录后将继续提交刚刚输入的评论';
    }
    if (continuation is FollowHomepageContinuation) {
      return '登录后将继续关注当前主页';
    }
    if (continuation is WishlistHomepageContinuation) {
      return '登录后将继续把当前主页标记为想去';
    }
    if (continuation is OpenHomepageReviewComposerContinuation) {
      return '登录后将继续打开当前主页的评价编辑器';
    }
    if (continuation is OpenHomepageOwnerConversationContinuation) {
      return '登录后将继续联系当前主页的认领主体';
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
    required Object error,
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
        label: FoundationText.login,
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
      final status = _statusCode(error, failure);
      final retryAfterSeconds = status == 429 && error is CloudException
          ? (error.retryAfter?.inSeconds ?? 0)
          : 0;
      return UiErrorAction(
        type: UiErrorActionType.retry,
        label: failure?.transportStatus == 409
            ? SearchText.refresh
            : _retryLabel(context, category: category),
        availableAfterSeconds: retryAfterSeconds,
      );
    }
    return null;
  }

  static UiErrorAction? _secondaryAction({
    required UiErrorCategory category,
    required UiErrorScope scope,
  }) {
    if (scope == UiErrorScope.dialog) {
      return const UiErrorAction(
        type: UiErrorActionType.dismiss,
        label: FoundationText.cancel,
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
    return CloudErrorMapper.runtimeFailureFromException(error);
  }

  static int? _statusCode(Object error, RuntimeFailureBase? failure) {
    if (error is CloudException) return error.statusCode;
    return failure?.transportStatus;
  }

  static bool _isContentUpstreamTimeout({
    required int? status,
    required String code,
  }) {
    return status == 504 || code == ContentErrorCode.upstreamTimeout.code;
  }

  static bool _isContentDependencyUnavailable({
    required int? status,
    required String code,
  }) {
    return status == 503 ||
        code == ContentErrorCode.requiredDependencyUnavailable.code;
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
      CloudErrorType.cancelled => RuntimeFailureKind.cancelled,
      CloudErrorType.network => RuntimeFailureKind.network,
      CloudErrorType.unauthorized => RuntimeFailureKind.auth,
      CloudErrorType.forbidden => RuntimeFailureKind.permission,
      CloudErrorType.notFound => RuntimeFailureKind.notFound,
      CloudErrorType.invalidResponse => RuntimeFailureKind.contract,
      CloudErrorType.server => RuntimeFailureKind.unavailable,
      CloudErrorType.rateLimited => RuntimeFailureKind.rateLimited,
      CloudErrorType.unknown => RuntimeFailureKind.internal,
    };
  }
}
