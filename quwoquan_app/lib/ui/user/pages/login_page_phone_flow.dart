part of 'login_page.dart';

extension _LoginFrameHostPhoneFlow on _LoginFrameHostState {
  Future<void> _resolveEntryState() async {
    final generation = ++_entryResolutionGeneration;
    final storedFuture = ref.read(authSessionStoreProvider).read();
    final socialFuture = _loadSocialMethodAvailability();
    final probeFuture = ref
        .read(oneTapLoginClientProvider)
        .probe()
        .timeout(_LoginFrameHostState._probeTimeout)
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
          : stored.quickLoginRefreshToken.isNotEmpty;
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
          .read(authenticationChallengeCommandWriterProvider)
          .resolveOneTapLoginHint(
            ResolveOneTapLoginHintCommand(
              vendor: probe.vendor,
              carrierToken: probe.carrierToken,
              deviceId: session.installId.isNotEmpty
                  ? session.installId
                  : stored.installId,
              platform: CloudRequestHeaders.platform(),
              appVersion: CloudRequestHeaders.appVersion,
            ),
          )
          .timeout(_LoginFrameHostState._probeTimeout);
      if (!mounted || generation != _entryResolutionGeneration) return;
      _applyCarrierHint(probe, hint);
    } catch (error) {
      if (mounted && generation == _entryResolutionGeneration) {
        final feedback = _loginFeedback(
          error,
          origin: LoginFailureOrigin.oneTap,
        );
        if (feedback.surface == LoginErrorSurface.accountBlocked) {
          _applyTopLevelLoginFailure(
            _presentation,
            error,
            origin: LoginFailureOrigin.oneTap,
            provider: 'one_tap_hint',
          );
          return;
        }
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

  void _applyCarrierHint(OneTapLoginProbe probe, OneTapLoginHint hint) {
    final typedHint = hint.accountHint;
    final accountHint = LoginAccountHint(
      displayName: typedHint?.displayName ?? '',
      avatarUrl: typedHint?.avatarUrl ?? '',
      maskedPhone: typedHint?.maskedPhone ?? '',
      identityOrigin: typedHint?.identityOrigin ?? '',
    );
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
    _updateState(() => _presentation = next);
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
    if (mounted) _updateState(() => _presentation = next);
  }

  void _showAgreementValidation() {
    if (mounted) _updateState(() => _showAgreementError = true);
  }

  void _replaceSocialMethodAvailability(
    Map<String, NativeAuthCapability> availability,
  ) {
    if (mounted) _updateState(() => _socialMethodAvailability = availability);
  }

  void _replaceSocialMethodFeedback(String message) {
    if (mounted && _socialMethodFeedback != message) {
      _updateState(() => _socialMethodFeedback = message);
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
          message: FoundationText.loginSessionExpiredHint,
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
        message: FoundationText.loginSessionExpiredHint,
      ),
    );
  }

  LoginPhoneOtpState get _phoneOtpState =>
      _presentation.phoneOtpState ?? const LoginPhoneOtpState.idle();
  void _setPhoneOtpState(LoginPhoneOtpState state) {
    if (!mounted) {
      return;
    }
    _updateState(() {
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
        message: FoundationText.loginPhoneInvalid,
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
      _updateState(() => _showAgreementError = true);
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
        ? FoundationText.loginOtpRequired
        : FoundationText.loginPhoneInvalid;
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
      _updateState(() => _showAgreementError = true);
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
          .read(authenticationChallengeCommandWriterProvider)
          .sendOtp(
            SendOtpCommand(
              phone: state.phone,
              deviceId: session.installId.isNotEmpty
                  ? session.installId
                  : stored.installId,
              platform: CloudRequestHeaders.platform(),
              appVersion: CloudRequestHeaders.appVersion,
              sourceOperation: 'login',
            ),
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
          .read(accountSessionLoginCommandWriterProvider)
          .loginWithPhone(
            LoginWithPhoneCommand(
              phone: state.phone,
              otpCode: state.code,
              deviceId: session.installId.isNotEmpty
                  ? session.installId
                  : stored.installId,
              platform: CloudRequestHeaders.platform(),
              appVersion: CloudRequestHeaders.appVersion,
              agreementVersion: AuthLegalConfig.agreementVersion,
              privacyVersion: AuthLegalConfig.privacyVersion,
            ),
          );
      if (!_isCurrentLoginAttempt(attempt)) {
        return;
      }
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginGrant(
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
          message: FoundationText.loginRedirecting,
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
      surfaceId: _LoginFrameHostState._loginPageName,
      retryAfterSeconds: afterSeconds < 0 ? 0 : afterSeconds,
      fallbackMessage: fallbackMessage,
    );
  }
}
