part of 'login_page.dart';

const Object _loginUnset = Object();

enum LoginSurfaceMode { page, inline }

enum LoginStep {
  resolving,
  oneTap,
  phoneEntry,
  otp,
  socialAuthorizing,
  socialFailed,
  socialPhoneEntry,
  socialPhoneOtp,
  blocked,
  completing,
}

enum LoginOperation {
  idle,
  sendingOtp,
  verifyingOtp,
  openingProvider,
  exchangingTicket,
  completingBinding,
}

enum LoginConsentState { unchecked, accepted, confirming }

enum OtpChallengeState { none, active, resendAvailable, expired, rateLimited }

enum OtpDeliveryState { none, confirming, queued, sent, failed }

enum OtpReadinessState { checking, ready, unavailable }

enum OtpPresentationTone { neutral, error }

enum OtpRecoveryAction { retryVerify, resend, contactSupport, changePhone }

enum LoginOtpPurpose { login, bindPhone }

enum LoginEntryMode { resolving, rememberedSession, carrier, phone, social }

enum LoginFeedbackSurface { phone, otp, page, social, silent }

enum LoginFailureOrigin {
  otpSend,
  otpVerify,
  oneTap,
  returningSession,
  social,
  phoneBinding,
}

enum LoginPendingIntent {
  oneTap,
  sendOtp,
  resendOtp,
  socialWechat,
  socialQq,
  socialAlipay,
}

class LoginAccountHint {
  const LoginAccountHint({
    required this.displayName,
    required this.maskedPhone,
    this.avatarUrl = '',
    this.identityOrigin = '',
    this.nicknameCustomized = false,
  });

  final String displayName;
  final String maskedPhone;
  final String avatarUrl;
  final String identityOrigin;
  final bool nicknameCustomized;

  bool get hasConcreteIdentifier =>
      (nicknameCustomized && displayName.trim().isNotEmpty) ||
      maskedPhone.trim().isNotEmpty;
}

class CarrierPhoneHint {
  const CarrierPhoneHint({
    required this.vendor,
    required this.carrierToken,
    required this.maskedPhone,
    this.registered = false,
    this.accountHint,
  });

  final String vendor;
  final String carrierToken;
  final String maskedPhone;
  final bool registered;
  final LoginAccountHint? accountHint;
}

class LoginFeedback {
  const LoginFeedback({
    required this.message,
    required this.copyKey,
    required this.surface,
    required this.recoveryAction,
    this.cloudError,
    this.sourceCode,
    this.failureKind,
    this.requestId,
    this.traceId,
    this.retryAfterSeconds = 0,
    this.clearOtp = false,
    this.shakeOtp = false,
    this.preserveOtp = false,
  });

  final String message;
  final String copyKey;
  final LoginFeedbackSurface surface;
  final String recoveryAction;
  final CloudException? cloudError;
  final String? sourceCode;
  final String? failureKind;
  final String? requestId;
  final String? traceId;
  final int retryAfterSeconds;
  final bool clearOtp;
  final bool shakeOtp;
  final bool preserveOtp;

  bool get isSilent => surface == LoginFeedbackSurface.silent;

  bool get blocksAccountLogin =>
      sourceCode == UserErrorCode.accountSuspended.code ||
      sourceCode == UserErrorCode.accountDeleted.code;
}

/// The only user-facing projection for OTP delivery, verification and
/// cooldown state. Widgets must not render those internal rails separately.
class OtpPagePresentation {
  const OtpPagePresentation({
    required this.message,
    required this.tone,
    required this.primaryAction,
    required this.secondaryAction,
    required this.resendRemainingSeconds,
    required this.showDeliveryProgress,
    required this.announceKey,
  });

  factory OtpPagePresentation.fromState(LoginFlowState state, DateTime now) {
    final remaining = state.remainingResendSeconds(now);
    final verifying =
        state.operation == LoginOperation.verifyingOtp ||
        state.operation == LoginOperation.completingBinding;
    if (verifying) {
      return OtpPagePresentation(
        message: FoundationText.loginOtpVerifying,
        tone: OtpPresentationTone.neutral,
        primaryAction: null,
        secondaryAction: null,
        resendRemainingSeconds: remaining,
        showDeliveryProgress: true,
        announceKey: 'otp-verifying',
      );
    }

    final feedback = state.feedback;
    if (feedback != null && !feedback.isSilent) {
      OtpRecoveryAction? primary;
      OtpRecoveryAction? secondary;
      switch (feedback.recoveryAction) {
        case 'retryVerifyOtp':
          primary = OtpRecoveryAction.retryVerify;
          if (remaining <= 0) secondary = OtpRecoveryAction.resend;
          break;
        case 'resendOtp':
          if (remaining <= 0) primary = OtpRecoveryAction.resend;
          break;
        case 'waitThenResendOtp':
          if (remaining <= 0) primary = OtpRecoveryAction.resend;
          break;
        case 'openSupport':
          primary = OtpRecoveryAction.contactSupport;
          break;
        case 'changePhone':
        case 'changeMethod':
          primary = OtpRecoveryAction.changePhone;
          break;
        default:
          break;
      }
      return OtpPagePresentation(
        message: feedback.message,
        tone: OtpPresentationTone.error,
        primaryAction: primary,
        secondaryAction: secondary,
        resendRemainingSeconds: remaining,
        showDeliveryProgress: false,
        announceKey: 'otp-error-${feedback.copyKey}',
      );
    }

    if (state.otpDeliveryState == OtpDeliveryState.failed) {
      final message = remaining > 0
          ? FoundationText.loginOtpDeliveryFailedCountdown.replaceFirst(
              '%d',
              remaining.toString(),
            )
          : FoundationText.loginOtpSendFailed;
      return OtpPagePresentation(
        message: message,
        tone: OtpPresentationTone.error,
        primaryAction: remaining <= 0 ? OtpRecoveryAction.resend : null,
        secondaryAction: null,
        resendRemainingSeconds: remaining,
        showDeliveryProgress: false,
        announceKey: 'otp-delivery-failed',
      );
    }

    // Once the user starts typing, delivery detail is no longer the primary
    // task and must not compete with the code input.
    if (state.code.isNotEmpty) {
      return OtpPagePresentation(
        message: '',
        tone: OtpPresentationTone.neutral,
        primaryAction: null,
        secondaryAction: null,
        resendRemainingSeconds: remaining,
        showDeliveryProgress: false,
        announceKey: 'otp-input',
      );
    }

    final message = switch (state.otpDeliveryState) {
      OtpDeliveryState.queued => FoundationText.loginOtpDeliveryQueued,
      OtpDeliveryState.sent => FoundationText.loginOtpDeliverySent,
      OtpDeliveryState.confirming when state.deliveryConfirmationExhausted =>
        FoundationText.loginOtpDeliveryUnknown,
      OtpDeliveryState.confirming => FoundationText.loginOtpDeliveryConfirming,
      OtpDeliveryState.none => FoundationText.loginOtpDeliveryUnknown,
      OtpDeliveryState.failed => '',
    };
    return OtpPagePresentation(
      message: message,
      tone: OtpPresentationTone.neutral,
      primaryAction: null,
      secondaryAction: null,
      resendRemainingSeconds: remaining,
      showDeliveryProgress:
          state.otpDeliveryState == OtpDeliveryState.queued ||
          (state.otpDeliveryState == OtpDeliveryState.confirming &&
              !state.deliveryConfirmationExhausted),
      announceKey: 'otp-delivery-${state.otpDeliveryState.name}',
    );
  }

  final String message;
  final OtpPresentationTone tone;
  final OtpRecoveryAction? primaryAction;
  final OtpRecoveryAction? secondaryAction;
  final int resendRemainingSeconds;
  final bool showDeliveryProgress;
  final String announceKey;

  bool get hasRecoveryActions =>
      primaryAction != null || secondaryAction != null;
}

class LoginFlowState {
  const LoginFlowState({
    required this.step,
    required this.flowId,
    this.operation = LoginOperation.idle,
    this.consentState = LoginConsentState.unchecked,
    this.otpChallengeState = OtpChallengeState.none,
    this.otpDeliveryState = OtpDeliveryState.none,
    this.otpReadinessState = OtpReadinessState.checking,
    this.otpPurpose = LoginOtpPurpose.login,
    this.entryMode = LoginEntryMode.resolving,
    this.phone = '',
    this.maskedPhone = '',
    this.code = '',
    this.challengeId = '',
    this.deliveryRequestId = '',
    this.idempotencyKey = '',
    this.provider = '',
    this.bindingTicket = '',
    this.resendDeadline,
    this.bindingDeadline,
    this.pendingOtpExpiresAt,
    this.feedback,
    this.deliveryConfirmationExhausted = false,
    this.otpShakeSerial = 0,
    this.otpFocusSerial = 0,
    this.attemptIndex = 0,
  });

  factory LoginFlowState.resolving(String flowId) =>
      LoginFlowState(step: LoginStep.resolving, flowId: flowId);

  final LoginStep step;
  final String flowId;
  final LoginOperation operation;
  final LoginConsentState consentState;
  final OtpChallengeState otpChallengeState;
  final OtpDeliveryState otpDeliveryState;
  final OtpReadinessState otpReadinessState;
  final LoginOtpPurpose otpPurpose;
  final LoginEntryMode entryMode;
  final String phone;
  final String maskedPhone;
  final String code;
  final String challengeId;
  final String deliveryRequestId;
  final String idempotencyKey;
  final String provider;
  final String bindingTicket;
  final DateTime? resendDeadline;
  final DateTime? bindingDeadline;
  final DateTime? pendingOtpExpiresAt;
  final LoginFeedback? feedback;
  final bool deliveryConfirmationExhausted;
  final int otpShakeSerial;
  final int otpFocusSerial;
  final int attemptIndex;

  bool get isBusy => operation != LoginOperation.idle;

  bool get isOtpStep =>
      step == LoginStep.otp || step == LoginStep.socialPhoneOtp;

  bool get isSocialBindingStep =>
      step == LoginStep.socialPhoneEntry || step == LoginStep.socialPhoneOtp;

  bool get isRootStep =>
      step == LoginStep.resolving ||
      step == LoginStep.oneTap ||
      step == LoginStep.phoneEntry;

  bool get showsConsent =>
      step == LoginStep.oneTap || step == LoginStep.phoneEntry;

  bool get canEditPhone => !isBusy && !isOtpStep;

  bool get canEditOtp => !isBusy && isOtpStep;

  bool get hasValidPhone => _isValidMainlandPhone(phone);

  int remainingResendSeconds(DateTime now) {
    final deadline = resendDeadline;
    if (deadline == null) return 0;
    final milliseconds = deadline.difference(now).inMilliseconds;
    if (milliseconds <= 0) return 0;
    return (milliseconds / Duration.millisecondsPerSecond).ceil();
  }

  LoginFlowState copyWith({
    LoginStep? step,
    LoginOperation? operation,
    LoginConsentState? consentState,
    OtpChallengeState? otpChallengeState,
    OtpDeliveryState? otpDeliveryState,
    OtpReadinessState? otpReadinessState,
    LoginOtpPurpose? otpPurpose,
    LoginEntryMode? entryMode,
    String? phone,
    String? maskedPhone,
    String? code,
    String? challengeId,
    String? deliveryRequestId,
    String? idempotencyKey,
    String? provider,
    String? bindingTicket,
    Object? resendDeadline = _loginUnset,
    Object? bindingDeadline = _loginUnset,
    Object? pendingOtpExpiresAt = _loginUnset,
    Object? feedback = _loginUnset,
    bool? deliveryConfirmationExhausted,
    int? otpShakeSerial,
    int? otpFocusSerial,
    int? attemptIndex,
  }) {
    return LoginFlowState(
      step: step ?? this.step,
      flowId: flowId,
      operation: operation ?? this.operation,
      consentState: consentState ?? this.consentState,
      otpChallengeState: otpChallengeState ?? this.otpChallengeState,
      otpDeliveryState: otpDeliveryState ?? this.otpDeliveryState,
      otpReadinessState: otpReadinessState ?? this.otpReadinessState,
      otpPurpose: otpPurpose ?? this.otpPurpose,
      entryMode: entryMode ?? this.entryMode,
      phone: phone ?? this.phone,
      maskedPhone: maskedPhone ?? this.maskedPhone,
      code: code ?? this.code,
      challengeId: challengeId ?? this.challengeId,
      deliveryRequestId: deliveryRequestId ?? this.deliveryRequestId,
      idempotencyKey: idempotencyKey ?? this.idempotencyKey,
      provider: provider ?? this.provider,
      bindingTicket: bindingTicket ?? this.bindingTicket,
      resendDeadline: identical(resendDeadline, _loginUnset)
          ? this.resendDeadline
          : resendDeadline as DateTime?,
      bindingDeadline: identical(bindingDeadline, _loginUnset)
          ? this.bindingDeadline
          : bindingDeadline as DateTime?,
      pendingOtpExpiresAt: identical(pendingOtpExpiresAt, _loginUnset)
          ? this.pendingOtpExpiresAt
          : pendingOtpExpiresAt as DateTime?,
      feedback: identical(feedback, _loginUnset)
          ? this.feedback
          : feedback as LoginFeedback?,
      deliveryConfirmationExhausted:
          deliveryConfirmationExhausted ?? this.deliveryConfirmationExhausted,
      otpShakeSerial: otpShakeSerial ?? this.otpShakeSerial,
      otpFocusSerial: otpFocusSerial ?? this.otpFocusSerial,
      attemptIndex: attemptIndex ?? this.attemptIndex,
    );
  }
}

class LoginFlowController extends ChangeNotifier {
  LoginFlowController({required String flowId})
    : _state = LoginFlowState.resolving(flowId);

  LoginFlowState _state;
  bool _terminalClaimed = false;

  LoginFlowState get state => _state;
  bool get terminalClaimed => _terminalClaimed;

  void replace(LoginFlowState next) {
    if (_terminalClaimed || identical(next, _state)) return;
    _state = next;
    notifyListeners();
  }

  void refresh() {
    if (!_terminalClaimed) notifyListeners();
  }

  bool tryClaimTerminal() {
    if (_terminalClaimed) return false;
    _terminalClaimed = true;
    return true;
  }
}

LoginFeedback accountSuspensionLoginFeedback({required String locale}) {
  final code = UserErrorCode.accountSuspended;
  return LoginFeedback(
    message: code.messageForLocale(locale),
    copyKey: 'loginAccountSuspended',
    surface: LoginFeedbackSurface.page,
    recoveryAction: 'openSupport',
    sourceCode: code.code,
    failureKind: RuntimeFailureKind.auth.name,
  );
}

LoginFeedback accountSuspensionSupportUnavailableFeedback() {
  return LoginFeedback(
    message: FoundationText.loginAccountSuspensionSupportUnavailable,
    copyKey: 'loginAccountSuspensionSupportUnavailable',
    surface: LoginFeedbackSurface.page,
    recoveryAction: 'retrySupport',
    sourceCode: UserErrorCode.accountSuspended.code,
    failureKind: RuntimeFailureKind.auth.name,
  );
}

LoginFeedback loginFeedbackForError(
  Object error, {
  required LoginFailureOrigin origin,
  required String locale,
  int retryAfterSeconds = 0,
}) {
  final cloudError = error is CloudException
      ? error
      : CloudErrorMapper.fromException(error);
  final rawCode = cloudError.code;
  final code = rawCode == null ? null : UserErrorCode.fromCode(rawCode);
  final failureKind = cloudError.runtimeFailure.kind.name;
  final recoverySeconds = cloudError.runtimeFailure.recovery.afterSeconds;
  final retrySeconds = retryAfterSeconds > 0
      ? retryAfterSeconds
      : recoverySeconds > 0
      ? recoverySeconds
      : 0;

  LoginFeedback feedback({
    required String message,
    required String copyKey,
    required LoginFeedbackSurface surface,
    required String recoveryAction,
    bool clearOtp = false,
    bool shakeOtp = false,
    bool preserveOtp = false,
    int? afterSeconds,
  }) {
    return LoginFeedback(
      message: message,
      copyKey: copyKey,
      surface: surface,
      recoveryAction: recoveryAction,
      cloudError: cloudError,
      sourceCode: rawCode,
      failureKind: failureKind,
      requestId: cloudError.requestId,
      traceId: cloudError.traceId,
      retryAfterSeconds: afterSeconds ?? retrySeconds,
      clearOtp: clearOtp,
      shakeOtp: shakeOtp,
      preserveOtp: preserveOtp,
    );
  }

  return switch (code) {
    UserErrorCode.socialProviderCancelled => feedback(
      message: '',
      copyKey: 'socialAuthorizationCancelled',
      surface: LoginFeedbackSurface.silent,
      recoveryAction: 'return',
    ),
    UserErrorCode.otpMismatch => feedback(
      message: FoundationText.loginOtpMismatch,
      copyKey: 'loginOtpMismatch',
      surface: LoginFeedbackSurface.otp,
      recoveryAction: 'reenterOtp',
      clearOtp: true,
      shakeOtp: true,
    ),
    UserErrorCode.otpExpired => feedback(
      message: FoundationText.loginOtpExpired,
      copyKey: 'loginOtpExpired',
      surface: LoginFeedbackSurface.otp,
      recoveryAction: 'resendOtp',
      clearOtp: true,
      afterSeconds: 0,
    ),
    UserErrorCode.challengeConsumed => feedback(
      message: FoundationText.loginOtpConsumed,
      copyKey: 'loginOtpConsumed',
      surface: LoginFeedbackSurface.otp,
      recoveryAction: 'resendOtp',
      clearOtp: true,
      afterSeconds: 0,
    ),
    UserErrorCode.otpAttemptsExceeded => feedback(
      message: FoundationText.loginOtpAttemptsExceeded,
      copyKey: 'loginOtpAttemptsExceeded',
      surface: LoginFeedbackSurface.otp,
      recoveryAction: 'resendOtp',
      clearOtp: true,
      afterSeconds: 0,
    ),
    UserErrorCode.otpRateLimited => feedback(
      message: FoundationText.loginOtpRateLimited,
      copyKey: 'loginOtpRateLimited',
      surface: LoginFeedbackSurface.otp,
      recoveryAction: 'waitThenResendOtp',
      clearOtp: true,
      afterSeconds: retrySeconds > 0 ? retrySeconds : 60,
    ),
    UserErrorCode.otpProviderFailed => feedback(
      message: FoundationText.loginOtpSendFailed,
      copyKey: 'loginOtpSendFailed',
      surface: LoginFeedbackSurface.phone,
      recoveryAction: 'resendOtp',
      afterSeconds: 0,
    ),
    UserErrorCode.credentialConflict => feedback(
      message: FoundationText.loginPhoneCredentialConflict,
      copyKey: 'loginPhoneCredentialConflict',
      surface: LoginFeedbackSurface.phone,
      recoveryAction: 'changePhone',
      clearOtp: true,
    ),
    UserErrorCode.wechatAuthFailed ||
    UserErrorCode.alipayAuthFailed ||
    UserErrorCode.qqAuthFailed ||
    UserErrorCode.socialProviderUnavailable => feedback(
      message: FoundationText.loginSocialAuthorizationFailed,
      copyKey: 'loginSocialAuthorizationFailed',
      surface: LoginFeedbackSurface.social,
      recoveryAction: 'retryAuthorization',
    ),
    UserErrorCode.consentRequired => feedback(
      message: FoundationText.loginAgreementRequired,
      copyKey: 'loginAgreementRequired',
      surface: LoginFeedbackSurface.page,
      recoveryAction: 'showConsentSheet',
    ),
    UserErrorCode.accountSuspended => feedback(
      // Account restriction copy is always local/generated. A response body
      // must never surface moderation reason, evidence, case id, or raw detail.
      message: UserErrorCode.accountSuspended.messageForLocale(locale),
      copyKey: 'loginAccountSuspended',
      surface: LoginFeedbackSurface.page,
      recoveryAction: 'openSupport',
    ),
    UserErrorCode.accountDeleted => feedback(
      message: resolveLoginErrorMessage(
        cloudError,
        code,
        sending: false,
        locale: locale,
      ),
      copyKey: 'loginAccountDeleted',
      surface: LoginFeedbackSurface.page,
      recoveryAction: 'changeMethod',
    ),
    _
        when origin == LoginFailureOrigin.otpSend &&
            cloudError.runtimeFailure.kind == RuntimeFailureKind.network =>
      feedback(
        message: FoundationText.loginNetworkUnavailable,
        copyKey: 'loginNetworkUnavailable',
        surface: LoginFeedbackSurface.phone,
        recoveryAction: 'resendOtp',
        afterSeconds: 0,
      ),
    _
        when origin == LoginFailureOrigin.otpSend &&
            cloudError.runtimeFailure.kind == RuntimeFailureKind.timeout =>
      feedback(
        message: FoundationText.loginRequestTimeout,
        copyKey: 'loginRequestTimeout',
        surface: LoginFeedbackSurface.phone,
        recoveryAction: 'resendOtp',
        afterSeconds: 0,
      ),
    _
        when origin == LoginFailureOrigin.otpSend &&
            cloudError.runtimeFailure.kind == RuntimeFailureKind.unavailable =>
      feedback(
        message: FoundationText.loginOtpServiceUnavailable,
        copyKey: 'loginOtpServiceUnavailable',
        surface: LoginFeedbackSurface.phone,
        recoveryAction: 'resendOtp',
        afterSeconds: 0,
      ),
    _
        when (origin == LoginFailureOrigin.otpVerify ||
                origin == LoginFailureOrigin.phoneBinding) &&
            cloudError.runtimeFailure.kind == RuntimeFailureKind.timeout =>
      feedback(
        message: FoundationText.loginOtpVerifyTimeout,
        copyKey: 'loginOtpVerifyTimeout',
        surface: LoginFeedbackSurface.otp,
        recoveryAction: 'retryVerifyOtp',
        preserveOtp: true,
      ),
    _
        when origin == LoginFailureOrigin.otpVerify ||
            origin == LoginFailureOrigin.phoneBinding =>
      feedback(
        message: FoundationText.loginOtpVerifyUnavailable,
        copyKey: 'loginOtpVerifyUnavailable',
        surface: LoginFeedbackSurface.otp,
        recoveryAction: 'retryVerifyOtp',
        preserveOtp: true,
      ),
    _ when origin == LoginFailureOrigin.otpSend => feedback(
      message: FoundationText.loginOtpServiceUnavailable,
      copyKey: 'loginOtpServiceUnavailable',
      surface: LoginFeedbackSurface.phone,
      recoveryAction: 'resendOtp',
    ),
    _ when origin == LoginFailureOrigin.social => feedback(
      message: FoundationText.loginSocialAuthorizationFailed,
      copyKey: 'loginSocialAuthorizationFailed',
      surface: LoginFeedbackSurface.social,
      recoveryAction: 'retryAuthorization',
    ),
    _ => feedback(
      message: resolveLoginErrorMessage(
        cloudError,
        code,
        sending: false,
        locale: locale,
      ),
      copyKey: 'loginUnavailable',
      surface: LoginFeedbackSurface.page,
      recoveryAction: 'changeMethod',
    ),
  };
}

String resolveLoginErrorMessage(
  CloudException? error,
  UserErrorCode? code, {
  required bool sending,
  String locale = 'zh',
  String? fallbackMessage,
}) {
  final cloudMessage = error?.userMessage?.trim() ?? '';
  if (cloudMessage.isNotEmpty) return cloudMessage;
  final baseline = code?.messageForLocale(locale).trim() ?? '';
  if (baseline.isNotEmpty) return baseline;
  final fallback = fallbackMessage?.trim() ?? '';
  if (fallback.isNotEmpty) return fallback;
  final kind = error?.runtimeFailure.kind;
  if (!sending &&
      (kind == RuntimeFailureKind.network ||
          kind == RuntimeFailureKind.timeout ||
          kind == RuntimeFailureKind.unavailable)) {
    return FoundationText.loginOtpVerifyUnavailable;
  }
  return sending
      ? FoundationText.loginOtpSendFailed
      : FoundationText.loginServiceUnavailable;
}

String _digitsOnly(String value) => value.replaceAll(RegExp(r'\D'), '');

bool _isValidMainlandPhone(String value) => isValidMainlandPhoneNumber(value);

String _validFullPhoneOrEmpty(String value) =>
    mainlandPhoneLocalDigitsOrEmpty(value);

String _maskPhone(String value) {
  final digits = _digitsOnly(value);
  if (digits.length != 11) return value;
  return '${digits.substring(0, 3)}****${digits.substring(7)}';
}
