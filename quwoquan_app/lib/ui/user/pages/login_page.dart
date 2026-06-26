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
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';
import 'package:simple_icons/simple_icons.dart';

part 'login_page_top_bar.dart';
part 'login_page_models.dart';
part 'login_page_frame.dart';
part 'login_page_form_controls.dart';

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
  final VoidCallback? onDismiss, onLoggedIn;
  final LoginSurfaceMode surfaceMode;

  @override
  ConsumerState<LoginFrameHost> createState() => _LoginFrameHostState();
}

class _LoginFrameHostState extends ConsumerState<LoginFrameHost> {
  static const Duration _probeTimeout = Duration(milliseconds: 1200);
  static const String _loginJourney = 'two_state_login',
      _loginPageName = 'LoginPage';

  bool _agreementAccepted = false;
  LoginEntryPresentation _presentation =
      const LoginEntryPresentation.resolving();
  OneTapLoginProbe? _probe;
  late final JourneyEventTracker _journeyTracker;
  late final TextEditingController _phoneController, _otpController;
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
  /// - 无完整号（三方登录 / 既往数据缺失）：回退到空号手动输入态。
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
        mockDataSourceActive: ref.read(mockDataSourceActiveProvider),
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

  /// 顶层登录失败（一键/既往会话/三方）统一恢复：绝不停在不可操作空面板。
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
      allowGuestDismissPop: widget.allowGuestDismissPop,
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
