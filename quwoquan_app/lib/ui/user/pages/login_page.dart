import 'dart:async';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/one_tap_login_hint_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_legal_config.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/di/login_dependencies.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:simple_icons/simple_icons.dart';
part 'login_page_top_bar.dart';
part 'login_page_models.dart';
part 'login_page_entry_surfaces.dart';
part 'login_page_frame.dart';
part 'login_page_form_controls.dart';
part 'login_page_social_actions.dart';

class LoginFrameHost extends ConsumerStatefulWidget {
  const LoginFrameHost({
    super.key,
    this.reason,
    this.redirect,
    this.dismissFallback,
    this.dismissPolicy = LoginDismissPolicy.popPrevious,
    this.onDismiss,
    this.onLoggedIn,
    this.surfaceMode = LoginSurfaceMode.page,
  });
  final String? reason;
  final String? redirect;
  final String? dismissFallback;
  final LoginDismissPolicy dismissPolicy;
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
  bool _showAgreementError = false;
  LoginEntryPresentation _presentation =
      const LoginEntryPresentation.resolving();
  OneTapLoginProbe? _probe;
  int _attemptSerial = 0;
  int? _activeAttempt;
  int _entryResolutionGeneration = 0;
  Map<String, NativeAuthCapability> _socialMethodAvailability =
      const <String, NativeAuthCapability>{};
  String _socialMethodFeedback = '';
  late final JourneyEventTracker _journeyTracker;
  late final TextEditingController _phoneController, _otpController;
  Timer? _otpCountdownTimer;
  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(loginJourneyEventTrackerProvider);
    _phoneController = TextEditingController();
    _otpController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackLoginEvent('login_page_exposed');
    });
    unawaited(_resolveEntryState());
  }

  @override
  void dispose() {
    _activeAttempt = null;
    _entryResolutionGeneration += 1;
    _otpCountdownTimer?.cancel();
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _resolveEntryState() async {
    final generation = ++_entryResolutionGeneration;
    final storedFuture = ref.read(authSessionStoreProvider).read();
    final socialFuture = _loadSocialMethodAvailability();
    final probeFuture = ref
        .read(oneTapLoginClientProvider)
        .probe()
        .timeout(_probeTimeout)
        .onError(
          (_, _) => const OneTapLoginProbe(
            availability: OneTapAvailability.probeTimeout,
            reason: 'timeout',
          ),
        );
    final stored = await storedFuture;
    final socialAvailability = await socialFuture;
    if (!mounted || generation != _entryResolutionGeneration) return;
    _replaceSocialMethodAvailability(socialAvailability);
    final session = ref.read(authSessionControllerProvider);
    final localHint = LoginAccountHint(
      displayName: stored.rememberedDisplayName,
      avatarUrl: stored.rememberedAvatarUrl,
      maskedPhone: stored.rememberedLoginMaskedIdentifier,
      identityOrigin: stored.identityOrigin,
      nicknameCustomized: stored.rememberedNicknameCustomized,
    );
    if (localHint.hasConcreteIdentifier) {
      final caps = ref.read(platformCapabilitiesProvider);
      final hasQuickLogin = caps.quickLoginPersistence
          ? stored.hasValidQuickLoginCredential
          : stored.refreshToken.trim().isNotEmpty;
      final fullPhone = _validFullPhoneOrEmpty(
        stored.rememberedLoginIdentifier,
      );
      final socialMethod = _socialMethodForRemembered(
        stored.rememberedLoginMethod,
      );
      final action = hasQuickLogin
          ? LoginPrimaryAction.continueSession
          : stored.rememberedLoginMethod ==
                    AuthRememberedLoginMethod.phoneOtp &&
                fullPhone.isNotEmpty
          ? LoginPrimaryAction.phoneReauth
          : socialMethod.isNotEmpty &&
                socialAvailability[socialMethod]?.isAvailable == true
          ? LoginPrimaryAction.socialReauth
          : LoginPrimaryAction.none;
      if (action != LoginPrimaryAction.none) {
        _setPresentation(
          LoginEntryPresentation(
            kind: LoginEntryKind.returningAccount,
            accountHint: localHint,
            primaryAction: action,
            primaryProvider: socialMethod,
            quickLoginPhone: fullPhone,
          ),
        );
        return;
      }
    }
    try {
      final probe = await probeFuture;
      if (!mounted || generation != _entryResolutionGeneration) return;
      _probe = probe;
      if (!probe.canOfferLogin) {
        _trackLoginEvent(
          'login_carrier_capability_resolved',
          targetKey: 'carrier',
          payload: <String, dynamic>{
            'capabilityReason': probe.availability.name,
          },
        );
        _enterPhoneOtp();
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
      if (!mounted || generation != _entryResolutionGeneration) return;
      _applyCarrierHint(probe, hint);
    } catch (_) {
      if (mounted && generation == _entryResolutionGeneration) {
        _enterPhoneOtp();
      }
    }
  }

  void _invalidateEntryResolution() => _entryResolutionGeneration += 1;

  int _beginLoginAttempt() {
    final attempt = ++_attemptSerial;
    _activeAttempt = attempt;
    return attempt;
  }

  bool _isCurrentLoginAttempt(int attempt) =>
      mounted && _activeAttempt == attempt;

  void _finishLoginAttempt(int attempt) {
    if (_activeAttempt == attempt) _activeAttempt = null;
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
      accountHint: accountHint.hasConcreteIdentifier ? accountHint : null,
    );
    _setPresentation(
      LoginEntryPresentation(
        kind: LoginEntryKind.carrierPhone,
        accountHint: accountHint.hasConcreteIdentifier ? accountHint : null,
        carrierHint: carrierHint,
        primaryAction: LoginPrimaryAction.carrierOneTap,
      ),
    );
  }

  void _setPresentation(LoginEntryPresentation next) {
    if (!mounted) return;
    final previous = _presentation;
    setState(() => _presentation = next);
    _trackLoginEvent(
      'login_state_resolved',
      payload: <String, dynamic>{
        'state': next.kind.name,
        'entryMode': next.kind.name,
        'primaryAction': next.resolvedPrimaryAction.name,
        'transitionFrom': previous.kind.name,
        'transitionTo': next.kind.name,
      },
    );
  }

  void _replacePresentation(LoginEntryPresentation next) {
    if (mounted) setState(() => _presentation = next);
  }

  void _showAgreementValidation() {
    if (mounted) setState(() => _showAgreementError = true);
  }

  void _replaceSocialMethodAvailability(
    Map<String, NativeAuthCapability> availability,
  ) {
    if (mounted) setState(() => _socialMethodAvailability = availability);
  }

  void _replaceSocialMethodFeedback(String message) {
    if (mounted && _socialMethodFeedback != message) {
      setState(() => _socialMethodFeedback = message);
    }
  }

  void _enterPhoneOtp({
    LoginPhoneOtpState state = const LoginPhoneOtpState.idle(),
  }) {
    _invalidateEntryResolution();
    _setPresentation(
      LoginEntryPresentation(
        kind: LoginEntryKind.phoneOtp,
        phoneOtpState: state,
        primaryAction: state._showsCode
            ? LoginPrimaryAction.verifyOtp
            : LoginPrimaryAction.requestOtp,
      ),
    );
    _trackLoginEvent('login_phone_otp_entered');
  }

  /// 过期 returning 点「短信验证码登录」：只预填本机记住的完整手机号，
  /// 不自动发码。短信发送始终由用户显式点击并在协议校验通过后触发。
  /// - 无完整号（三方登录 / 既往数据缺失）：回退到空号手动输入态。
  void _enterReturningSmsLogin(String quickLoginPhone) {
    final fullPhone = _validFullPhoneOrEmpty(quickLoginPhone);
    if (fullPhone.isEmpty) {
      _setPresentation(
        const LoginEntryPresentation(
          kind: LoginEntryKind.phoneOtp,
          phoneOtpState: LoginPhoneOtpState.idle(),
          primaryAction: LoginPrimaryAction.requestOtp,
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
    _setPresentation(
      LoginEntryPresentation(
        kind: LoginEntryKind.phoneOtp,
        phoneOtpState: prefilled,
        primaryAction: LoginPrimaryAction.requestOtp,
        message: UITextConstants.loginSessionExpiredHint,
      ),
    );
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
        primaryAction: state._showsCode
            ? LoginPrimaryAction.verifyOtp
            : LoginPrimaryAction.requestOtp,
      );
    });
  }

  void _handlePhoneChanged(String value) {
    _invalidateEntryResolution();
    final phone = _digitsOnly(value);
    if (_phoneController.text != phone) {
      _phoneController.value = TextEditingValue(
        text: phone,
        selection: TextSelection.collapsed(offset: phone.length),
      );
    }
    _otpController.clear();
    _otpCountdownTimer?.cancel();
    // 输入期间不抢先报错；手机号格式只在用户显式提交时校验。
    final phase = phone.isEmpty
        ? LoginPhoneOtpPhase.idle
        : _isValidMainlandPhone(phone)
        ? LoginPhoneOtpPhase.valid
        : LoginPhoneOtpPhase.editing;
    _setPhoneOtpState(
      LoginPhoneOtpState(phase: phase, phone: phone, message: ''),
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
  }

  void _handlePhoneEditingComplete() {
    final state = _phoneOtpState;
    if (state.phone.isEmpty || _isValidMainlandPhone(state.phone)) {
      return;
    }
    _setPhoneOtpState(
      state.copyWith(
        phase: LoginPhoneOtpPhase.invalid,
        message: UITextConstants.loginPhoneInvalid,
      ),
    );
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
      setState(() => _showAgreementError = true);
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
    _setPhoneOtpState(
      state.copyWith(
        phase: _isValidMainlandPhone(state.phone)
            ? state.phase
            : LoginPhoneOtpPhase.invalid,
        message: message,
      ),
    );
  }

  /// 清空手机号与验证码并回到可输入态，作为"换个手机号"的统一出口。
  void _resetPhoneOtpToIdle() {
    _otpCountdownTimer?.cancel();
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
      setState(() => _showAgreementError = true);
      return;
    }
    await _sendPhoneOtp(state);
  }

  Future<void> _sendPhoneOtp(LoginPhoneOtpState state) async {
    final attempt = _beginLoginAttempt();
    final latency = Stopwatch()..start();
    _trackLoginEvent('login_otp_request_clicked');
    _setPhoneOtpState(state.copyWith(phase: LoginPhoneOtpPhase.sendingCode));
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
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
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
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
        otpWasDelivered: true,
      );
      _otpController.clear();
      _setPhoneOtpState(next);
      _startOtpCountdown(seconds);
      _trackLoginEvent(
        'login_otp_send_succeeded',
        targetKey: 'phone',
        payload: <String, dynamic>{'durationMs': latency.elapsedMilliseconds},
      );
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      final feedback = _loginFeedback(
        error,
        origin: LoginFailureOrigin.otpSend,
      );
      final next = _phoneOtpStateForFeedback(state, feedback);
      _setPhoneOtpState(next);
      if (next.resendSeconds > 0) {
        _startOtpCountdown(next.resendSeconds);
      }
      _trackLoginEvent(
        'login_otp_send_failed',
        targetKey: 'phone',
        payload: <String, dynamic>{
          ...feedback.telemetry,
          'durationMs': latency.elapsedMilliseconds,
        },
      );
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  Future<void> _submitPhoneOtpLogin(LoginPhoneOtpState state) async {
    final attempt = _beginLoginAttempt();
    final latency = Stopwatch()..start();
    _trackLoginEvent('login_phone_login_clicked');
    _setPhoneOtpState(state.copyWith(phase: LoginPhoneOtpPhase.loggingIn));
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
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
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginResult(
            result,
            rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
            rememberedLoginMaskedIdentifier: _maskPhone(state.phone),
            // 记住完整手机号（安全存储），过期后再登录只自动预填，发码仍需显式点击。
            rememberedLoginIdentifier: state.phone,
          );
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      _setPhoneOtpState(
        state.copyWith(
          phase: LoginPhoneOtpPhase.success,
          message: UITextConstants.loginRedirecting,
        ),
      );
      // 登录成功提交自动填充上下文，便于系统保存手机号/验证码以供下次自动填充。
      TextInput.finishAutofillContext();
      _trackLoginEvent(
        'login_phone_login_succeeded',
        targetKey: 'phone',
        payload: <String, dynamic>{'durationMs': latency.elapsedMilliseconds},
      );
      _completeLogin();
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      final feedback = _loginFeedback(
        error,
        origin: LoginFailureOrigin.otpLogin,
      );
      final next = _phoneOtpStateForFeedback(state, feedback);
      _setPhoneOtpState(next);
      if (next.resendSeconds > 0) {
        _startOtpCountdown(next.resendSeconds);
      }
      _trackLoginEvent(
        'login_phone_login_failed',
        targetKey: 'phone',
        payload: <String, dynamic>{
          ...feedback.telemetry,
          'durationMs': latency.elapsedMilliseconds,
        },
      );
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  LoginPhoneOtpState _phoneOtpStateForFeedback(
    LoginPhoneOtpState state,
    LoginFeedback feedback,
  ) {
    final presentation = feedback.presentation;
    if (presentation.clearCode) {
      _otpController.clear();
    }
    return state.copyWith(
      phase: presentation.phase,
      code: presentation.clearCode ? '' : state.code,
      message: feedback.message,
      resendSeconds: presentation.resendSeconds ?? state.resendSeconds,
    );
  }

  LoginFeedback _loginFeedback(
    Object error, {
    required LoginFailureOrigin origin,
    String? fallbackMessage,
  }) {
    final cloudError = error is CloudException
        ? error
        : CloudErrorMapper.fromException(error);
    final afterSeconds = cloudError.runtimeFailure.recovery.afterSeconds;
    return loginFeedbackForError(
      cloudError,
      origin: origin,
      locale: Localizations.localeOf(context).languageCode,
      entryId: widget.reason ?? 'direct',
      surfaceId: _loginPageName,
      retryAfterSeconds: afterSeconds < 0 ? 0 : afterSeconds,
      fallbackMessage: fallbackMessage,
    );
  }

  Future<void> _handlePrimaryLogin() async {
    final entryBeforeSubmit = _presentation;
    if (entryBeforeSubmit.kind == LoginEntryKind.submitting) {
      return;
    }
    _invalidateEntryResolution();
    _trackLoginEvent(
      'login_primary_clicked',
      payload: <String, dynamic>{'state': entryBeforeSubmit.kind.name},
    );
    if (entryBeforeSubmit.kind == LoginEntryKind.phoneOtp) {
      await _handlePhoneOtpPrimary();
      return;
    }
    if (entryBeforeSubmit.resolvedPrimaryAction ==
        LoginPrimaryAction.phoneReauth) {
      _enterReturningSmsLogin(entryBeforeSubmit.quickLoginPhone);
      return;
    }
    if (entryBeforeSubmit.resolvedPrimaryAction ==
        LoginPrimaryAction.socialReauth) {
      await _handleSocialLogin(entryBeforeSubmit.primaryProvider);
      return;
    }
    if (!entryBeforeSubmit.canSubmit) {
      setState(() {
        _presentation = LoginEntryPresentation(
          kind: entryBeforeSubmit.kind,
          accountHint: entryBeforeSubmit.accountHint,
          carrierHint: entryBeforeSubmit.carrierHint,
          phoneOtpState: entryBeforeSubmit.phoneOtpState,
          message: UITextConstants.loginQuickLoginUnavailableHint,
          primaryAction: entryBeforeSubmit.primaryAction,
          primaryProvider: entryBeforeSubmit.primaryProvider,
          quickLoginPhone: entryBeforeSubmit.quickLoginPhone,
        );
      });
      return;
    }
    if (!_agreementAccepted) {
      setState(() => _showAgreementError = true);
      return;
    }
    final attempt = _beginLoginAttempt();
    final latency = Stopwatch()..start();
    setState(() {
      _presentation = LoginEntryPresentation(
        kind: LoginEntryKind.submitting,
        accountHint: entryBeforeSubmit.accountHint,
        carrierHint: entryBeforeSubmit.carrierHint,
        phoneOtpState: entryBeforeSubmit.phoneOtpState,
        primaryAction: entryBeforeSubmit.primaryAction,
        primaryProvider: entryBeforeSubmit.primaryProvider,
        quickLoginPhone: entryBeforeSubmit.quickLoginPhone,
      );
    });
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      if (entryBeforeSubmit.resolvedPrimaryAction ==
          LoginPrimaryAction.continueSession) {
        if (stored.refreshToken.trim().isNotEmpty) {
          final result = await ref
              .read(authRepositoryProvider)
              .refreshToken(stored.refreshToken.trim());
          if (!_isCurrentLoginAttempt(attempt)) {
            return;
          }
          await ref
              .read(authSessionControllerProvider.notifier)
              .applyRefreshResult(result);
          if (!_isCurrentLoginAttempt(attempt)) {
            return;
          }
          _trackLoginEvent(
            'login_success',
            targetKey: 'refresh_token',
            payload: <String, dynamic>{
              'state': entryBeforeSubmit.kind.name,
              'durationMs': latency.elapsedMilliseconds,
            },
          );
          _completeLogin();
          return;
        }
        _setPresentation(
          const LoginEntryPresentation(
            kind: LoginEntryKind.phoneOtp,
            phoneOtpState: LoginPhoneOtpState.idle(),
            primaryAction: LoginPrimaryAction.requestOtp,
            message: UITextConstants.loginQuickLoginUnavailableHint,
          ),
        );
        return;
      }
      final probe = _probe;
      final carrierHint = entryBeforeSubmit.carrierHint;
      var token = carrierHint?.carrierToken ?? probe?.carrierToken ?? '';
      var vendor = carrierHint?.vendor ?? probe?.vendor ?? '';
      if (entryBeforeSubmit.resolvedPrimaryAction !=
              LoginPrimaryAction.carrierOneTap ||
          token.isEmpty ||
          vendor.isEmpty) {
        _enterPhoneOtp();
        return;
      }
      Future<AuthLoginResultDto> submitOneTap({
        required String token,
        required String vendor,
      }) {
        return ref
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
      }

      late AuthLoginResultDto result;
      try {
        result = await submitOneTap(token: token, vendor: vendor);
      } on CloudException catch (error) {
        if (error.code != UserErrorCode.carrierTokenInvalid.code) {
          rethrow;
        }
        // 运营商 token 短时有效：首次被服务端判定失效时，当前用户动作内仅刷新并重试一次。
        // 第二次仍失败则交给统一恢复矩阵降级短信，避免无限刷新和重复提交。
        final fresh = await ref
            .read(oneTapLoginClientProvider)
            .requestLoginToken()
            .timeout(_probeTimeout);
        if (!_isCurrentLoginAttempt(attempt)) {
          return;
        }
        token = fresh.carrierToken;
        vendor = fresh.vendor;
        _probe = null;
        result = await submitOneTap(token: token, vendor: vendor);
      }
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginResult(
            result,
            rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
            rememberedLoginMaskedIdentifier: _resolvedMaskedPhone(result),
          );
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      _trackLoginEvent(
        'login_success',
        targetKey: 'one_tap',
        payload: <String, dynamic>{
          'state': entryBeforeSubmit.kind.name,
          'durationMs': latency.elapsedMilliseconds,
        },
      );
      _completeLogin();
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      _applyTopLevelLoginFailure(
        entryBeforeSubmit,
        error,
        provider: 'one_tap',
        durationMs: latency.elapsedMilliseconds,
      );
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  /// 顶层登录失败（一键/既往会话/三方）统一恢复：绝不停在不可操作空面板。
  /// 规则：
  /// - 运营商系列错误 -> 降级到手机号验证码输入态，并解释原因（用户改走短信）。
  /// - 其它错误 -> 回到失败前的有效操作态（returning/carrier/phoneOtp），
  ///   由 LoginFeedback 指定唯一就近承载面，用户可重试或换路径。
  void _applyTopLevelLoginFailure(
    LoginEntryPresentation entryBeforeSubmit,
    Object error, {
    String? fallbackMessage,
    bool preserveEntry = false,
    LoginFailureOrigin origin = LoginFailureOrigin.oneTap,
    String provider = '',
    int? durationMs,
  }) {
    if (!mounted) {
      return;
    }
    final feedback = _loginFeedback(
      error,
      origin: origin,
      fallbackMessage: fallbackMessage,
    );
    if (feedback.isSilent) {
      setState(() => _presentation = entryBeforeSubmit);
      return;
    }
    if (feedback.surface == LoginErrorSurface.agreement) {
      setState(() {
        _showAgreementError = true;
        _presentation = LoginEntryPresentation(
          kind: entryBeforeSubmit.kind,
          accountHint: entryBeforeSubmit.accountHint,
          carrierHint: entryBeforeSubmit.carrierHint,
          phoneOtpState: entryBeforeSubmit.phoneOtpState,
          feedback: feedback,
          primaryAction: entryBeforeSubmit.primaryAction,
          primaryProvider: entryBeforeSubmit.primaryProvider,
          quickLoginPhone: entryBeforeSubmit.quickLoginPhone,
        );
      });
      return;
    }
    if (feedback.surface == LoginErrorSurface.accountBlocked) {
      final state =
          entryBeforeSubmit.phoneOtpState ?? const LoginPhoneOtpState.idle();
      _setPresentation(
        LoginEntryPresentation(
          kind: LoginEntryKind.phoneOtp,
          phoneOtpState: state.copyWith(
            phase: feedback.presentation.phase,
            message: feedback.message,
            resendSeconds: 0,
          ),
          feedback: feedback,
        ),
      );
      _trackLoginEvent(
        'login_failed',
        targetKey: provider,
        payload: <String, dynamic>{
          'state': LoginEntryKind.phoneOtp.name,
          ...feedback.telemetry,
          'durationMs': ?durationMs,
        },
      );
      return;
    }
    final isCarrierFailure = switch (feedback.code) {
      UserErrorCode.carrierUnavailable ||
      UserErrorCode.carrierProviderTimeout ||
      UserErrorCode.carrierTokenInvalid ||
      UserErrorCode.carrierPhoneMismatch => true,
      _ => false,
    };
    if (isCarrierFailure) {
      _setPresentation(
        LoginEntryPresentation(
          kind: LoginEntryKind.phoneOtp,
          phoneOtpState: const LoginPhoneOtpState.idle(),
          primaryAction: LoginPrimaryAction.requestOtp,
          feedback: LoginFeedback(
            cloudError: feedback.cloudError,
            code: feedback.code,
            message: feedback.message,
            presentation: feedback.presentation,
            surface: LoginErrorSurface.fallbackNotice,
            origin: feedback.origin,
          ),
          message: feedback.message,
        ),
      );
      _trackLoginEvent(
        'login_failed',
        targetKey: provider,
        payload: <String, dynamic>{
          'state': LoginEntryKind.phoneOtp.name,
          ...feedback.telemetry,
          'durationMs': ?durationMs,
        },
      );
      return;
    }
    final recoverKind =
        !preserveEntry &&
            entryBeforeSubmit.kind == LoginEntryKind.returningAccount
        ? LoginEntryKind.phoneOtp
        : entryBeforeSubmit.kind;
    setState(() {
      _presentation = LoginEntryPresentation(
        kind: recoverKind,
        accountHint: entryBeforeSubmit.accountHint,
        carrierHint: entryBeforeSubmit.carrierHint,
        phoneOtpState: entryBeforeSubmit.phoneOtpState,
        feedback: feedback,
        message: feedback.message,
        primaryAction: entryBeforeSubmit.primaryAction,
        primaryProvider: entryBeforeSubmit.primaryProvider,
        quickLoginPhone: entryBeforeSubmit.quickLoginPhone,
      );
    });
    _trackLoginEvent(
      'login_failed',
      targetKey: provider,
      payload: <String, dynamic>{
        'state': recoverKind.name,
        ...feedback.telemetry,
        'durationMs': ?durationMs,
      },
    );
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
    // continuation 仍由原目标表面按类型 take；登录页只负责把该表面恢复到前台，
    // 不与宿主竞争消费。若没有目标表面，再落安全首页。
    if (ref.read(authContinuationProvider) != null &&
        Navigator.of(context).canPop()) {
      context.pop();
      return;
    }
    final router = GoRouter.maybeOf(context);
    if (router != null) {
      router.go(AppRoutePaths.home);
    }
  }

  void _dismissAsGuest() {
    _activeAttempt = null;
    ref.read(authContinuationProvider.notifier).clear();
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
    switch (widget.dismissPolicy) {
      case LoginDismissPolicy.popPrevious:
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(fallback);
        }
      case LoginDismissPolicy.safeFallback:
        context.go(fallback);
      case LoginDismissPolicy.hostControlledClose:
        assert(
          widget.onDismiss != null,
          'hostControlledClose requires an onDismiss callback',
        );
        context.go(fallback);
    }
  }

  @override
  Widget build(BuildContext context) {
    final content = LoginFrame(
      reason: widget.reason,
      presentation: _presentation,
      agreementAccepted: _agreementAccepted,
      showAgreementError: _showAgreementError,
      socialMethodAvailability: _socialMethodAvailability,
      socialMethodFeedback: _socialMethodFeedback,
      dismissPolicy: widget.dismissPolicy,
      isInline: widget.surfaceMode == LoginSurfaceMode.inline,
      phoneController: _phoneController,
      otpController: _otpController,
      onAgreementToggle: () => setState(() {
        _agreementAccepted = !_agreementAccepted;
        if (_agreementAccepted) {
          _showAgreementError = false;
        }
      }),
      onDismiss: _dismissAsGuest,
      onPrimary: _handlePrimaryLogin,
      onAgreementTap: () => context.push(AppRoutePaths.legalUserAgreement),
      onPrivacyTap: () => context.push(AppRoutePaths.legalPrivacyPolicy),
      onOtherMethod: _handleOtherMethod,
      onPhoneChanged: _handlePhoneChanged,
      onPhoneEditingComplete: _handlePhoneEditingComplete,
      onOtpChanged: _handleOtpChanged,
      onResendOtp: _resendPhoneOtp,
      onChangePhone: _resetPhoneOtpToIdle,
    );
    if (widget.surfaceMode == LoginSurfaceMode.inline) {
      return content;
    }
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      child: content,
    );
  }
}
