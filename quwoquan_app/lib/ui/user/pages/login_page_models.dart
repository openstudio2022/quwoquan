part of 'login_page.dart';

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
    this.debugCode = '',
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
  final String debugCode;

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
      return UITextConstants.loginSendOtp;
    }
    if (_showsCode) {
      return UITextConstants.loginPhoneSubmit;
    }
    return UITextConstants.loginSendOtp;
  }

  bool get _showsCode =>
      phase == LoginPhoneOtpPhase.codeSent ||
      phase == LoginPhoneOtpPhase.codeEditing ||
      phase == LoginPhoneOtpPhase.codeComplete ||
      phase == LoginPhoneOtpPhase.loggingIn ||
      phase == LoginPhoneOtpPhase.success ||
      phase == LoginPhoneOtpPhase.codeError ||
      phase == LoginPhoneOtpPhase.rateLimited ||
      phase == LoginPhoneOtpPhase.loginLocked ||
      phase == LoginPhoneOtpPhase.accountSuspended ||
      phase == LoginPhoneOtpPhase.accountDeleted;

  LoginPhoneOtpState copyWith({
    LoginPhoneOtpPhase? phase,
    String? phone,
    String? maskedPhone,
    String? code,
    String? message,
    int? expiresInSeconds,
    int? retryAfterSeconds,
    int? resendSeconds,
    String? debugCode,
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
      debugCode: debugCode ?? this.debugCode,
    );
  }
}

bool shouldRevealOtpDebugCode({
  required String runtimeEnv,
  required bool mockDataSourceActive,
  required OtpSendResultData result,
}) {
  if (!result.isDebugCodeVisible) {
    return false;
  }
  if (runtimeEnv == 'alpha') {
    return mockDataSourceActive;
  }
  if (runtimeEnv == 'beta') {
    return true;
  }
  // gamma：对接真实上游，仅受控放通命中沙箱白名单（deliveryStatus == 'sandbox'）才回填验证码。
  if (runtimeEnv == 'gamma') {
    return result.deliveryStatus == 'sandbox';
  }
  return false;
}

class LoginAccountHint {
  const LoginAccountHint({
    required this.displayName,
    required this.maskedPhone,
    this.avatarUrl = '',
    this.identityOrigin = '',
  });

  factory LoginAccountHint.fromMap(Map<String, dynamic>? map) {
    final data = map ?? const <String, dynamic>{};
    return LoginAccountHint(
      displayName: data['displayName']?.toString().trim() ?? '',
      maskedPhone: data['maskedPhone']?.toString().trim() ?? '',
      avatarUrl: data['avatarUrl']?.toString().trim() ?? '',
      identityOrigin: data['identityOrigin']?.toString().trim() ?? '',
    );
  }

  final String displayName;
  final String maskedPhone;
  final String avatarUrl;
  final String identityOrigin;

  bool get hasDisplay => displayName.isNotEmpty || maskedPhone.isNotEmpty;
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
  return digits.length == 11 && digits.startsWith('1');
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
    this.resendSeconds,
    this.clearCode = false,
  });

  final LoginPhoneOtpPhase phase;
  final int? resendSeconds;
  final bool clearCode;
}

LoginErrorPresentation loginErrorPresentationForCode(
  UserErrorCode? code, {
  required bool sending,
  int retryAfterSeconds = 0,
}) {
  final retrySeconds = retryAfterSeconds > 0 ? retryAfterSeconds : 60;
  return switch (code) {
    UserErrorCode.otpMismatch => const LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.codeError,
    ),
    UserErrorCode.otpExpired => const LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.codeExpired,
      resendSeconds: 0,
      clearCode: true,
    ),
    UserErrorCode.otpRateLimited ||
    UserErrorCode.rateLimited => LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.rateLimited,
      resendSeconds: retrySeconds,
    ),
    // 登录被锁定属于"此号当前不可登录"，不是发码倒计时：不占用重发倒计时，
    // 主按钮收敛为"换个手机号登录"，message 说明锁定原因/时长。
    UserErrorCode.loginLocked => const LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.loginLocked,
      resendSeconds: 0,
    ),
    UserErrorCode.accountSuspended => const LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.accountSuspended,
      resendSeconds: 0,
    ),
    UserErrorCode.accountDeleted => const LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.accountDeleted,
      resendSeconds: 0,
    ),
    UserErrorCode.otpProviderFailed ||
    UserErrorCode.carrierUnavailable ||
    UserErrorCode.carrierProviderTimeout ||
    UserErrorCode.carrierTokenInvalid ||
    UserErrorCode.carrierPhoneMismatch => const LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.sendFailed,
      resendSeconds: 0,
    ),
    UserErrorCode.consentRequired => const LoginErrorPresentation(
      phase: LoginPhoneOtpPhase.codeError,
    ),
    _ => LoginErrorPresentation(
      phase: sending
          ? LoginPhoneOtpPhase.sendFailed
          : LoginPhoneOtpPhase.codeError,
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
}) {
  final cloudMessage = error?.userMessage?.trim() ?? '';
  if (cloudMessage.isNotEmpty) {
    return cloudMessage;
  }
  final baseline = code?.defaultMessage.trim() ?? '';
  if (baseline.isNotEmpty) {
    return baseline;
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
    this.message = '',
    this.oneTapCredentialAvailable = true,
    this.quickLoginPhone = '',
  });

  const LoginEntryPresentation.resolving()
    : this(kind: LoginEntryKind.resolving);

  final LoginEntryKind kind;
  final LoginAccountHint? accountHint;
  final CarrierPhoneHint? carrierHint;
  final LoginPhoneOtpState? phoneOtpState;
  final String message;

  /// returning 态是否有可用的快速登录凭证（有效期内 refreshToken 或运营商 token）。
  ///
  /// 为 false 时（软退出后过期 / 已彻底退出）returning 头部仍保留熟悉感，
  /// 但主按钮落短信验证码登录，避免呈现注定失败的一键登录。
  final bool oneTapCredentialAvailable;

  /// returning 态本机记住的完整手机号（仅手机号登录方式持有）。
  ///
  /// 过期 returning 用户点「用短信验证码登录」时据此自动预填手机号并自动发码，
  /// 免去重新输入；为空（无完整号 / 三方登录）则进入空号手动输入态。
  final String quickLoginPhone;

  bool get canSubmit =>
      kind == LoginEntryKind.returningAccount ||
      kind == LoginEntryKind.carrierPhone ||
      (kind == LoginEntryKind.phoneOtp &&
          (phoneOtpState?.canSendCode == true ||
              phoneOtpState?.canLogin == true ||
              phoneOtpState?.isBlocked == true));

  String get primaryLabel {
    return switch (kind) {
      LoginEntryKind.returningAccount =>
        oneTapCredentialAvailable
            ? UITextConstants.loginOneTap
            : UITextConstants.loginReturningSmsPrimary,
      LoginEntryKind.carrierPhone => UITextConstants.loginOneTapPrimary,
      LoginEntryKind.phoneOtp =>
        phoneOtpState?.primaryLabel ?? UITextConstants.loginSendOtp,
      LoginEntryKind.submitting => UITextConstants.loginSubmitting,
      _ => UITextConstants.loginOtherMethodFallback,
    };
  }
}
