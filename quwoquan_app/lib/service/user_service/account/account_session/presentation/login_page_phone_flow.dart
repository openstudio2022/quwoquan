part of 'login_page.dart';

extension _LoginFrameHostPhoneFlow on _LoginFrameHostState {
  Future<void> _resolveEntryState() async {
    final generation = ++_entryResolutionGeneration;
    if (_isAccountSuspensionEntry) {
      _transitionFlow(
        _flow.copyWith(
          step: LoginStep.blocked,
          operation: LoginOperation.idle,
          feedback: accountSuspensionLoginFeedback(
            locale: Localizations.localeOf(context).languageCode,
          ),
        ),
        action: 'login_state_changed',
        result: 'account_suspended',
      );
      return;
    }
    final socialFuture = _loadSocialMethodAvailability();
    unawaited(
      socialFuture.then((availability) {
        if (!mounted || generation != _entryResolutionGeneration) return;
        _socialMethodAvailability = availability;
        _flowController.refresh();
      }),
    );

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

    try {
      final stored = await ref.read(authSessionStoreProvider).read();
      if (!mounted || generation != _entryResolutionGeneration) return;
      _quickLoginRefreshToken = stored.quickLoginRefreshToken;
      _rememberedPhone = _validFullPhoneOrEmpty(
        stored.rememberedLoginIdentifier,
      );
      final capabilities = ref.read(platformCapabilitiesProvider);
      final hasQuickLogin = capabilities.quickLoginPersistence
          ? stored.hasValidQuickLoginCredential
          : _quickLoginRefreshToken.isNotEmpty;
      final masked = stored.rememberedLoginMaskedIdentifier.trim();
      if (hasQuickLogin && masked.isNotEmpty) {
        _rootStep = LoginStep.oneTap;
        _rootEntryMode = LoginEntryMode.rememberedSession;
        _rootMaskedPhone = masked;
        _transitionFlow(
          _flow.copyWith(
            step: LoginStep.oneTap,
            entryMode: LoginEntryMode.rememberedSession,
            maskedPhone: masked,
            operation: LoginOperation.idle,
            feedback: null,
          ),
          action: 'login_state_changed',
        );
        return;
      }

      final probe = await probeFuture;
      if (!mounted || generation != _entryResolutionGeneration) return;
      _probe = probe;
      if (!probe.canOfferLogin) {
        _enterPhoneEntry();
        return;
      }
      final session = ref.read(authSessionControllerProvider);
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
      _rootStep = LoginStep.oneTap;
      _rootEntryMode = LoginEntryMode.carrier;
      _rootMaskedPhone = hint.maskedPhone.isNotEmpty
          ? hint.maskedPhone
          : probe.maskedPhone;
      _transitionFlow(
        _flow.copyWith(
          step: LoginStep.oneTap,
          entryMode: LoginEntryMode.carrier,
          maskedPhone: _rootMaskedPhone,
          operation: LoginOperation.idle,
          feedback: null,
        ),
        action: 'login_state_changed',
      );
    } catch (error) {
      if (!mounted || generation != _entryResolutionGeneration) return;
      _trackLoginOperation(
        operationId: 'resolve_login_entry',
        result: 'failure',
        error: error,
      );
      _enterPhoneEntry();
    }
  }

  void _transitionFlow(
    LoginFlowState next, {
    required String action,
    String result = 'success',
  }) {
    if (!mounted || _flowController.terminalClaimed) return;
    final previous = _flow;
    final durationMs = _stateDwellStopwatch.elapsedMilliseconds;
    _stateDwellStopwatch.reset();
    _flowController.replace(next);
    _armStateDwellWatchdog();
    _trackLoginFunnel(
      action,
      result: result,
      fromStep: previous.step,
      toStep: next.step,
      durationMs: durationMs,
    );
  }

  void _armStateDwellWatchdog() {
    _stateDwellWatchdog?.cancel();
    final observedStep = _flow.step;
    _stateDwellWatchdog = Timer(_LoginFrameHostState._stateDwellThreshold, () {
      if (!mounted ||
          _flowController.terminalClaimed ||
          _flow.step != observedStep) {
        return;
      }
      final elapsedMs = _stateDwellStopwatch.elapsedMilliseconds;
      final thresholdMs =
          _LoginFrameHostState._stateDwellThreshold.inMilliseconds;
      _trackLoginFunnel(
        'login_state_changed',
        result: 'stalled',
        fromStep: observedStep,
        toStep: observedStep,
        // Timer firing is the authoritative threshold crossing. Fake-time
        // widget tests do not advance Stopwatch, so preserve the real lower
        // bound instead of reporting a misleading sub-threshold duration.
        durationMs: elapsedMs < thresholdMs ? thresholdMs : elapsedMs,
      );
    });
  }

  int _beginLoginAttempt(LoginOperation operation) {
    final attempt = ++_attemptSerial;
    _activeAttempt = attempt;
    _flowController.replace(
      _flow.copyWith(
        operation: operation,
        attemptIndex: attempt,
        feedback: null,
      ),
    );
    return attempt;
  }

  bool _isCurrentLoginAttempt(int attempt) =>
      mounted && !_flowController.terminalClaimed && _activeAttempt == attempt;

  void _finishLoginAttempt(int attempt) {
    if (_activeAttempt != attempt) return;
    _activeAttempt = null;
    if (mounted && !_flowController.terminalClaimed && _flow.isBusy) {
      _flowController.replace(_flow.copyWith(operation: LoginOperation.idle));
    }
  }

  void _cancelActiveAttempt() {
    _activeAttempt = null;
    _attemptSerial += 1;
    if (mounted && _flow.isBusy) {
      _flowController.replace(_flow.copyWith(operation: LoginOperation.idle));
    }
  }

  void _enterPhoneEntry({
    LoginFeedback? feedback,
    bool preservePhone = true,
    bool preserveRoot = false,
  }) {
    _entryResolutionGeneration += 1;
    _cancelActiveAttempt();
    if (!preserveRoot) {
      _rootStep = LoginStep.phoneEntry;
      _rootEntryMode = LoginEntryMode.phone;
      _rootMaskedPhone = '';
    }
    _otpCountdownTicker?.cancel();
    _lastAutoVerifiedCode = '';
    _otpController.clear();
    if (!preservePhone) {
      _phoneController.clear();
    }
    final phone = preservePhone
        ? _validFullPhoneOrEmpty(
            _phoneController.text.isNotEmpty
                ? _phoneController.text
                : _rememberedPhone,
          )
        : '';
    if (_phoneController.text != phone) {
      _phoneController.value = TextEditingValue(
        text: phone,
        selection: TextSelection.collapsed(offset: phone.length),
      );
    }
    _transitionFlow(
      LoginFlowState(
        step: LoginStep.phoneEntry,
        flowId: _flow.flowId,
        consentState: _flow.consentState,
        entryMode: LoginEntryMode.phone,
        phone: phone,
        maskedPhone: phone.isEmpty ? '' : _maskPhone(phone),
        feedback: feedback,
      ),
      action: 'login_state_changed',
    );
  }

  void _handlePhoneChanged(String value) {
    if (!_flow.canEditPhone) return;
    final digits = _digitsOnly(value);
    final phone = digits.length > 11 ? digits.substring(0, 11) : digits;
    if (_phoneController.text != phone) {
      _phoneController.value = TextEditingValue(
        text: phone,
        selection: TextSelection.collapsed(offset: phone.length),
      );
    }
    _flowController.replace(
      _flow.copyWith(
        phone: phone,
        maskedPhone: phone.length == 11 ? _maskPhone(phone) : '',
        feedback: null,
      ),
    );
  }

  void _handlePhoneEditingComplete() {
    if (_flow.phone.isEmpty || _flow.hasValidPhone) return;
    _flowController.replace(
      _flow.copyWith(
        feedback: const LoginFeedback(
          message: FoundationText.loginPhoneInvalid,
          copyKey: 'loginPhoneInvalid',
          surface: LoginFeedbackSurface.phone,
          recoveryAction: 'editPhone',
        ),
      ),
    );
  }

  Future<void> _requestOtp({
    bool resend = false,
    bool consentChecked = false,
  }) async {
    if (_flow.isBusy || !_flow.hasValidPhone) {
      _handlePhoneEditingComplete();
      return;
    }
    final binding = _flow.isSocialBindingStep;
    if (!binding &&
        _flow.consentState != LoginConsentState.accepted &&
        !consentChecked) {
      await _runWithConsent(
        resend ? LoginPendingIntent.resendOtp : LoginPendingIntent.sendOtp,
      );
      return;
    }
    if (resend && _flow.remainingResendSeconds(DateTime.now()) > 0) return;
    if (binding &&
        (_flow.bindingTicket.isEmpty ||
            (_flow.bindingDeadline?.isBefore(DateTime.now()) ?? false))) {
      _showSocialFailure();
      return;
    }

    final attempt = _beginLoginAttempt(LoginOperation.sendingOtp);
    final stopwatch = Stopwatch()..start();
    final purpose = binding ? LoginOtpPurpose.bindPhone : LoginOtpPurpose.login;
    final wirePhone = mainlandPhoneE164OrEmpty(_flow.phone);
    _trackLoginFunnel('login_otp_send', result: 'started', otpPurpose: purpose);
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      if (!_isCurrentLoginAttempt(attempt)) return;
      final result = await ref
          .read(authenticationChallengeCommandWriterProvider)
          .sendOtp(
            SendOtpCommand(
              phone: wirePhone,
              deviceId: session.installId.isNotEmpty
                  ? session.installId
                  : stored.installId,
              platform: CloudRequestHeaders.platform(),
              appVersion: CloudRequestHeaders.appVersion,
              sourceOperation: binding ? 'bind_phone' : 'login',
              bindingTicket: binding ? _flow.bindingTicket : null,
            ),
          )
          .timeout(_LoginFrameHostState._requestTimeout);
      if (!_isCurrentLoginAttempt(attempt)) return;
      final retryAfter = result.retryAfterSeconds > 0
          ? result.retryAfterSeconds
          : 60;
      final deadline = DateTime.now().add(Duration(seconds: retryAfter));
      _otpController.clear();
      _lastAutoVerifiedCode = '';
      final nextStep = binding ? LoginStep.socialPhoneOtp : LoginStep.otp;
      _transitionFlow(
        _flow.copyWith(
          step: nextStep,
          operation: LoginOperation.idle,
          otpPurpose: purpose,
          otpChallengeState: OtpChallengeState.active,
          code: '',
          challengeId: result.challengeId ?? '',
          maskedPhone: result.maskedPhone.isNotEmpty
              ? result.maskedPhone
              : _maskPhone(_flow.phone),
          resendDeadline: deadline,
          feedback: null,
          otpFocusSerial: _flow.otpFocusSerial + 1,
        ),
        action: 'login_state_changed',
      );
      _startCountdownTicker();
      _trackLoginOperation(
        operationId: 'send_otp',
        result: 'success',
        otpPurpose: purpose,
        durationMs: stopwatch.elapsedMilliseconds,
      );
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) return;
      final feedback = _loginFeedback(
        error,
        origin: LoginFailureOrigin.otpSend,
      );
      _flowController.replace(
        _flow.copyWith(operation: LoginOperation.idle, feedback: feedback),
      );
      _trackLoginOperation(
        operationId: 'send_otp',
        result: 'failure',
        otpPurpose: purpose,
        durationMs: stopwatch.elapsedMilliseconds,
        error: error,
        feedback: feedback,
      );
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  void _startCountdownTicker() {
    _otpCountdownTicker?.cancel();
    _refreshCountdownFromDeadline();
    if (_flow.remainingResendSeconds(DateTime.now()) <= 0) return;
    _otpCountdownTicker = Timer.periodic(const Duration(seconds: 1), (_) {
      _refreshCountdownFromDeadline();
    });
  }

  void _refreshCountdownFromDeadline({bool trackResume = false}) {
    if (!mounted || !_flow.isOtpStep) return;
    final remaining = _flow.remainingResendSeconds(DateTime.now());
    if (remaining <= 0 && _flow.otpChallengeState == OtpChallengeState.active) {
      _otpCountdownTicker?.cancel();
      _flowController.replace(
        _flow.copyWith(otpChallengeState: OtpChallengeState.resendAvailable),
      );
      _trackLoginFunnel(
        'login_otp_resend_available',
        result: 'available',
        otpPurpose: _flow.otpPurpose,
      );
      return;
    }
    _flowController.refresh();
    if (trackResume) {
      _trackLoginFunnel(
        'login_otp_countdown_recalculated',
        result: 'resumed',
        otpPurpose: _flow.otpPurpose,
        countdownBucket: remaining > 30
            ? '31_60'
            : remaining > 0
            ? '1_30'
            : 'ready',
      );
    }
  }

  void _handleOtpChanged(String value) {
    if (!_flow.canEditOtp) return;
    final digits = _digitsOnly(value);
    final code = digits.length > 6 ? digits.substring(0, 6) : digits;
    if (_otpController.text != code) {
      _otpController.value = TextEditingValue(
        text: code,
        selection: TextSelection.collapsed(offset: code.length),
      );
    }
    _flowController.replace(_flow.copyWith(code: code, feedback: null));
    if (code.length != 6 || code == _lastAutoVerifiedCode) return;
    _lastAutoVerifiedCode = code;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _flow.code == code && !_flow.isBusy) {
        unawaited(_verifyOtp());
      }
    });
  }

  Future<void> _verifyOtp() async {
    final state = _flow;
    if (!state.isOtpStep || state.isBusy || state.code.length != 6) return;
    final binding = state.step == LoginStep.socialPhoneOtp;
    final operation = binding
        ? LoginOperation.completingBinding
        : LoginOperation.verifyingOtp;
    final attempt = _beginLoginAttempt(operation);
    final stopwatch = Stopwatch()..start();
    _trackLoginFunnel(
      binding ? 'login_phone_binding' : 'login_otp_verify',
      result: 'started',
      otpPurpose: state.otpPurpose,
    );
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      final wirePhone = mainlandPhoneE164OrEmpty(state.phone);
      if (!_isCurrentLoginAttempt(attempt)) return;
      late final AuthSessionGrant grant;
      if (binding) {
        grant = await ref
            .read(appCredentialBindingCommandWriterProvider)
            .completeFederatedPhoneBinding(
              CompleteFederatedPhoneBindingCommand(
                bindingTicket: state.bindingTicket,
                phone: wirePhone,
                otpCode: state.code,
                challengeId: state.challengeId,
                deviceId: session.installId.isNotEmpty
                    ? session.installId
                    : stored.installId,
                platform: CloudRequestHeaders.platform(),
                appVersion: CloudRequestHeaders.appVersion,
                agreementVersion: AuthLegalConfig.agreementVersion,
                privacyVersion: AuthLegalConfig.privacyVersion,
              ),
            )
            .timeout(_LoginFrameHostState._requestTimeout);
      } else {
        grant = await ref
            .read(accountSessionLoginCommandWriterProvider)
            .loginWithPhone(
              LoginWithPhoneCommand(
                phone: wirePhone,
                otpCode: state.code,
                deviceId: session.installId.isNotEmpty
                    ? session.installId
                    : stored.installId,
                platform: CloudRequestHeaders.platform(),
                appVersion: CloudRequestHeaders.appVersion,
                agreementVersion: AuthLegalConfig.agreementVersion,
                privacyVersion: AuthLegalConfig.privacyVersion,
              ),
            )
            .timeout(_LoginFrameHostState._requestTimeout);
      }
      if (!_isCurrentLoginAttempt(attempt)) return;
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginGrant(
            grant,
            rememberedLoginMethod: binding
                ? _rememberedMethodFor(state.provider)
                : AuthRememberedLoginMethod.phoneOtp,
            rememberedLoginMaskedIdentifier: _maskPhone(state.phone),
            rememberedLoginIdentifier: binding ? '' : state.phone,
          );
      if (!_isCurrentLoginAttempt(attempt)) return;
      TextInput.finishAutofillContext();
      _trackLoginOperation(
        operationId: binding
            ? 'complete_federated_phone_binding'
            : 'verify_login_otp',
        result: 'success',
        otpPurpose: state.otpPurpose,
        durationMs: stopwatch.elapsedMilliseconds,
      );
      _completeLogin();
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) return;
      final feedback = _loginFeedback(
        error,
        origin: binding
            ? LoginFailureOrigin.phoneBinding
            : LoginFailureOrigin.otpVerify,
      );
      _applyOtpFailure(feedback);
      _trackLoginOperation(
        operationId: binding
            ? 'complete_federated_phone_binding'
            : 'verify_login_otp',
        result: 'failure',
        otpPurpose: state.otpPurpose,
        durationMs: stopwatch.elapsedMilliseconds,
        error: error,
        feedback: feedback,
      );
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  void _applyOtpFailure(LoginFeedback feedback) {
    if (feedback.blocksAccountLogin) {
      _otpCountdownTicker?.cancel();
      _transitionFlow(
        _flow.copyWith(
          step: LoginStep.blocked,
          operation: LoginOperation.idle,
          code: '',
          challengeId: '',
          otpChallengeState: OtpChallengeState.none,
          resendDeadline: null,
          feedback: feedback,
        ),
        action: 'login_state_changed',
        result: 'blocked',
      );
      return;
    }
    var next = _flow.copyWith(
      operation: LoginOperation.idle,
      feedback: feedback,
    );
    if (feedback.clearOtp) {
      _otpController.clear();
      _lastAutoVerifiedCode = '';
      next = next.copyWith(
        code: '',
        otpFocusSerial: next.otpFocusSerial + 1,
        otpShakeSerial: feedback.shakeOtp
            ? next.otpShakeSerial + 1
            : next.otpShakeSerial,
      );
    }
    var restartCountdown = false;
    if (feedback.copyKey == 'loginOtpExpired') {
      next = next.copyWith(
        otpChallengeState: OtpChallengeState.expired,
        resendDeadline: DateTime.now(),
      );
    } else if (feedback.copyKey == 'loginOtpRateLimited') {
      final seconds = feedback.retryAfterSeconds > 0
          ? feedback.retryAfterSeconds
          : 60;
      next = next.copyWith(
        otpChallengeState: OtpChallengeState.rateLimited,
        resendDeadline: DateTime.now().add(Duration(seconds: seconds)),
      );
      restartCountdown = true;
    } else if (feedback.copyKey == 'loginPhoneCredentialConflict') {
      _otpCountdownTicker?.cancel();
      next = next.copyWith(
        step: LoginStep.socialPhoneEntry,
        otpChallengeState: OtpChallengeState.none,
        challengeId: '',
        resendDeadline: null,
      );
    }
    _flowController.replace(next);
    if (restartCountdown) _startCountdownTicker();
  }

  void _changePhone() {
    _cancelActiveAttempt();
    _otpCountdownTicker?.cancel();
    _phoneController.clear();
    _otpController.clear();
    _lastAutoVerifiedCode = '';
    if (_flow.isSocialBindingStep) {
      _transitionFlow(
        _flow.copyWith(
          step: LoginStep.socialPhoneEntry,
          operation: LoginOperation.idle,
          phone: '',
          maskedPhone: '',
          code: '',
          challengeId: '',
          otpChallengeState: OtpChallengeState.none,
          resendDeadline: null,
          feedback: null,
        ),
        action: 'login_state_changed',
      );
      return;
    }
    _enterPhoneEntry(preservePhone: false);
  }

  LoginFeedback _loginFeedback(
    Object error, {
    required LoginFailureOrigin origin,
  }) {
    final cloudError = error is CloudException
        ? error
        : CloudErrorMapper.fromException(error);
    return loginFeedbackForError(
      cloudError,
      origin: origin,
      locale: Localizations.localeOf(context).languageCode,
    );
  }
}
