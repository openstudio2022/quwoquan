part of 'login_page.dart';

Map<String, dynamic> buildLoginTelemetryPayload({
  required String environment,
  required String platform,
  required String action,
  String provider = '',
  Map<String, dynamic> raw = const <String, dynamic>{},
}) {
  final normalizedProvider = _loginTelemetryProvider(
    action: action,
    provider: provider,
    state: raw['state']?.toString() ?? '',
  );
  final rawErrorCode = raw['code']?.toString().trim() ?? '';
  final errorCode = rawErrorCode.isEmpty ? null : rawErrorCode;
  final rawDuration = raw['durationMs'];
  final durationMs = rawDuration is num && rawDuration.isFinite
      ? rawDuration.round().clamp(0, 600000)
      : null;
  String? safeEnumField(String key) {
    final value = raw[key]?.toString().trim() ?? '';
    if (value.isEmpty || value.length > 64) return null;
    return RegExp(r'^[a-zA-Z0-9_]+$').hasMatch(value) ? value : null;
  }

  final entryMode = safeEnumField('entryMode');
  final primaryAction = safeEnumField('primaryAction');
  final transitionFrom = safeEnumField('transitionFrom');
  final transitionTo = safeEnumField('transitionTo');
  final capabilityReason = safeEnumField('capabilityReason');
  return <String, dynamic>{
    'environment': environment,
    'platform': platform,
    'provider': normalizedProvider,
    'stage': action,
    'result': _loginTelemetryResult(action),
    'errorCode': ?errorCode,
    'durationMs': ?durationMs,
    'entryMode': ?entryMode,
    'primaryAction': ?primaryAction,
    'transitionFrom': ?transitionFrom,
    'transitionTo': ?transitionTo,
    'capabilityReason': ?capabilityReason,
  };
}

String _loginTelemetryProvider({
  required String action,
  required String provider,
  required String state,
}) {
  final normalized = provider.trim().toLowerCase().replaceAll('-', '_');
  if (const <String>{
    'phone',
    'wechat',
    'qq',
    'alipay',
    'one_tap',
    'refresh_token',
  }.contains(normalized)) {
    return normalized;
  }
  if (action.contains('otp') || action.contains('phone')) {
    return 'phone';
  }
  if (state == LoginEntryKind.carrierPhone.name) {
    return 'one_tap';
  }
  if (state == LoginEntryKind.returningAccount.name) {
    return 'refresh_token';
  }
  return 'none';
}

String _loginTelemetryResult(String action) {
  if (action.contains('cancelled') || action.contains('dismissed')) {
    return 'cancelled';
  }
  if (action.contains('failed') || action.contains('unavailable')) {
    return 'failure';
  }
  if (action.contains('success') || action.contains('succeeded')) {
    return 'success';
  }
  if (action.contains('clicked') ||
      action.contains('entered') ||
      action.contains('requested')) {
    return 'attempt';
  }
  if (action.contains('resolved')) {
    return 'resolved';
  }
  return 'observed';
}

enum LoginSurfaceMode { page, inline }

enum LoginEntryKind {
  resolving,
  returningAccount,
  carrierPhone,
  phoneOtp,
  unavailable,
  submitting,
  error,
}

enum LoginPrimaryAction {
  none,
  continueSession,
  carrierOneTap,
  requestOtp,
  verifyOtp,
  phoneReauth,
  socialReauth,
}

enum LoginPhoneOtpPhase {
  idle,
  editing,
  invalid,
  valid,
  sendingCode,
  codeSent,
  codeEditing,
  codeComplete,
  loggingIn,
  success,
  codeError,
  codeExpired,
  rateLimited,
  sendFailed,
  loginLocked,
  accountSuspended,
  accountDeleted,
}

/// 登录提示语气分级：红色（destructive）仅保留真正阻断态（账号被锁定/封禁/注销），
/// 其余可恢复异常（验证码错误/过期、发送失败、降级提示）用中性，频繁限流用琥珀，
/// 避免用非阻断红字吓阻用户、误导其"无法继续使用"。
enum LoginMessageTone { neutral, warning, blocking }

enum LoginErrorSurface {
  phoneField,
  otpField,
  agreement,
  socialMethod,
  topLevel,
  fallbackNotice,
  accountBlocked,
  silent,
}

enum LoginFailureOrigin { otpSend, otpLogin, oneTap, returningSession, social }

LoginMessageTone loginMessageToneForPhase(LoginPhoneOtpPhase phase) {
  return switch (phase) {
    LoginPhoneOtpPhase.loginLocked ||
    LoginPhoneOtpPhase.accountSuspended ||
    LoginPhoneOtpPhase.accountDeleted => LoginMessageTone.blocking,
    LoginPhoneOtpPhase.rateLimited => LoginMessageTone.warning,
    _ => LoginMessageTone.neutral,
  };
}

Color loginMessageToneColor(BuildContext context, LoginMessageTone tone) {
  return switch (tone) {
    LoginMessageTone.blocking => AppColors.iosDestructive(context),
    LoginMessageTone.warning => AppColors.warning,
    LoginMessageTone.neutral => AppColors.iosSecondaryLabel(context),
  };
}

class LoginPhoneOtpState {
  const LoginPhoneOtpState({
    required this.phase,
    this.phone = '',
    this.maskedPhone = '',
    this.code = '',
    this.message = '',
    this.expiresInSeconds = 0,
    this.retryAfterSeconds = 0,
    this.resendSeconds = 0,
    this.otpWasDelivered = false,
  });

  const LoginPhoneOtpState.idle() : this(phase: LoginPhoneOtpPhase.idle);

  final LoginPhoneOtpPhase phase;
  final String phone;
  final String maskedPhone;
  final String code;
  final String message;
  final int expiresInSeconds;
  final int retryAfterSeconds;
  final int resendSeconds;
  final bool otpWasDelivered;

  bool get isBusy =>
      phase == LoginPhoneOtpPhase.sendingCode ||
      phase == LoginPhoneOtpPhase.loggingIn;

  bool get isSuccess => phase == LoginPhoneOtpPhase.success;

  bool get isPhoneEditable => !isBusy && !isSuccess;

  bool get isCodeDisabled =>
      isBusy || isSuccess || phase == LoginPhoneOtpPhase.codeExpired;

  /// 此手机号当前路径走不通（账号被限制/注销，或登录被锁定）：
  /// 不允许在原号上无效重试提交，但必须给"换个手机号 / 换其他方式"出口。
  bool get isBlocked =>
      phase == LoginPhoneOtpPhase.loginLocked ||
      phase == LoginPhoneOtpPhase.accountSuspended ||
      phase == LoginPhoneOtpPhase.accountDeleted;

  bool get canSendCode =>
      _isValidMainlandPhone(phone) &&
      !isBusy &&
      !isSuccess &&
      !isBlocked &&
      resendSeconds <= 0;

  bool get canLogin =>
      _isValidMainlandPhone(phone) &&
      code.length == 6 &&
      !isBusy &&
      !isSuccess &&
      !isBlocked &&
      phase != LoginPhoneOtpPhase.codeExpired;

  String get primaryLabel {
    if (phase == LoginPhoneOtpPhase.sendingCode) {
      return UITextConstants.loginSendOtpSubmitting;
    }
    if (phase == LoginPhoneOtpPhase.loggingIn) {
      return UITextConstants.loginSubmitting;
    }
    if (phase == LoginPhoneOtpPhase.success) {
      return UITextConstants.loginSuccess;
    }
    // 账号此路不通：主按钮收敛为"换个手机号登录"出口，不诱导无效重试。
    if (isBlocked) {
      return UITextConstants.loginSwitchPhone;
    }
    // 验证码已过期且已清码：主按钮语义=重新获取验证码（文案与行为一致）。
    if (phase == LoginPhoneOtpPhase.codeExpired) {
      return UITextConstants.loginOtpResend;
    }
    if (_showsCode) {
      return UITextConstants.loginPhoneSubmit;
    }
    return UITextConstants.loginSendOtp;
  }

  bool get _showsCode =>
      otpWasDelivered && phase != LoginPhoneOtpPhase.codeExpired && !isBlocked;

  LoginPhoneOtpState copyWith({
    LoginPhoneOtpPhase? phase,
    String? phone,
    String? maskedPhone,
    String? code,
    String? message,
    int? expiresInSeconds,
    int? retryAfterSeconds,
    int? resendSeconds,
    bool? otpWasDelivered,
  }) {
    return LoginPhoneOtpState(
      phase: phase ?? this.phase,
      phone: phone ?? this.phone,
      maskedPhone: maskedPhone ?? this.maskedPhone,
      code: code ?? this.code,
      message: message ?? this.message,
      expiresInSeconds: expiresInSeconds ?? this.expiresInSeconds,
      retryAfterSeconds: retryAfterSeconds ?? this.retryAfterSeconds,
      resendSeconds: resendSeconds ?? this.resendSeconds,
      otpWasDelivered: otpWasDelivered ?? this.otpWasDelivered,
    );
  }
}

class LoginAccountHint {
  const LoginAccountHint({
    required this.displayName,
    required this.maskedPhone,
    this.avatarUrl = '',
    this.identityOrigin = '',
    this.nicknameCustomized = false,
  });

  factory LoginAccountHint.fromMap(Map<String, dynamic>? map) {
    final data = map ?? const <String, dynamic>{};
    return LoginAccountHint(
      displayName: data['displayName']?.toString().trim() ?? '',
      maskedPhone: data['maskedPhone']?.toString().trim() ?? '',
      avatarUrl: data['avatarUrl']?.toString().trim() ?? '',
      identityOrigin: data['identityOrigin']?.toString().trim() ?? '',
      nicknameCustomized: data['nicknameCustomized'] == true,
    );
  }

  final String displayName;
  final String maskedPhone;
  final String avatarUrl;
  final String identityOrigin;
  final bool nicknameCustomized;

  /// 返回账号卡片必须包含用户能够识别的具体线索。系统默认昵称、单独头像、
  /// identityOrigin 都不能独立构成返回账号入口。
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

String _digitsOnly(String value) {
  return value.replaceAll(RegExp(r'\D'), '');
}

bool _isValidMainlandPhone(String value) {
  final digits = _digitsOnly(value);
  return RegExp(r'^1[3-9]\d{9}$').hasMatch(digits);
}

/// 仅当本机记住的是合法完整手机号时返回其规整后的数字串，否则返回空串。
String _validFullPhoneOrEmpty(String value) {
  final digits = _digitsOnly(value);
  return _isValidMainlandPhone(digits) ? digits : '';
}

String _maskPhone(String value) {
  final digits = _digitsOnly(value);
  if (digits.length != 11) {
    return value;
  }
  return '${digits.substring(0, 3)}****${digits.substring(7)}';
}

/// 登录错误的 UI 行为表达：仅承载就近视觉状态（phase）、重发倒计时、是否清码。
/// 展示文案不再由本地按 code 覆盖；统一走云端 userMessage 优先（见 resolveLoginErrorMessage）。
class LoginErrorPresentation {
  const LoginErrorPresentation({
    required this.phase,
    required this.recoveryAction,
    required this.disruptionLevel,
    this.resendSeconds,
    this.clearCode = false,
  });

  final LoginPhoneOtpPhase phase;
  final RuntimeRecoveryAction recoveryAction;
  final UserDisruptionLevel disruptionLevel;
  final int? resendSeconds;
  final bool clearCode;
}

class LoginFeedback {
  const LoginFeedback({
    required this.cloudError,
    required this.presentation,
    required this.surface,
    required this.message,
    required this.origin,
    this.code,
  });

  final CloudException cloudError;
  final UserErrorCode? code;
  final LoginErrorPresentation presentation;
  final LoginErrorSurface surface;
  final String message;
  final LoginFailureOrigin origin;

  bool get isSilent =>
      surface == LoginErrorSurface.silent ||
      presentation.recoveryAction == RuntimeRecoveryAction.absorb ||
      presentation.disruptionLevel == UserDisruptionLevel.silent;

  Map<String, dynamic> get telemetry {
    final failure = cloudError.runtimeFailure;
    final errorType = failure.context.attributes
        .where((attribute) => attribute.key == 'errorType')
        .map((attribute) => attribute.value.trim())
        .firstWhere((value) => value.isNotEmpty, orElse: () => '');
    return <String, dynamic>{
      if ((cloudError.code ?? '').isNotEmpty) 'code': cloudError.code,
      'failureKind': failure.kind.name,
      if (errorType.isNotEmpty) 'errorType': errorType,
      'recovery': presentation.recoveryAction.name,
      'disruption': presentation.disruptionLevel.name,
      'surface': surface.name,
      'operation': origin.name,
      if ((cloudError.requestId ?? '').isNotEmpty)
        'requestId': cloudError.requestId,
      if ((cloudError.traceId ?? '').isNotEmpty) 'traceId': cloudError.traceId,
    };
  }
}

LoginFeedback loginFeedbackForError(
  Object error, {
  required LoginFailureOrigin origin,
  required String locale,
  required String entryId,
  required String surfaceId,
  int retryAfterSeconds = 0,
  String? fallbackMessage,
}) {
  final cloudError = error is CloudException
      ? error
      : CloudErrorMapper.fromException(error);
  final rawCode = cloudError.code;
  final code = rawCode == null ? null : UserErrorCode.fromCode(rawCode);
  final failure = cloudError.runtimeFailure;
  final presentation = loginErrorPresentationForCode(
    code,
    failure: failure,
    sending: origin == LoginFailureOrigin.otpSend,
    retryAfterSeconds: retryAfterSeconds,
    entryId: entryId,
    surfaceId: surfaceId,
  );
  return LoginFeedback(
    cloudError: cloudError,
    code: code,
    presentation: presentation,
    surface: loginErrorSurfaceForCode(code, origin: origin),
    origin: origin,
    message: resolveLoginErrorMessage(
      cloudError,
      code,
      sending: origin == LoginFailureOrigin.otpSend,
      locale: locale,
      fallbackMessage: fallbackMessage,
    ),
  );
}

LoginErrorSurface loginErrorSurfaceForCode(
  UserErrorCode? code, {
  required LoginFailureOrigin origin,
}) {
  return switch (code) {
    UserErrorCode.socialProviderCancelled => LoginErrorSurface.silent,
    UserErrorCode.wechatAuthFailed ||
    UserErrorCode.alipayAuthFailed ||
    UserErrorCode.qqAuthFailed ||
    UserErrorCode.socialProviderUnavailable ||
    UserErrorCode.appleAuthFailed ||
    UserErrorCode.passkeyAuthFailed => LoginErrorSurface.socialMethod,
    UserErrorCode.consentRequired => LoginErrorSurface.agreement,
    UserErrorCode.accountSuspended ||
    UserErrorCode.accountDeleted ||
    UserErrorCode.loginLocked => LoginErrorSurface.accountBlocked,
    UserErrorCode.otpMismatch ||
    UserErrorCode.otpAttemptsExceeded ||
    UserErrorCode.otpExpired ||
    UserErrorCode.otpRateLimited ||
    UserErrorCode.otpProviderFailed ||
    UserErrorCode.rateLimited => LoginErrorSurface.otpField,
    UserErrorCode.carrierUnavailable ||
    UserErrorCode.carrierProviderTimeout ||
    UserErrorCode.carrierTokenInvalid ||
    UserErrorCode.carrierPhoneMismatch ||
    UserErrorCode.tokenExpired => LoginErrorSurface.topLevel,
    _ => switch (origin) {
      LoginFailureOrigin.otpSend ||
      LoginFailureOrigin.otpLogin => LoginErrorSurface.otpField,
      LoginFailureOrigin.social => LoginErrorSurface.socialMethod,
      _ => LoginErrorSurface.topLevel,
    },
  };
}

LoginErrorPresentation loginErrorPresentationForCode(
  UserErrorCode? code, {
  RuntimeFailureBase? failure,
  required bool sending,
  int retryAfterSeconds = 0,
  String entryId = 'login',
  String surfaceId = 'LoginPage',
}) {
  final decision = failure == null
      ? const RuntimeRecoveryDecision(
          action: RuntimeRecoveryAction.surface,
          disruptionLevel: UserDisruptionLevel.inlineCard,
          policyId: 'login.local-fallback',
        )
      : const DefaultRuntimeRecoveryPolicy().decide(
          failure,
          EntryContext(
            kind: 'login',
            entryId: entryId,
            actorType: 'guest',
            actorId: '',
            surfaceId: surfaceId,
          ),
          BoundaryContext(
            boundary: 'login',
            stage: 'authentication',
            remainingBudget: 0,
          ),
        );
  final retrySeconds = retryAfterSeconds > 0 ? retryAfterSeconds : 60;
  return switch (code) {
    UserErrorCode.otpMismatch => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.codeError,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
    ),
    UserErrorCode.otpExpired => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.codeExpired,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: 0,
      clearCode: true,
    ),
    UserErrorCode.otpAttemptsExceeded => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.codeExpired,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: retrySeconds,
      clearCode: true,
    ),
    UserErrorCode.otpRateLimited ||
    UserErrorCode.rateLimited => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.rateLimited,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: retrySeconds,
    ),
    // 登录被锁定属于"此号当前不可登录"，不是发码倒计时：不占用重发倒计时，
    // 主按钮收敛为"换个手机号登录"，message 说明锁定原因/时长。
    UserErrorCode.loginLocked => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.loginLocked,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: 0,
    ),
    UserErrorCode.accountSuspended => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.accountSuspended,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: 0,
    ),
    UserErrorCode.accountDeleted => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.accountDeleted,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: 0,
    ),
    UserErrorCode.otpProviderFailed ||
    UserErrorCode.carrierUnavailable ||
    UserErrorCode.carrierProviderTimeout ||
    UserErrorCode.carrierTokenInvalid ||
    UserErrorCode.carrierPhoneMismatch => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.sendFailed,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: 0,
    ),
    UserErrorCode.consentRequired => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.codeError,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
    ),
    _ => LoginErrorPresentation(
      phase: sending
          ? LoginPhoneOtpPhase.sendFailed
          : LoginPhoneOtpPhase.codeError,
      recoveryAction: decision.action,
      disruptionLevel: decision.disruptionLevel,
      resendSeconds: sending ? 0 : null,
    ),
  };
}

/// userMessage 优先单路径：展示文案唯一真相源是云端随响应下发的 userMessage
/// （可经 control-plane 热配置 override）。离线/缺失时回退 codegen 错误码 baseline
/// （同源 errors.yaml），仍无则用通用兜底。不再按 code 维护第二套本地文案。
String resolveLoginErrorMessage(
  CloudException? error,
  UserErrorCode? code, {
  required bool sending,
  String locale = 'zh',
  String? fallbackMessage,
}) {
  final cloudMessage = error?.userMessage?.trim() ?? '';
  if (cloudMessage.isNotEmpty) {
    return cloudMessage;
  }
  final baseline = code?.messageForLocale(locale).trim() ?? '';
  if (baseline.isNotEmpty) {
    return baseline;
  }
  final fallback = fallbackMessage?.trim() ?? '';
  if (fallback.isNotEmpty) {
    return fallback;
  }
  return sending
      ? UITextConstants.loginOtpSendFailed
      : UITextConstants.loginFailed;
}

class LoginEntryPresentation {
  const LoginEntryPresentation({
    required this.kind,
    this.accountHint,
    this.carrierHint,
    this.phoneOtpState,
    this.feedback,
    this.message = '',
    this.primaryAction = LoginPrimaryAction.none,
    this.primaryProvider = '',
    this.quickLoginPhone = '',
  });

  const LoginEntryPresentation.resolving()
    : this(kind: LoginEntryKind.resolving);

  final LoginEntryKind kind;
  final LoginAccountHint? accountHint;
  final CarrierPhoneHint? carrierHint;
  final LoginPhoneOtpState? phoneOtpState;
  final LoginFeedback? feedback;
  final String message;

  final LoginPrimaryAction primaryAction;
  final String primaryProvider;

  /// returning 态本机记住的完整手机号（仅手机号登录方式持有）。
  ///
  /// 过期 returning 用户点「短信验证码登录」时据此只预填手机号；
  /// 为空（无完整号 / 三方登录）则进入空号手动输入态。发码始终需要显式点击。
  final String quickLoginPhone;

  LoginPrimaryAction get resolvedPrimaryAction {
    if (primaryAction != LoginPrimaryAction.none) return primaryAction;
    if (kind != LoginEntryKind.phoneOtp) return LoginPrimaryAction.none;
    final state = phoneOtpState ?? const LoginPhoneOtpState.idle();
    return state._showsCode && state.phase != LoginPhoneOtpPhase.codeExpired
        ? LoginPrimaryAction.verifyOtp
        : LoginPrimaryAction.requestOtp;
  }

  bool get hasExecutableRecovery => switch (resolvedPrimaryAction) {
    LoginPrimaryAction.continueSession ||
    LoginPrimaryAction.carrierOneTap ||
    LoginPrimaryAction.phoneReauth ||
    LoginPrimaryAction.socialReauth => true,
    _ => false,
  };

  bool get canSubmit => switch (resolvedPrimaryAction) {
    LoginPrimaryAction.continueSession ||
    LoginPrimaryAction.carrierOneTap ||
    LoginPrimaryAction.phoneReauth ||
    LoginPrimaryAction.socialReauth => true,
    LoginPrimaryAction.requestOtp =>
      phoneOtpState?.canSendCode == true || phoneOtpState?.isBlocked == true,
    LoginPrimaryAction.verifyOtp => phoneOtpState?.canLogin == true,
    LoginPrimaryAction.none => false,
  };

  String get primaryLabel {
    if (kind == LoginEntryKind.submitting) {
      return UITextConstants.loginSubmitting;
    }
    return switch (resolvedPrimaryAction) {
      LoginPrimaryAction.continueSession => UITextConstants.loginContinue,
      LoginPrimaryAction.carrierOneTap => UITextConstants.loginOneTapPrimary,
      LoginPrimaryAction.phoneReauth =>
        UITextConstants.loginReturningSmsPrimary,
      LoginPrimaryAction.socialReauth => switch (primaryProvider) {
        'wechat' => UITextConstants.loginUseWechat,
        'qq' => UITextConstants.loginUseQq,
        'alipay' => UITextConstants.loginUseAlipay,
        _ => UITextConstants.loginOtherMethodFallback,
      },
      LoginPrimaryAction.requestOtp || LoginPrimaryAction.verifyOtp =>
        phoneOtpState?.primaryLabel ?? UITextConstants.loginSendOtp,
      LoginPrimaryAction.none => UITextConstants.loginOtherMethodFallback,
    };
  }
}
