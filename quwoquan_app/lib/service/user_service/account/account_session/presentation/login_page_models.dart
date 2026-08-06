part of 'login_page.dart';

const Object _loginUnset = Object();

Map<String, dynamic> buildLoginTelemetryPayload({
  required String environment,
  required String platform,
  required String action,
  String provider = '',
  Map<String, dynamic> raw = const <String, dynamic>{},
}) {
  String? safeString(String key, {int maxLength = 128}) {
    final value = raw[key]?.toString().trim() ?? '';
    if (value.isEmpty || value.length > maxLength) return null;
    return value;
  }

  int? safeInt(String key) {
    final value = raw[key];
    if (value is! num || !value.isFinite) return null;
    return value.round().clamp(0, 600000);
  }

  final normalizedProvider = provider.trim().toLowerCase().replaceAll('-', '_');
  return <String, dynamic>{
    'environment': environment,
    'platform': platform,
    'action': action,
    if (normalizedProvider.isNotEmpty) 'provider': normalizedProvider,
    'flowId': ?safeString('flowId'),
    'entryMode': ?safeString('entryMode'),
    'step': ?safeString('step'),
    'fromStep': ?safeString('fromStep'),
    'toStep': ?safeString('toStep'),
    'otpPurpose': ?safeString('otpPurpose'),
    'consentState': ?safeString('consentState'),
    'result': ?safeString('result'),
    'sourceCode': ?safeString('sourceCode'),
    'failureKind': ?safeString('failureKind'),
    'recoveryAction': ?safeString('recoveryAction'),
    'copyKey': ?safeString('copyKey'),
    'feedbackSurface': ?safeString('feedbackSurface'),
    'requestId': ?safeString('requestId'),
    'traceId': ?safeString('traceId'),
    'countdownBucket': ?safeString('countdownBucket'),
    'dismissPolicy': ?safeString('dismissPolicy'),
    'durationMs': ?safeInt('durationMs'),
    'attemptIndex': ?safeInt('attemptIndex'),
    if (raw['motionReduced'] is bool)
      'motionReduced': raw['motionReduced'] as bool,
  };
}

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
      sourceCode == UserErrorCode.accountDeleted.code ||
      sourceCode == UserErrorCode.loginLocked.code;

  Map<String, dynamic> get telemetry => <String, dynamic>{
    if ((sourceCode ?? '').isNotEmpty) 'sourceCode': sourceCode,
    if ((failureKind ?? '').isNotEmpty) 'failureKind': failureKind,
    if (recoveryAction.isNotEmpty) 'recoveryAction': recoveryAction,
    'copyKey': copyKey,
    'feedbackSurface': surface.name,
    if ((requestId ?? '').isNotEmpty) 'requestId': requestId,
    if ((traceId ?? '').isNotEmpty) 'traceId': traceId,
  };
}

class LoginFlowState {
  const LoginFlowState({
    required this.step,
    required this.flowId,
    this.operation = LoginOperation.idle,
    this.consentState = LoginConsentState.unchecked,
    this.otpChallengeState = OtpChallengeState.none,
    this.otpPurpose = LoginOtpPurpose.login,
    this.entryMode = LoginEntryMode.resolving,
    this.phone = '',
    this.maskedPhone = '',
    this.code = '',
    this.challengeId = '',
    this.provider = '',
    this.bindingTicket = '',
    this.resendDeadline,
    this.bindingDeadline,
    this.feedback,
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
  final LoginOtpPurpose otpPurpose;
  final LoginEntryMode entryMode;
  final String phone;
  final String maskedPhone;
  final String code;
  final String challengeId;
  final String provider;
  final String bindingTicket;
  final DateTime? resendDeadline;
  final DateTime? bindingDeadline;
  final LoginFeedback? feedback;
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
    LoginOtpPurpose? otpPurpose,
    LoginEntryMode? entryMode,
    String? phone,
    String? maskedPhone,
    String? code,
    String? challengeId,
    String? provider,
    String? bindingTicket,
    Object? resendDeadline = _loginUnset,
    Object? bindingDeadline = _loginUnset,
    Object? feedback = _loginUnset,
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
      otpPurpose: otpPurpose ?? this.otpPurpose,
      entryMode: entryMode ?? this.entryMode,
      phone: phone ?? this.phone,
      maskedPhone: maskedPhone ?? this.maskedPhone,
      code: code ?? this.code,
      challengeId: challengeId ?? this.challengeId,
      provider: provider ?? this.provider,
      bindingTicket: bindingTicket ?? this.bindingTicket,
      resendDeadline: identical(resendDeadline, _loginUnset)
          ? this.resendDeadline
          : resendDeadline as DateTime?,
      bindingDeadline: identical(bindingDeadline, _loginUnset)
          ? this.bindingDeadline
          : bindingDeadline as DateTime?,
      feedback: identical(feedback, _loginUnset)
          ? this.feedback
          : feedback as LoginFeedback?,
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
    UserErrorCode.otpExpired || UserErrorCode.challengeConsumed => feedback(
      message: FoundationText.loginOtpExpired,
      copyKey: 'loginOtpExpired',
      surface: LoginFeedbackSurface.otp,
      recoveryAction: 'resendOtp',
      clearOtp: true,
      afterSeconds: 0,
    ),
    UserErrorCode.otpAttemptsExceeded ||
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
    UserErrorCode.loginLocked => feedback(
      message: resolveLoginErrorMessage(
        cloudError,
        code,
        sending: false,
        locale: locale,
      ),
      copyKey: 'loginAccountTemporarilyLocked',
      surface: LoginFeedbackSurface.page,
      recoveryAction: 'waitThenChangeMethod',
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
