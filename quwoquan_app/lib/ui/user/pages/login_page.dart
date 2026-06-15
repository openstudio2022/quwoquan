import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/one_tap_login_hint_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';
import 'package:simple_icons/simple_icons.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({
    super.key,
    this.reason,
    this.redirect,
    this.dismissFallback,
    this.allowGuestDismissPop = true,
  });

  final String? reason;
  final String? redirect;
  final String? dismissFallback;
  final bool allowGuestDismissPop;

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class WebInlineLoginSurface extends StatelessWidget {
  const WebInlineLoginSurface({
    super.key,
    required this.onDismiss,
    required this.onLoggedIn,
    this.reason,
  });

  final VoidCallback onDismiss;
  final VoidCallback onLoggedIn;
  final String? reason;

  @override
  Widget build(BuildContext context) {
    return LoginFrameHost(
      reason: reason,
      allowGuestDismissPop: false,
      onDismiss: onDismiss,
      onLoggedIn: onLoggedIn,
      surfaceMode: LoginSurfaceMode.inline,
    );
  }
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
  required AppDataSourceMode dataSourceMode,
  required OtpSendResultData result,
}) {
  if (!result.isDebugCodeVisible) {
    return false;
  }
  if (runtimeEnv == 'alpha') {
    return dataSourceMode == AppDataSourceMode.mock;
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

class _LoginPageState extends ConsumerState<LoginPage> {
  @override
  Widget build(BuildContext context) {
    return LoginFrameHost(
      reason: widget.reason,
      redirect: widget.redirect,
      dismissFallback: widget.dismissFallback,
      allowGuestDismissPop: widget.allowGuestDismissPop,
      surfaceMode: LoginSurfaceMode.page,
    );
  }
}

class LoginFrameHost extends ConsumerStatefulWidget {
  const LoginFrameHost({
    super.key,
    this.reason,
    this.redirect,
    this.dismissFallback,
    this.allowGuestDismissPop = true,
    this.onDismiss,
    this.onLoggedIn,
    this.surfaceMode = LoginSurfaceMode.page,
  });

  final String? reason;
  final String? redirect;
  final String? dismissFallback;
  final bool allowGuestDismissPop;
  final VoidCallback? onDismiss;
  final VoidCallback? onLoggedIn;
  final LoginSurfaceMode surfaceMode;

  @override
  ConsumerState<LoginFrameHost> createState() => _LoginFrameHostState();
}

class _LoginFrameHostState extends ConsumerState<LoginFrameHost> {
  static const Duration _probeTimeout = Duration(milliseconds: 1200);
  static const String _loginJourney = 'two_state_login';
  static const String _loginPageName = 'LoginPage';

  bool _agreementAccepted = false;
  LoginEntryPresentation _presentation =
      const LoginEntryPresentation.resolving();
  OneTapLoginProbe? _probe;
  late final JourneyEventTracker _journeyTracker;
  late final TextEditingController _phoneController;
  late final TextEditingController _otpController;
  Timer? _otpCountdownTimer;
  String? _autoSubmittedOtpCode;

  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    _phoneController = TextEditingController();
    _otpController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackLoginEvent('login_page_exposed');
    });
    unawaited(_resolveEntryState());
  }

  @override
  void dispose() {
    _otpCountdownTimer?.cancel();
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _resolveEntryState() async {
    final stored = await ref.read(authSessionStoreProvider).read();
    final session = ref.read(authSessionControllerProvider);
    final localHint = LoginAccountHint(
      displayName: stored.rememberedDisplayName,
      avatarUrl: stored.rememberedAvatarUrl,
      maskedPhone: stored.rememberedLoginMaskedIdentifier,
      identityOrigin: stored.identityOrigin,
    );
    if (localHint.hasDisplay) {
      // 有展示摘要 != 有可用凭证：仅当存在可用快速登录凭证才呈现一键登录，
      // 否则保留 returning 头部但主按钮落短信，避免注定失败的一键登录。
      //
      // 平台差异（能力优先，遵循 14-cross-platform）：个人设备（手机/iPad/桌面）
      // 在安全存储中长期持有凭证，按云端下发有效期判定；Web 凭证生命周期由浏览器
      // cookies/会话控制，端侧不长期持有，只看"会话是否仍持有 refreshToken"。
      final caps = ref.read(platformCapabilitiesProvider);
      final hasQuickLogin = caps.quickLoginPersistence
          ? stored.hasValidQuickLoginCredential
          : stored.refreshToken.trim().isNotEmpty;
      _setPresentation(
        LoginEntryPresentation(
          kind: LoginEntryKind.returningAccount,
          accountHint: localHint,
          oneTapCredentialAvailable: hasQuickLogin,
          quickLoginPhone: _validFullPhoneOrEmpty(
            stored.rememberedLoginIdentifier,
          ),
        ),
      );
    }

    try {
      final probe = await ref
          .read(oneTapLoginClientProvider)
          .probe()
          .timeout(_probeTimeout);
      _probe = probe;
      if (!probe.isAvailable || probe.carrierToken.trim().isEmpty) {
        if (!localHint.hasDisplay) {
          _enterPhoneOtp();
        }
        return;
      }
      final hint = await ref
          .read(authRepositoryProvider)
          .resolveOneTapLoginHint(
            vendor: probe.vendor,
            carrierToken: probe.carrierToken,
            deviceId: session.installId.isNotEmpty
                ? session.installId
                : stored.installId,
            platform: CloudRequestHeaders.platform(),
            appVersion: CloudRequestHeaders.appVersion,
          )
          .timeout(_probeTimeout);
      _applyCarrierHint(probe, hint);
    } catch (_) {
      if (!localHint.hasDisplay) {
        _enterPhoneOtp();
      }
    }
  }

  void _applyCarrierHint(OneTapLoginProbe probe, OneTapLoginHintDto hint) {
    final accountHint = LoginAccountHint.fromMap(hint.accountHint);
    final carrierHint = CarrierPhoneHint(
      vendor: probe.vendor,
      carrierToken: probe.carrierToken,
      maskedPhone: hint.maskedPhone.isNotEmpty
          ? hint.maskedPhone
          : probe.maskedPhone,
      registered: hint.registered,
      accountHint: accountHint.hasDisplay ? accountHint : null,
    );
    if (hint.registered && accountHint.hasDisplay) {
      _setPresentation(
        LoginEntryPresentation(
          kind: LoginEntryKind.returningAccount,
          accountHint: accountHint,
          carrierHint: carrierHint,
        ),
      );
      return;
    }
    _setPresentation(
      LoginEntryPresentation(
        kind: LoginEntryKind.carrierPhone,
        carrierHint: carrierHint,
      ),
    );
  }

  void _setPresentation(LoginEntryPresentation next) {
    if (!mounted) {
      return;
    }
    setState(() => _presentation = next);
    _trackLoginEvent(
      'login_state_resolved',
      payload: <String, dynamic>{'state': next.kind.name},
    );
  }

  void _enterPhoneOtp({
    LoginPhoneOtpState state = const LoginPhoneOtpState.idle(),
  }) {
    _setPresentation(
      LoginEntryPresentation(
        kind: LoginEntryKind.phoneOtp,
        phoneOtpState: state,
      ),
    );
    _trackLoginEvent('login_phone_otp_entered');
  }

  /// 过期 returning 点「用短信验证码登录」：自动预填本机记住的完整手机号，
  /// 并自动发码（等价用户已点「获取验证码」），用户只需等待验证码自动填充完成登录。
  ///
  /// - 有完整号 + 已勾协议：预填 + 自动发码，直接进入验证码态。
  /// - 有完整号 + 未勾协议：预填到可发码态并提示勾选协议，用户勾选后点一次即可。
  /// - 无完整号（三方登录 / 历史数据缺失）：回退到空号手动输入态。
  Future<void> _enterReturningSmsLogin(String quickLoginPhone) async {
    final fullPhone = _validFullPhoneOrEmpty(quickLoginPhone);
    if (fullPhone.isEmpty) {
      _enterPhoneOtp(
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.idle,
          message: UITextConstants.loginSessionExpiredHint,
        ),
      );
      return;
    }
    _phoneController.text = fullPhone;
    final prefilled = LoginPhoneOtpState(
      phase: LoginPhoneOtpPhase.valid,
      phone: fullPhone,
      maskedPhone: _maskPhone(fullPhone),
    );
    if (!_agreementAccepted) {
      // 未勾协议不可自动发码：预填到可发码态并提示勾选，避免静默拦截。
      _enterPhoneOtp(
        state: prefilled.copyWith(
          message: UITextConstants.loginSessionExpiredHint,
        ),
      );
      return;
    }
    _enterPhoneOtp(state: prefilled);
    await _sendPhoneOtp(prefilled);
  }

  LoginPhoneOtpState get _phoneOtpState =>
      _presentation.phoneOtpState ?? const LoginPhoneOtpState.idle();

  void _setPhoneOtpState(LoginPhoneOtpState state) {
    if (!mounted) {
      return;
    }
    setState(() {
      _presentation = LoginEntryPresentation(
        kind: LoginEntryKind.phoneOtp,
        phoneOtpState: state,
      );
    });
  }

  void _handlePhoneChanged(String value) {
    final phone = _digitsOnly(value);
    _autoSubmittedOtpCode = null;
    if (_phoneController.text != phone) {
      _phoneController.value = TextEditingValue(
        text: phone,
        selection: TextSelection.collapsed(offset: phone.length),
      );
    }
    _otpController.clear();
    _otpCountdownTimer?.cancel();
    final phase = phone.isEmpty
        ? LoginPhoneOtpPhase.idle
        : phone.length < 11
        ? LoginPhoneOtpPhase.editing
        : _isValidMainlandPhone(phone)
        ? LoginPhoneOtpPhase.valid
        : LoginPhoneOtpPhase.invalid;
    _setPhoneOtpState(
      LoginPhoneOtpState(
        phase: phase,
        phone: phone,
        message: phase == LoginPhoneOtpPhase.invalid
            ? UITextConstants.loginPhoneInvalid
            : '',
      ),
    );
    _trackLoginEvent('login_phone_changed');
  }

  void _handleOtpChanged(String value) {
    final code = _digitsOnly(value);
    final trimmed = code.length > 6 ? code.substring(0, 6) : code;
    if (_otpController.text != trimmed) {
      _otpController.value = TextEditingValue(
        text: trimmed,
        selection: TextSelection.collapsed(offset: trimmed.length),
      );
    }
    final current = _phoneOtpState;
    final phase = trimmed.length == 6
        ? LoginPhoneOtpPhase.codeComplete
        : trimmed.isEmpty
        ? LoginPhoneOtpPhase.codeSent
        : LoginPhoneOtpPhase.codeEditing;
    _setPhoneOtpState(
      current.copyWith(phase: phase, code: trimmed, message: ''),
    );
    _trackLoginEvent(
      'login_otp_code_changed',
      payload: <String, dynamic>{'length': trimmed.length},
    );
    _scheduleAutoSubmitCompletedOtp(trimmed);
  }

  void _scheduleAutoSubmitCompletedOtp(String code) {
    if (code.length != 6 || _autoSubmittedOtpCode == code) {
      return;
    }
    final state = _phoneOtpState.copyWith(code: code);
    if (!state.canLogin) {
      return;
    }
    if (!_agreementAccepted) {
      _setPhoneOtpState(
        state.copyWith(message: UITextConstants.loginAgreementRequired),
      );
      return;
    }
    _autoSubmittedOtpCode = code;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final current = _phoneOtpState;
      if (current.canLogin &&
          current.code == code &&
          _agreementAccepted &&
          current.phase == LoginPhoneOtpPhase.codeComplete) {
        unawaited(_submitPhoneOtpLogin(current));
      }
    });
  }

  void _startOtpCountdown(int seconds) {
    _otpCountdownTimer?.cancel();
    if (seconds <= 0) {
      return;
    }
    _otpCountdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      final current = _phoneOtpState;
      final next = current.resendSeconds - 1;
      if (next <= 0) {
        timer.cancel();
      }
      if (mounted && _presentation.kind == LoginEntryKind.phoneOtp) {
        _setPhoneOtpState(current.copyWith(resendSeconds: next < 0 ? 0 : next));
      }
    });
  }

  Future<void> _handlePhoneOtpPrimary() async {
    final state = _phoneOtpState;
    // 账号此路不通（限制/注销/锁定）：主按钮=换个手机号，重置到可输入态，
    // 不再校验协议、不做无效重试，直接给出口。
    if (state.isBlocked) {
      _resetPhoneOtpToIdle();
      return;
    }
    if (!_agreementAccepted) {
      AppToast.show(context, UITextConstants.loginAgreementRequired);
      _setPhoneOtpState(
        state.copyWith(message: UITextConstants.loginAgreementRequired),
      );
      return;
    }
    if (state.canLogin) {
      await _submitPhoneOtpLogin(state);
      return;
    }
    if (state.canSendCode) {
      await _sendPhoneOtp(state);
      return;
    }
    final message = _isValidMainlandPhone(state.phone)
        ? UITextConstants.loginOtpRequired
        : UITextConstants.loginPhoneInvalid;
    _setPhoneOtpState(state.copyWith(message: message));
  }

  /// 清空手机号与验证码并回到可输入态，作为"换个手机号"的统一出口。
  void _resetPhoneOtpToIdle() {
    _otpCountdownTimer?.cancel();
    _autoSubmittedOtpCode = null;
    _phoneController.clear();
    _otpController.clear();
    _enterPhoneOtp();
    _trackLoginEvent('login_phone_reset');
  }

  /// "重新获取"动作：仅在倒计时结束、非繁忙、非阻断态下可触发。
  /// 打通 codeSent/codeError/codeExpired/rateLimited/sendFailed 的重发出口。
  Future<void> _resendPhoneOtp() async {
    final state = _phoneOtpState;
    if (!state.canSendCode) {
      return;
    }
    if (!_agreementAccepted) {
      AppToast.show(context, UITextConstants.loginAgreementRequired);
      _setPhoneOtpState(
        state.copyWith(message: UITextConstants.loginAgreementRequired),
      );
      return;
    }
    await _sendPhoneOtp(state);
  }

  Future<void> _sendPhoneOtp(LoginPhoneOtpState state) async {
    _trackLoginEvent('login_otp_request_clicked');
    _setPhoneOtpState(state.copyWith(phase: LoginPhoneOtpPhase.sendingCode));
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      final result = await ref
          .read(authRepositoryProvider)
          .sendOtp(
            phone: state.phone,
            deviceId: session.installId.isNotEmpty
                ? session.installId
                : stored.installId,
            platform: CloudRequestHeaders.platform(),
            appVersion: CloudRequestHeaders.appVersion,
            sourceOperation: 'LoginPhoneOtp',
          );
      final revealDebugCode = shouldRevealOtpDebugCode(
        runtimeEnv: CloudRuntimeConfig.appRuntimeEnv,
        dataSourceMode: ref.read(appDataSourceModeProvider),
        result: result,
      );
      final seconds = result.retryAfterSeconds > 0
          ? result.retryAfterSeconds
          : result.expiresInSeconds > 0
          ? result.expiresInSeconds
          : 60;
      final next = state.copyWith(
        phase: LoginPhoneOtpPhase.codeSent,
        maskedPhone: result.maskedPhone.isEmpty
            ? _maskPhone(state.phone)
            : result.maskedPhone,
        code: '',
        message: '',
        expiresInSeconds: result.expiresInSeconds,
        retryAfterSeconds: result.retryAfterSeconds,
        resendSeconds: seconds,
        debugCode: revealDebugCode ? result.debugCode ?? '' : '',
      );
      _autoSubmittedOtpCode = null;
      _otpController.clear();
      _setPhoneOtpState(next);
      _startOtpCountdown(seconds);
      _trackLoginEvent('login_otp_send_succeeded');
    } catch (error) {
      final next = _phoneOtpStateForError(state, error, sending: true);
      _setPhoneOtpState(next);
      if (next.resendSeconds > 0) {
        _startOtpCountdown(next.resendSeconds);
      }
      _trackLoginEvent(
        'login_otp_send_failed',
        payload: <String, dynamic>{'message': next.message},
      );
    }
  }

  Future<void> _submitPhoneOtpLogin(LoginPhoneOtpState state) async {
    _trackLoginEvent('login_phone_login_clicked');
    _setPhoneOtpState(state.copyWith(phase: LoginPhoneOtpPhase.loggingIn));
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      final result = await ref
          .read(authRepositoryProvider)
          .login(
            credentialType: 'phone',
            credentialKey: state.phone,
            otpCode: state.code,
            displayLabel: state.maskedPhone.isEmpty
                ? _maskPhone(state.phone)
                : state.maskedPhone,
            deviceId: session.installId.isNotEmpty
                ? session.installId
                : stored.installId,
            platform: CloudRequestHeaders.platform(),
            appVersion: CloudRequestHeaders.appVersion,
            agreementVersion: AuthLegalConfig.agreementVersion,
            privacyVersion: AuthLegalConfig.privacyVersion,
          );
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginResult(
            result,
            rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
            rememberedLoginMaskedIdentifier: _maskPhone(state.phone),
            // 记住完整手机号（安全存储），过期后再登录可自动预填并自动发码。
            rememberedLoginIdentifier: state.phone,
          );
      _setPhoneOtpState(
        state.copyWith(
          phase: LoginPhoneOtpPhase.success,
          message: UITextConstants.loginRedirecting,
        ),
      );
      // 登录成功提交自动填充上下文，便于系统保存手机号/验证码以供下次自动填充。
      TextInput.finishAutofillContext();
      _trackLoginEvent('login_phone_login_succeeded');
      _completeLogin();
    } catch (error) {
      final next = _phoneOtpStateForError(state, error);
      _setPhoneOtpState(next);
      if (next.resendSeconds > 0) {
        _startOtpCountdown(next.resendSeconds);
      }
      _trackLoginEvent(
        'login_phone_login_failed',
        payload: <String, dynamic>{'message': next.message},
      );
    }
  }

  LoginPhoneOtpState _phoneOtpStateForError(
    LoginPhoneOtpState state,
    Object error, {
    bool sending = false,
  }) {
    final cloudError = error is CloudException ? error : null;
    final rawCode = cloudError?.code;
    final code = rawCode == null ? null : UserErrorCode.fromCode(rawCode);
    final retryAfterSeconds = cloudError == null
        ? 0
        : _retryAfterSecondsFromCloudException(cloudError);
    final presentation = loginErrorPresentationForCode(
      code,
      sending: sending,
      retryAfterSeconds: retryAfterSeconds,
    );
    return state.copyWith(
      phase: presentation.phase,
      code: presentation.clearCode ? '' : state.code,
      message: resolveLoginErrorMessage(cloudError, code, sending: sending),
      resendSeconds: presentation.resendSeconds ?? state.resendSeconds,
    );
  }

  int _retryAfterSecondsFromCloudException(CloudException error) {
    final afterSeconds = error.runtimeFailure?.recovery.afterSeconds ?? 0;
    return afterSeconds < 0 ? 0 : afterSeconds;
  }

  Future<void> _handlePrimaryLogin() async {
    final entryBeforeSubmit = _presentation;
    _trackLoginEvent(
      'login_primary_clicked',
      payload: <String, dynamic>{'state': entryBeforeSubmit.kind.name},
    );
    if (entryBeforeSubmit.kind == LoginEntryKind.phoneOtp) {
      await _handlePhoneOtpPrimary();
      return;
    }
    // returning 头部展示熟悉感但无可用快速登录凭证（软退出后过期/已彻底退出）：
    // 主按钮即"用短信验证码登录"，直接进验证码流程，绝不发起注定失败的一键登录。
    if (entryBeforeSubmit.kind == LoginEntryKind.returningAccount &&
        !entryBeforeSubmit.oneTapCredentialAvailable) {
      await _enterReturningSmsLogin(entryBeforeSubmit.quickLoginPhone);
      return;
    }
    if (!entryBeforeSubmit.canSubmit) {
      AppToast.show(context, UITextConstants.loginMethodComingSoonToast);
      return;
    }
    if (!_agreementAccepted) {
      AppToast.show(context, UITextConstants.loginAgreementRequired);
      return;
    }
    setState(() {
      _presentation = LoginEntryPresentation(
        kind: LoginEntryKind.submitting,
        accountHint: entryBeforeSubmit.accountHint,
        carrierHint: entryBeforeSubmit.carrierHint,
      );
    });
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      final probe = _probe;
      final carrierHint = entryBeforeSubmit.carrierHint;
      final token = carrierHint?.carrierToken ?? probe?.carrierToken ?? '';
      final vendor = carrierHint?.vendor ?? probe?.vendor ?? 'carrier';
      if (token.isEmpty) {
        if (entryBeforeSubmit.kind == LoginEntryKind.returningAccount &&
            stored.refreshToken.trim().isNotEmpty) {
          final result = await ref
              .read(authRepositoryProvider)
              .refreshToken(stored.refreshToken.trim());
          await ref
              .read(authSessionControllerProvider.notifier)
              .applyRefreshResult(result);
          _trackLoginEvent(
            'login_success',
            payload: <String, dynamic>{'state': entryBeforeSubmit.kind.name},
          );
          _completeLogin();
          return;
        }
        // 无运营商 token 且无可用 refreshToken：不抛错、不停在失败态，
        // 无红字降级到短信验证码登录，给用户立刻可用的恢复出口。
        _enterPhoneOtp(
          state: const LoginPhoneOtpState(
            phase: LoginPhoneOtpPhase.idle,
            message: UITextConstants.loginQuickLoginUnavailableHint,
          ),
        );
        return;
      }
      final result = await ref
          .read(authRepositoryProvider)
          .loginOneTap(
            vendor: vendor,
            carrierToken: token,
            deviceId: session.installId.isNotEmpty
                ? session.installId
                : stored.installId,
            platform: CloudRequestHeaders.platform(),
            appVersion: CloudRequestHeaders.appVersion,
            agreementVersion: AuthLegalConfig.agreementVersion,
            privacyVersion: AuthLegalConfig.privacyVersion,
          );
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginResult(
            result,
            rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
            rememberedLoginMaskedIdentifier: _resolvedMaskedPhone(result),
          );
      _trackLoginEvent(
        'login_success',
        payload: <String, dynamic>{'state': entryBeforeSubmit.kind.name},
      );
      _completeLogin();
    } catch (error) {
      _applyTopLevelLoginFailure(entryBeforeSubmit, error);
    }
  }

  /// 顶层登录失败（一键/历史会话/三方）统一恢复：绝不停在不可操作空面板。
  /// 规则：
  /// - 运营商系列错误 -> 降级到手机号验证码输入态，并解释原因（用户改走短信）。
  /// - 其它错误 -> 回到失败前的有效操作态（returning/carrier/phoneOtp），
  ///   附就近错误横幅 + toast，用户可重试或从底部"其他方式"换路径。
  void _applyTopLevelLoginFailure(
    LoginEntryPresentation entryBeforeSubmit,
    Object error, {
    String? fallbackMessage,
  }) {
    if (!mounted) {
      return;
    }
    // 与验证码路径同源：云端 userMessage 优先 -> UserErrorCode baseline -> 通用兜底，
    // 禁止再直接读取 runtimeErrorDisplayMessage（见 resolveLoginErrorMessage / 统一错误语义）。
    final cloudError = error is CloudException ? error : null;
    final userCode = (cloudError?.code != null)
        ? UserErrorCode.fromCode(cloudError!.code!)
        : null;
    // 非云端异常（如 refresh 缺 token 的 StateError、本地一键凭证失效）绝不呈现
    // 「登录失败，请稍后重试」这类无意义红字：统一给中性、可立刻恢复的短信指引。
    // loginFailed 仅用于日志，不作为可见主提示。
    final message = cloudError != null
        ? resolveLoginErrorMessage(cloudError, userCode, sending: false)
        : (fallbackMessage ?? UITextConstants.loginSessionExpiredHint);
    final isCarrierFailure =
        userCode == UserErrorCode.carrierUnavailable ||
        userCode == UserErrorCode.carrierProviderTimeout ||
        userCode == UserErrorCode.carrierTokenInvalid ||
        userCode == UserErrorCode.carrierPhoneMismatch;
    if (isCarrierFailure) {
      _enterPhoneOtp(
        state: LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.idle,
          message: message,
        ),
      );
      _trackLoginEvent(
        'login_failed',
        payload: <String, dynamic>{
          'state': LoginEntryKind.phoneOtp.name,
          'message': message,
        },
      );
      AppToast.show(context, message);
      return;
    }
    // returning 一键登录失败（refreshToken 过期/无效）若回到 returning，会再次呈现
    // 注定失败的一键登录形成死循环；统一降级到验证码流程。仅 carrierPhone 的非运营商
    // 异常保留原态加横幅（可重试或换其他方式）。
    final recoverKind = entryBeforeSubmit.kind == LoginEntryKind.carrierPhone
        ? LoginEntryKind.carrierPhone
        : LoginEntryKind.phoneOtp;
    if (recoverKind == LoginEntryKind.phoneOtp) {
      _enterPhoneOtp(
        state: LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.idle,
          message: message,
        ),
      );
    } else {
      setState(() {
        _presentation = LoginEntryPresentation(
          kind: recoverKind,
          accountHint: entryBeforeSubmit.accountHint,
          carrierHint: entryBeforeSubmit.carrierHint,
          message: message,
        );
      });
    }
    _trackLoginEvent(
      'login_failed',
      payload: <String, dynamic>{'state': recoverKind.name, 'message': message},
    );
    AppToast.show(context, message);
  }

  String _resolvedMaskedPhone(AuthLoginResultDto result) {
    final fromResult =
        result.accountHint?['maskedPhone']?.toString().trim() ?? '';
    if (fromResult.isNotEmpty) {
      return fromResult;
    }
    return _presentation.accountHint?.maskedPhone ??
        _presentation.carrierHint?.maskedPhone ??
        '';
  }

  void _completeLogin() {
    final callback = widget.onLoggedIn;
    if (callback != null) {
      callback();
      return;
    }
    final redirect = widget.redirect?.trim() ?? '';
    if (redirect.isNotEmpty) {
      context.go(redirect);
      return;
    }
    if (ref.read(authContinuationProvider) != null) {
      ref.read(authContinuationProvider.notifier).clear();
    }
    final router = GoRouter.maybeOf(context);
    if (router != null) {
      router.go(AppRoutePaths.home);
    }
  }

  void _dismissAsGuest() {
    _trackLoginEvent(
      'login_dismissed',
      payload: <String, dynamic>{'state': _presentation.kind.name},
    );
    final callback = widget.onDismiss;
    if (callback != null) {
      callback();
      return;
    }
    final fallback = safeLoginDismissFallback(
      redirect: widget.redirect,
      dismissFallback: widget.dismissFallback,
    );
    if (widget.allowGuestDismissPop && context.canPop()) {
      context.pop();
    } else {
      context.go(fallback);
    }
  }

  @override
  Widget build(BuildContext context) {
    final content = LoginFrame(
      reason: widget.reason,
      presentation: _presentation,
      agreementAccepted: _agreementAccepted,
      isInline: widget.surfaceMode == LoginSurfaceMode.inline,
      phoneController: _phoneController,
      otpController: _otpController,
      onAgreementToggle: () =>
          setState(() => _agreementAccepted = !_agreementAccepted),
      onDismiss: _dismissAsGuest,
      onPrimary: _handlePrimaryLogin,
      onAgreementTap: () => context.push(AppRoutePaths.legalUserAgreement),
      onPrivacyTap: () => context.push(AppRoutePaths.legalPrivacyPolicy),
      onOtherMethod: _handleOtherMethod,
      onPhoneChanged: _handlePhoneChanged,
      onOtpChanged: _handleOtpChanged,
      onResendOtp: _resendPhoneOtp,
    );
    if (widget.surfaceMode == LoginSurfaceMode.inline) {
      return content;
    }
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      child: content,
    );
  }

  void _handleOtherMethod(String method) {
    _trackLoginEvent(
      'login_method_clicked',
      targetKey: method,
      payload: <String, dynamic>{'state': _presentation.kind.name},
    );
    if (method == 'phone') {
      _enterPhoneOtp();
      return;
    }
    if (method == 'wechat' || method == 'alipay' || method == 'qq') {
      unawaited(_handleSocialLogin(method));
      return;
    }
    AppToast.show(context, UITextConstants.loginMethodComingSoonToast);
  }

  NativeAuthProvider _nativeAuthProviderFor(String method) {
    return switch (method) {
      'wechat' => NativeAuthProvider.wechat,
      'alipay' => NativeAuthProvider.alipay,
      'qq' => NativeAuthProvider.qq,
      _ => throw ArgumentError.value(method, 'method', 'not a social provider'),
    };
  }

  Future<AuthLoginResultDto> _socialLoginByMethod(
    String method,
    String authCode,
    String deviceId,
    String platform,
  ) {
    final repo = ref.read(authRepositoryProvider);
    return switch (method) {
      'wechat' => repo.loginWechat(
        wechatCode: authCode,
        deviceId: deviceId,
        platform: platform,
      ),
      'alipay' => repo.loginAlipay(
        alipayAuthCode: authCode,
        deviceId: deviceId,
        platform: platform,
      ),
      'qq' => repo.loginQq(
        qqAuthCode: authCode,
        deviceId: deviceId,
        platform: platform,
      ),
      _ => throw ArgumentError.value(method, 'method', 'not a social provider'),
    };
  }

  AuthRememberedLoginMethod _rememberedMethodFor(String method) {
    return switch (method) {
      'wechat' => AuthRememberedLoginMethod.wechat,
      'alipay' => AuthRememberedLoginMethod.alipay,
      'qq' => AuthRememberedLoginMethod.qq,
      _ => AuthRememberedLoginMethod.unknown,
    };
  }

  /// 三方登录（微信/支付宝/QQ）：先经原生防腐桥取得短期授权码，再由服务端置换会话。
  /// 失败/取消只提示并保持登录页可重试，绝不在受限态二次弹登录（登录入口无死循环宪法）。
  Future<void> _handleSocialLogin(String method) async {
    if (!_agreementAccepted) {
      AppToast.show(context, UITextConstants.loginAgreementRequired);
      return;
    }
    final entryBeforeSubmit = _presentation;
    setState(() {
      _presentation = LoginEntryPresentation(
        kind: LoginEntryKind.submitting,
        accountHint: entryBeforeSubmit.accountHint,
        carrierHint: entryBeforeSubmit.carrierHint,
      );
    });
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      final deviceId = session.installId.isNotEmpty
          ? session.installId
          : stored.installId;
      final bridge = ref.read(nativeAuthBridgeProvider);
      final ticket = await bridge.signIn(_nativeAuthProviderFor(method));
      if (ticket.ticket.trim().isEmpty) {
        throw StateError('$method authorization ticket is empty');
      }
      final result = await _socialLoginByMethod(
        method,
        ticket.ticket.trim(),
        deviceId,
        CloudRequestHeaders.platform(),
      );
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginResult(
            result,
            rememberedLoginMethod: _rememberedMethodFor(method),
            rememberedLoginMaskedIdentifier: ticket.maskedAccount,
          );
      _trackLoginEvent(
        'login_success',
        targetKey: method,
        payload: <String, dynamic>{'state': entryBeforeSubmit.kind.name},
      );
      _completeLogin();
    } catch (error) {
      // 三方失败/取消：回到失败前的有效态并提示，保持登录页可重试或换路径，
      // 绝不在受限态二次弹登录（登录入口无死循环宪法）。
      _applyTopLevelLoginFailure(
        entryBeforeSubmit,
        error,
        fallbackMessage: UserErrorCode.socialProviderUnavailable.defaultMessage,
      );
    }
  }

  void _trackLoginEvent(
    String action, {
    String targetKey = '',
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) {
    unawaited(
      _journeyTracker.trackAction(
        journey: _loginJourney,
        action: action,
        pageName: _loginPageName,
        targetType: 'login',
        targetKey: targetKey,
        payload: <String, dynamic>{
          'surfaceMode': widget.surfaceMode.name,
          if ((widget.reason ?? '').trim().isNotEmpty) 'reason': widget.reason,
          ...payload,
        },
      ),
    );
  }
}

class LoginFrame extends StatelessWidget {
  const LoginFrame({
    super.key,
    required this.reason,
    required this.presentation,
    required this.agreementAccepted,
    required this.onAgreementToggle,
    required this.onDismiss,
    required this.onPrimary,
    required this.onAgreementTap,
    required this.onPrivacyTap,
    required this.onOtherMethod,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onOtpChanged,
    required this.onResendOtp,
    this.isInline = false,
  });

  final String? reason;
  final LoginEntryPresentation presentation;
  final bool agreementAccepted;
  final VoidCallback onAgreementToggle;
  final VoidCallback onDismiss;
  final VoidCallback onPrimary;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;
  final ValueChanged<String> onOtherMethod;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResendOtp;
  final bool isInline;

  @override
  Widget build(BuildContext context) {
    final copy = _loginHeroCopyForPresentation(presentation, reason);
    final content = DecoratedBox(
      decoration: BoxDecoration(color: AppColors.loginPageBackground(context)),
      // 单屏布局：内容按设计已收紧到常见 iPhone 一屏可容纳，弹性 Spacer 把
      // "其他登录方式"贴底完整展示；ClampingScrollPhysics 去掉 iOS 回弹/阻尼，
      // 内容适配时不可滑动，仅在极小屏作为兜底（不裁切）。
      child: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              physics: const ClampingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: AppSpacing.loginFrameMaxWidth,
                    minHeight: constraints.maxHeight,
                  ),
                  child: IntrinsicHeight(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.loginFrameHorizontalPadding,
                        vertical: AppSpacing.loginFrameVerticalPadding,
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.max,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: <Widget>[
                          _LoginTopBar(onDismiss: onDismiss),
                          const SizedBox(
                            height: AppSpacing.loginTopBarToHeroGap,
                          ),
                          LoginHeroBrand(
                            title: copy.title,
                            subtitle: copy.subtitle,
                          ),
                          const SizedBox(
                            height: AppSpacing.loginHeroToAccountGap,
                          ),
                          LoginAccountArea(
                            presentation: presentation,
                            phoneController: phoneController,
                            otpController: otpController,
                            onPhoneChanged: onPhoneChanged,
                            onOtpChanged: onOtpChanged,
                            onResendOtp: onResendOtp,
                          ),
                          if (_showsTopLevelError(presentation)) ...<Widget>[
                            const SizedBox(height: AppSpacing.sm),
                            // 入口级（returning/carrier）失败均为可恢复降级提示，用中性语气；
                            // 真正阻断态（锁定/封禁/注销）已路由到验证码面板按 phase 取红色。
                            _TopLevelErrorBanner(
                              message: presentation.message,
                              tone: LoginMessageTone.neutral,
                            ),
                          ],
                          const SizedBox(
                            height: AppSpacing.loginAccountToButtonGap,
                          ),
                          PrimaryLoginButton(
                            label: presentation.primaryLabel,
                            isSubmitting:
                                presentation.kind == LoginEntryKind.submitting,
                            enabled: presentation.canSubmit,
                            onPressed: onPrimary,
                          ),
                          const SizedBox(
                            height: AppSpacing.loginButtonToAgreementGap,
                          ),
                          LoginAgreementRow(
                            accepted: agreementAccepted,
                            onToggle: onAgreementToggle,
                            onAgreementTap: onAgreementTap,
                            onPrivacyTap: onPrivacyTap,
                          ),
                          const Spacer(),
                          const SizedBox(
                            height: AppSpacing.loginAgreementToOtherGap,
                          ),
                          OtherLoginMethodGrid(
                            onTap: onOtherMethod,
                            mode: presentation.kind == LoginEntryKind.phoneOtp
                                ? OtherLoginMethodMode.phoneOtp
                                : OtherLoginMethodMode.returning,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
    if (!isInline) {
      return content;
    }
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.loginPageBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: AppColors.webPcLoginSurfaceShadow,
            blurRadius: AppSpacing.webPcToolbarElevationBlurRadius,
            offset: Offset(AppSpacing.zero, AppSpacing.ten),
          ),
        ],
      ),
      child: content,
    );
  }
}

/// 顶层（非手机号输入）态的错误是否需要就近横幅展示。
/// phoneOtp 由 PhoneOtpPanel 内部自带 message，不在此重复。
bool _showsTopLevelError(LoginEntryPresentation presentation) {
  if (presentation.kind == LoginEntryKind.phoneOtp) {
    return false;
  }
  return presentation.message.trim().isNotEmpty;
}

class _TopLevelErrorBanner extends StatelessWidget {
  const _TopLevelErrorBanner({
    required this.message,
    this.tone = LoginMessageTone.neutral,
  });

  final String message;

  /// 顶层提示语气。一键/三方登录失败后的降级提示通常可恢复（中性/琥珀），
  /// 红色仅用于真正阻断态（此类已路由到验证码面板，几乎不会经此横幅）。
  final LoginMessageTone tone;

  @override
  Widget build(BuildContext context) {
    final color = loginMessageToneColor(context, tone);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.loginInputRadius),
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          height: AppSpacing.textLineHeightBody,
          color: color,
        ),
      ),
    );
  }
}

LoginReasonCopy _loginHeroCopyForPresentation(
  LoginEntryPresentation presentation,
  String? routeReason,
) {
  return switch (presentation.kind) {
    LoginEntryKind.returningAccount => LoginReasonCopy(
      title: UITextConstants.loginReturningHeroTitle,
      subtitle: presentation.oneTapCredentialAvailable
          ? UITextConstants.loginReturningHeroSubtitle
          : UITextConstants.loginSessionExpiredHint,
      source: LoginReasonCopySource.localSession,
    ),
    LoginEntryKind.carrierPhone => const LoginReasonCopy(
      title: UITextConstants.loginCarrierHeroTitle,
      subtitle: UITextConstants.loginCarrierHeroSubtitle,
      source: LoginReasonCopySource.cloudHint,
    ),
    _ => loginReasonCopyForName(routeReason),
  };
}

class _LoginTopBar extends StatelessWidget {
  const _LoginTopBar({required this.onDismiss});

  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Semantics(
          button: true,
          label: UITextConstants.loginDismissSemanticLabel,
          child: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: onDismiss,
            color: AppColors.iosLabel(context),
          ),
        ),
        const Spacer(),
      ],
    );
  }
}

class LoginHeroBrand extends StatelessWidget {
  const LoginHeroBrand({
    super.key,
    required this.title,
    required this.subtitle,
  });

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Semantics(
          image: true,
          label: UITextConstants.loginBrandIconSemanticLabel,
          child: Container(
            width: AppSpacing.loginBrandMarkSize,
            height: AppSpacing.loginBrandMarkSize,
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(
                AppSpacing.loginBrandMarkRadius,
              ),
              boxShadow: const <BoxShadow>[
                BoxShadow(
                  color: AppColors.webPcLoginSurfaceShadow,
                  blurRadius: AppSpacing.ten,
                  offset: Offset(AppSpacing.zero, AppSpacing.six),
                ),
              ],
            ),
            child: CustomPaint(
              painter: WelcomeAppIconPainter(
                appearance: WelcomeAppearance.brandMark(),
              ),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.ten),
        Text(
          UITextConstants.loginBrandName,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosTitle3,
            fontWeight: AppTypography.bold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.loginBrandToTitleGap),
        Text(
          title,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            fontWeight: AppTypography.semiBold,
            height: AppTypography.lineHeightTight,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.six),
        Text(
          subtitle,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            height: AppSpacing.textLineHeightBody,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class LoginAccountArea extends StatelessWidget {
  const LoginAccountArea({
    super.key,
    required this.presentation,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onOtpChanged,
    required this.onResendOtp,
  });

  final LoginEntryPresentation presentation;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResendOtp;

  @override
  Widget build(BuildContext context) {
    final child = switch (presentation.kind) {
      LoginEntryKind.returningAccount => ReturningAccountPanel(
        hint: presentation.accountHint ?? presentation.carrierHint?.accountHint,
      ),
      LoginEntryKind.carrierPhone => CarrierPhonePanel(
        hint: presentation.carrierHint,
      ),
      LoginEntryKind.phoneOtp => PhoneOtpPanel(
        state: presentation.phoneOtpState ?? const LoginPhoneOtpState.idle(),
        phoneController: phoneController,
        otpController: otpController,
        onPhoneChanged: onPhoneChanged,
        onOtpChanged: onOtpChanged,
        onResend: onResendOtp,
      ),
      LoginEntryKind.resolving ||
      LoginEntryKind.submitting => const _ResolvingPanel(),
      LoginEntryKind.error => UnavailablePanel(message: presentation.message),
      LoginEntryKind.unavailable => UnavailablePanel(
        message: presentation.message,
      ),
    };
    final areaHeight = _heightForPresentation(presentation);
    if (areaHeight == null) {
      return child;
    }
    return SizedBox(height: areaHeight, child: child);
  }

  double? _heightForPresentation(LoginEntryPresentation presentation) {
    if (presentation.kind == LoginEntryKind.phoneOtp) {
      return null;
    }
    return AppSpacing.loginAccountAreaHeight;
  }
}

class ReturningAccountPanel extends StatelessWidget {
  const ReturningAccountPanel({super.key, required this.hint});

  final LoginAccountHint? hint;

  @override
  Widget build(BuildContext context) {
    final displayName = hint?.displayName.isNotEmpty == true
        ? hint!.displayName
        : UITextConstants.loginReturningDefaultName;
    final maskedPhone = hint?.maskedPhone ?? '';
    return Column(
      key: const ValueKey<String>('returningAccount'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        _Avatar(avatarUrl: hint?.avatarUrl ?? '', displayName: displayName),
        const SizedBox(height: AppSpacing.sm),
        Text(
          displayName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.xl,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          maskedPhone.isEmpty
              ? UITextConstants.loginReturningDefaultAccount
              : maskedPhone,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class CarrierPhonePanel extends StatelessWidget {
  const CarrierPhonePanel({super.key, required this.hint});

  final CarrierPhoneHint? hint;

  @override
  Widget build(BuildContext context) {
    final phone = hint?.maskedPhone ?? '';
    return Column(
      key: const ValueKey<String>('carrierPhone'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        Text(
          phone.isEmpty ? UITextConstants.loginCarrierDefaultPhone : phone,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosProfileTitle,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          UITextConstants.loginCarrierCreateHint,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class PhoneOtpPanel extends StatelessWidget {
  const PhoneOtpPanel({
    super.key,
    required this.state,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onOtpChanged,
    required this.onResend,
  });

  final LoginPhoneOtpState state;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResend;

  @override
  Widget build(BuildContext context) {
    final showsCode = state._showsCode || state.code.isNotEmpty;
    final message = _messageForState();
    return AutofillGroup(
      child: Column(
        key: ValueKey<String>('phoneOtp-${state.phase.name}'),
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          PhoneNumberField(
            controller: phoneController,
            enabled: state.isPhoneEditable,
            hasError: state.phase == LoginPhoneOtpPhase.invalid,
            onChanged: onPhoneChanged,
          ),
          if (showsCode) ...<Widget>[
            const SizedBox(height: AppSpacing.ten),
            Text(
              _otpSentLine(),
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            const SizedBox(height: AppSpacing.ten),
            OtpCodeBoxes(
              controller: otpController,
              enabled: !state.isCodeDisabled,
              hasError: state.phase == LoginPhoneOtpPhase.codeError,
              onChanged: onOtpChanged,
            ),
            const SizedBox(height: AppSpacing.sm),
            _OtpResendAction(
              resendSeconds: state.resendSeconds,
              enabled: state.canSendCode,
              onResend: onResend,
            ),
          ],
          if (message.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: loginMessageToneColor(
                  context,
                  loginMessageToneForPhase(state.phase),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _messageForState() {
    if (state.phase == LoginPhoneOtpPhase.success) {
      return UITextConstants.loginRedirecting;
    }
    if (state.message.isNotEmpty) {
      return state.message;
    }
    // 兜底文案：异常/过渡态在 state.message 缺失时（例如纯构造或离线）仍给出
    // 明确、可指引下一步的提示，杜绝空白提示导致用户不知所措。
    return switch (state.phase) {
      LoginPhoneOtpPhase.editing => UITextConstants.loginPhoneRequired,
      LoginPhoneOtpPhase.invalid => UITextConstants.loginPhoneInvalid,
      LoginPhoneOtpPhase.sendingCode => UITextConstants.loginSendOtpSubmitting,
      LoginPhoneOtpPhase.codeError => UITextConstants.loginOtpMismatch,
      LoginPhoneOtpPhase.codeExpired => UITextConstants.loginOtpExpired,
      LoginPhoneOtpPhase.rateLimited =>
        UITextConstants.loginOtpRateLimited.replaceFirst(
          '%d',
          '${state.resendSeconds > 0 ? state.resendSeconds : 60}',
        ),
      LoginPhoneOtpPhase.sendFailed => UITextConstants.loginOtpSendFailed,
      LoginPhoneOtpPhase.loginLocked => UITextConstants.loginPhoneLoginLocked,
      LoginPhoneOtpPhase.accountSuspended =>
        UITextConstants.loginAccountSuspended,
      LoginPhoneOtpPhase.accountDeleted => UITextConstants.loginAccountDeleted,
      _ => '',
    };
  }

  String _otpSentLine() {
    final maskedPhone = state.maskedPhone.isEmpty
        ? _maskPhone(state.phone)
        : state.maskedPhone;
    final base = UITextConstants.loginOtpSentTo.replaceFirst('%s', maskedPhone);
    if (state.debugCode.isEmpty) {
      return base;
    }
    return '$base  ${UITextConstants.loginOtpDebugCodePrefix}${state.debugCode}';
  }
}

/// 重发验证码动作：倒计时进行中显示禁用倒计时文案；倒计时结束且可发码时
/// 显示可点击的"重新获取"，让用户在任何"想换一份验证码"的态下都有明确出口。
class _OtpResendAction extends StatelessWidget {
  const _OtpResendAction({
    required this.resendSeconds,
    required this.enabled,
    required this.onResend,
  });

  final int resendSeconds;
  final bool enabled;
  final VoidCallback onResend;

  @override
  Widget build(BuildContext context) {
    final counting = resendSeconds > 0;
    final label = counting
        ? UITextConstants.loginOtpResendCountdown.replaceFirst(
            '%d',
            '$resendSeconds',
          )
        : UITextConstants.loginOtpResend;
    final canTap = enabled && !counting;
    return Semantics(
      button: true,
      enabled: canTap,
      label: UITextConstants.loginOtpResend,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: canTap ? onResend : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          child: Text(
            label,
            key: const ValueKey<String>('loginOtpResendAction'),
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: canTap
                  ? AppColors.iosAccent(context)
                  : AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
      ),
    );
  }
}

class PhoneNumberField extends StatefulWidget {
  const PhoneNumberField({
    super.key,
    required this.controller,
    required this.enabled,
    required this.hasError,
    required this.onChanged,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool hasError;
  final ValueChanged<String> onChanged;

  @override
  State<PhoneNumberField> createState() => _PhoneNumberFieldState();
}

class _LoginInputDecorationSpec {
  const _LoginInputDecorationSpec({
    required this.surface,
    required this.border,
    required this.borderWidth,
    required this.shadow,
  });

  final Color surface;
  final Color border;
  final double borderWidth;
  final List<BoxShadow> shadow;
}

_LoginInputDecorationSpec _loginInputDecorationForState(
  BuildContext context, {
  required bool focused,
  required bool hasError,
  bool enabled = true,
}) {
  final border = hasError
      ? AppColors.iosDestructive(context)
      : focused
      ? AppColors.loginInputFocusedBorder(context)
      : AppColors.loginInputBorder(context);
  return _LoginInputDecorationSpec(
    surface: AppColors.loginInputSurface(context),
    border: border,
    borderWidth: focused || hasError ? AppSpacing.oneHalf : AppSpacing.one,
    shadow: <BoxShadow>[
      if (focused && enabled)
        BoxShadow(
          color: AppColors.loginInputFocusedBorder(
            context,
          ).withValues(alpha: 0.10),
          blurRadius: AppSpacing.ten,
          offset: const Offset(AppSpacing.zero, AppSpacing.three),
        ),
    ],
  );
}

class _PhoneNumberFieldState extends State<PhoneNumberField> {
  late final FocusNode _focusNode;
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode();
    _focusNode.addListener(_handleFocusChanged);
  }

  @override
  void dispose() {
    _focusNode.removeListener(_handleFocusChanged);
    _focusNode.dispose();
    super.dispose();
  }

  void _handleFocusChanged() {
    if (mounted) {
      setState(() => _focused = _focusNode.hasFocus);
    }
  }

  @override
  Widget build(BuildContext context) {
    final decoration = _loginInputDecorationForState(
      context,
      focused: _focused,
      hasError: widget.hasError,
      enabled: widget.enabled,
    );
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.enabled ? () => _focusNode.requestFocus() : null,
      child: Container(
        height: AppSpacing.loginPhoneFieldHeight,
        decoration: BoxDecoration(
          color: decoration.surface,
          borderRadius: BorderRadius.circular(AppSpacing.loginInputRadius),
          border: Border.all(
            color: decoration.border,
            width: decoration.borderWidth,
          ),
          boxShadow: decoration.shadow,
        ),
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Row(
          children: <Widget>[
            Text(
              '+86',
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosLabel(context),
                fontWeight: AppTypography.semiBold,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Container(
              width: AppSpacing.one,
              height: AppSpacing.twenty,
              color: AppColors.iosSeparator(context),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: CupertinoTextField.borderless(
                controller: widget.controller,
                enabled: widget.enabled,
                focusNode: _focusNode,
                keyboardType: TextInputType.phone,
                autofillHints: const <String>[AutofillHints.telephoneNumber],
                placeholder: UITextConstants.loginPhoneNumberPlaceholder,
                inputFormatters: <TextInputFormatter>[
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(11),
                ],
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: widget.enabled
                      ? AppColors.iosLabel(context)
                      : AppColors.iosSecondaryLabel(context),
                ),
                placeholderStyle: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: AppColors.iosTertiaryLabel(context),
                ),
                onChanged: widget.onChanged,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class OtpCodeBoxes extends StatelessWidget {
  const OtpCodeBoxes({
    super.key,
    required this.controller,
    required this.enabled,
    required this.hasError,
    required this.onChanged,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool hasError;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return _OtpCodeBoxesBody(
      controller: controller,
      enabled: enabled,
      hasError: hasError,
      onChanged: onChanged,
    );
  }
}

class _OtpCodeBoxesBody extends StatefulWidget {
  const _OtpCodeBoxesBody({
    required this.controller,
    required this.enabled,
    required this.hasError,
    required this.onChanged,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool hasError;
  final ValueChanged<String> onChanged;

  @override
  State<_OtpCodeBoxesBody> createState() => _OtpCodeBoxesBodyState();
}

class _OtpCodeBoxesBodyState extends State<_OtpCodeBoxesBody> {
  late final FocusNode _focusNode;
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode();
    _focusNode.addListener(_handleFocusChanged);
  }

  @override
  void dispose() {
    _focusNode.removeListener(_handleFocusChanged);
    _focusNode.dispose();
    super.dispose();
  }

  void _handleFocusChanged() {
    if (mounted) {
      setState(() => _focused = _focusNode.hasFocus);
    }
  }

  @override
  Widget build(BuildContext context) {
    final decoration = _loginInputDecorationForState(
      context,
      focused: _focused,
      hasError: widget.hasError,
      enabled: widget.enabled,
    );
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.enabled ? () => _focusNode.requestFocus() : null,
      child: SizedBox(
        height: AppSpacing.loginOtpBoxSize,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            LayoutBuilder(
              builder: (context, constraints) {
                final gap = AppSpacing.loginOtpBoxGap;
                final availableWidth = constraints.maxWidth.isFinite
                    ? constraints.maxWidth
                    : AppSpacing.loginOtpBoxSize * 6 + gap * 5;
                final boxSize = ((availableWidth - gap * 5) / 6).clamp(
                  AppSpacing.loginOtpBoxMinSize,
                  AppSpacing.loginOtpBoxSize,
                );
                return Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: List<Widget>.generate(6, (index) {
                    final value = index < widget.controller.text.length
                        ? widget.controller.text[index]
                        : '';
                    return Padding(
                      padding: EdgeInsets.only(
                        right: index == 5 ? AppSpacing.zero : gap,
                      ),
                      child: Container(
                        width: boxSize,
                        height: boxSize,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: decoration.surface,
                          borderRadius: BorderRadius.circular(
                            AppSpacing.loginOtpBoxRadius,
                          ),
                          border: Border.all(
                            color: decoration.border,
                            width: decoration.borderWidth,
                          ),
                          boxShadow: decoration.shadow,
                        ),
                        child: Text(
                          value,
                          style: TextStyle(
                            fontSize: AppTypography.iosTitle3,
                            fontWeight: AppTypography.semiBold,
                            color: AppColors.iosLabel(context),
                          ),
                        ),
                      ),
                    );
                  }),
                );
              },
            ),
            Opacity(
              opacity: 0.01,
              child: SizedBox(
                height: AppSpacing.loginOtpBoxSize,
                child: CupertinoTextField.borderless(
                  controller: widget.controller,
                  enabled: widget.enabled,
                  focusNode: _focusNode,
                  autofocus: false,
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.done,
                  autofillHints: const <String>[AutofillHints.oneTimeCode],
                  enableInteractiveSelection: true,
                  inputFormatters: <TextInputFormatter>[
                    FilteringTextInputFormatter.digitsOnly,
                    LengthLimitingTextInputFormatter(6),
                  ],
                  onChanged: widget.onChanged,
                  onSubmitted: widget.onChanged,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class UnavailablePanel extends StatelessWidget {
  const UnavailablePanel({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const ValueKey<String>('unavailable'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        Icon(
          CupertinoIcons.device_phone_portrait,
          size: AppSpacing.forty,
          color: AppColors.iosSecondaryLabel(context),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          message.isEmpty ? UITextConstants.loginCarrierUnavailable : message,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosCallout,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class _ResolvingPanel extends StatelessWidget {
  const _ResolvingPanel();

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const ValueKey<String>('resolving'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        CupertinoActivityIndicator(color: AppColors.iosAccent(context)),
        const SizedBox(height: AppSpacing.loginOtherTitleToIconsGap),
        Text(
          UITextConstants.loginResolvingHint,
          style: TextStyle(
            fontSize: AppTypography.iosCallout,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.avatarUrl, required this.displayName});

  final String avatarUrl;
  final String displayName;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSpacing.loginAvatarSize,
      height: AppSpacing.loginAvatarSize,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: AppColors.iosAccent(context).withValues(alpha: 0.16),
      ),
      clipBehavior: Clip.antiAlias,
      alignment: Alignment.center,
      child: avatarUrl.isEmpty
          ? Text(
              displayName.isEmpty
                  ? UITextConstants.loginDefaultAvatarGlyph
                  : displayName.characters.first,
              style: TextStyle(
                fontSize: AppTypography.iosProfileTitle,
                fontWeight: AppTypography.bold,
                color: AppColors.iosAccent(context),
              ),
            )
          : Image.network(
              avatarUrl,
              fit: BoxFit.cover,
              width: AppSpacing.loginAvatarSize,
              height: AppSpacing.loginAvatarSize,
              errorBuilder: (_, __, ___) => Text(
                UITextConstants.loginDefaultAvatarGlyph,
                style: TextStyle(
                  fontSize: AppTypography.iosProfileTitle,
                  fontWeight: AppTypography.bold,
                  color: AppColors.iosAccent(context),
                ),
              ),
            ),
    );
  }
}

class PrimaryLoginButton extends StatelessWidget {
  const PrimaryLoginButton({
    super.key,
    required this.label,
    required this.isSubmitting,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final bool isSubmitting;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      enabled: enabled && !isSubmitting,
      label: label,
      child: CupertinoButton(
        minSize: AppSpacing.loginPrimaryButtonHeight,
        padding: EdgeInsets.zero,
        color: enabled
            ? AppColors.iosAccent(context)
            : AppColors.loginPrimaryDisabled(context),
        disabledColor: AppColors.loginPrimaryDisabled(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
        onPressed: enabled && !isSubmitting ? onPressed : null,
        child: isSubmitting
            ? const CupertinoActivityIndicator(color: CupertinoColors.white)
            : Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: FontWeight.w600,
                  color: enabled
                      ? CupertinoColors.white
                      : CupertinoColors.white.withValues(alpha: 0.76),
                ),
              ),
      ),
    );
  }
}

class LoginAgreementRow extends StatelessWidget {
  const LoginAgreementRow({
    super.key,
    required this.accepted,
    required this.onToggle,
    required this.onAgreementTap,
    required this.onPrivacyTap,
  });

  final bool accepted;
  final VoidCallback onToggle;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        CupertinoButton(
          padding: EdgeInsets.zero,
          minSize: 44,
          onPressed: onToggle,
          child: Icon(
            accepted
                ? CupertinoIcons.check_mark_circled_solid
                : CupertinoIcons.circle,
            size: AppSpacing.twenty,
            color: accepted
                ? AppColors.iosAccent(context)
                : AppColors.iosSecondaryLabel(context),
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Wrap(
              children: <Widget>[
                Text(
                  UITextConstants.loginAgreementPrefix,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
                _AgreementLink(
                  label: UITextConstants.userAgreement,
                  onTap: onAgreementTap,
                ),
                Text(
                  UITextConstants.loginAgreementAnd,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
                _AgreementLink(
                  label: UITextConstants.privacyPolicy,
                  onTap: onPrivacyTap,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _AgreementLink extends StatelessWidget {
  const _AgreementLink({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.base,
          color: AppColors.iosAccent(context),
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }
}

enum OtherLoginMethodMode { returning, phoneOtp }

class OtherLoginMethodGrid extends StatelessWidget {
  const OtherLoginMethodGrid({
    super.key,
    required this.onTap,
    this.mode = OtherLoginMethodMode.phoneOtp,
  });

  final ValueChanged<String> onTap;
  final OtherLoginMethodMode mode;

  @override
  Widget build(BuildContext context) {
    final entries = mode == OtherLoginMethodMode.returning
        ? const <
            ({
              String id,
              IconData icon,
              Color background,
              Color iconColor,
              double iconSize,
              String label,
              String semanticLabel,
            })
          >[
            (
              id: 'wechat',
              icon: SimpleIcons.wechat,
              background: AppColors.loginMethodWechatBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodWechatFull,
              semanticLabel: UITextConstants.loginMethodWechatSemanticLabel,
            ),
            (
              id: 'qq',
              icon: SimpleIcons.qq,
              background: AppColors.loginMethodQqBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodQqFull,
              semanticLabel: UITextConstants.loginMethodQqSemanticLabel,
            ),
            (
              id: 'phone',
              icon: Icons.phone_iphone,
              background: AppColors.loginMethodPhoneCircle,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodPhoneFull,
              semanticLabel: UITextConstants.loginMethodPhoneSemanticLabel,
            ),
          ]
        : const <
            ({
              String id,
              IconData icon,
              Color background,
              Color iconColor,
              double iconSize,
              String label,
              String semanticLabel,
            })
          >[
            (
              id: 'phone',
              icon: Icons.phone_iphone,
              background: AppColors.loginMethodPhoneCircle,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodPhone,
              semanticLabel: UITextConstants.loginMethodPhoneSemanticLabel,
            ),
            (
              id: 'wechat',
              icon: SimpleIcons.wechat,
              background: AppColors.loginMethodWechatBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodWechat,
              semanticLabel: UITextConstants.loginMethodWechatSemanticLabel,
            ),
            (
              id: 'qq',
              icon: SimpleIcons.qq,
              background: AppColors.loginMethodQqBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodQq,
              semanticLabel: UITextConstants.loginMethodQqSemanticLabel,
            ),
            (
              id: 'alipay',
              icon: SimpleIcons.alipay,
              background: AppColors.loginMethodAlipayBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodAlipay,
              semanticLabel: UITextConstants.loginMethodAlipaySemanticLabel,
            ),
          ];
    return Column(
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Container(
                height: AppSpacing.one,
                color: AppColors.loginOtherDivider(context),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              child: Text(
                UITextConstants.loginOtherMethods,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ),
            Expanded(
              child: Container(
                height: AppSpacing.one,
                color: AppColors.loginOtherDivider(context),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        Align(
          alignment: Alignment.center,
          child: SizedBox(
            width: mode == OtherLoginMethodMode.returning
                ? AppSpacing.loginOtherMethodsThreeColumnWidth
                : double.infinity,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: entries
                  .map((entry) {
                    return Semantics(
                      button: true,
                      label: entry.semanticLabel,
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () => onTap(entry.id),
                        child: Column(
                          children: <Widget>[
                            Container(
                              width: AppSpacing.loginOtherMethodSize,
                              height: AppSpacing.loginOtherMethodSize,
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: entry.background,
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                entry.icon,
                                size: entry.iconSize,
                                color: entry.iconColor,
                              ),
                            ),
                            const SizedBox(height: AppSpacing.xs),
                            Text(
                              entry.label,
                              style: TextStyle(
                                fontSize: AppTypography.iosCaption1,
                                color: AppColors.iosSecondaryLabel(context),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  })
                  .toList(growable: false),
            ),
          ),
        ),
      ],
    );
  }
}
