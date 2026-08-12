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
    _cancelDeliveryConfirmationTimers();
    unawaited(_otpAutofillGateway.stop());
    unawaited(_clearPendingOtpAttempt());
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
        otpReadinessState: OtpReadinessState.checking,
        phone: phone,
        maskedPhone: phone.isEmpty ? '' : _maskPhone(phone),
        feedback: feedback,
      ),
      action: 'login_state_changed',
    );
    unawaited(_checkOtpDeliveryReadiness());
  }

  void _handlePhoneChanged(String value) {
    if (!_flow.canEditPhone) return;
    final digits = _digitsOnly(value);
    final phone = digits.length > 11 ? digits.substring(0, 11) : digits;
    final changedTarget = phone != _flow.phone;
    final readinessFeedback =
        _flow.otpReadinessState == OtpReadinessState.unavailable &&
            _flow.feedback?.copyKey == 'loginOtpServiceUnavailable'
        ? _flow.feedback
        : null;
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
        otpChallengeState: changedTarget
            ? OtpChallengeState.none
            : _flow.otpChallengeState,
        otpDeliveryState: changedTarget
            ? OtpDeliveryState.none
            : _flow.otpDeliveryState,
        challengeId: changedTarget ? '' : _flow.challengeId,
        deliveryRequestId: changedTarget ? '' : _flow.deliveryRequestId,
        idempotencyKey: changedTarget ? '' : _flow.idempotencyKey,
        resendDeadline: changedTarget ? null : _flow.resendDeadline,
        feedback: readinessFeedback,
      ),
    );
    if (changedTarget) {
      _otpCountdownTicker?.cancel();
      unawaited(_clearPendingOtpAttempt());
    }
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
    if (_flow.isBusy ||
        _flow.otpReadinessState != OtpReadinessState.ready ||
        !_flow.hasValidPhone) {
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

    final requestedAt = DateTime.now();
    final idempotencyKey = newOtpIdempotencyKey();
    final defaultResendDeadline = requestedAt.add(const Duration(seconds: 60));
    final pendingExpiresAt = requestedAt.add(
      _LoginFrameHostState._pendingOtpTtl,
    );
    _flowController.replace(
      _flow.copyWith(
        idempotencyKey: idempotencyKey,
        deliveryRequestId: '',
        challengeId: '',
        otpDeliveryState: OtpDeliveryState.confirming,
        deliveryConfirmationExhausted: false,
        resendDeadline: defaultResendDeadline,
        pendingOtpExpiresAt: pendingExpiresAt,
        feedback: null,
      ),
    );
    await _persistPendingOtpAttempt(_flow);

    final attempt = _beginLoginAttempt(LoginOperation.sendingOtp);
    await _otpAutofillGateway.start((code) {
      if (mounted && _flow.isOtpStep && !_flow.isBusy) {
        _handleOtpChanged(code);
      }
    });
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
              platform: otpClientPlatformForRuntime(
                CloudRequestHeaders.platform(),
              ),
              appVersion: CloudRequestHeaders.appVersion,
              sourceOperation: binding ? 'bind_phone' : 'login',
              bindingTicket: binding ? _flow.bindingTicket : null,
            ),
            idempotencyKey: idempotencyKey,
          )
          .timeout(_LoginFrameHostState._sendOtpTimeout);
      if (!_isCurrentLoginAttempt(attempt)) return;
      final retryAfter = result.retryAfterSeconds;
      final deadline = DateTime.now().add(Duration(seconds: retryAfter));
      _otpController.clear();
      _lastAutoVerifiedCode = '';
      final nextStep = binding ? LoginStep.socialPhoneOtp : LoginStep.otp;
      final deliveryState = _otpDeliveryStateFromWire(result.deliveryStatus);
      _transitionFlow(
        _flow.copyWith(
          step: nextStep,
          operation: LoginOperation.idle,
          otpPurpose: purpose,
          otpChallengeState: OtpChallengeState.active,
          otpDeliveryState: deliveryState,
          code: '',
          challengeId: result.challengeId,
          deliveryRequestId: result.requestId,
          idempotencyKey: idempotencyKey,
          maskedPhone: result.maskedPhone.isNotEmpty
              ? result.maskedPhone
              : _maskPhone(_flow.phone),
          resendDeadline: deadline,
          pendingOtpExpiresAt: pendingExpiresAt,
          feedback: null,
          deliveryConfirmationExhausted: false,
          otpFocusSerial: _flow.otpFocusSerial + 1,
        ),
        action: 'login_state_changed',
      );
      _otpAutofillGateway.bindRequestRef(result.requestId);
      _startCountdownTicker();
      await _persistPendingOtpAttempt(_flow);
      if (deliveryState == OtpDeliveryState.queued) {
        _scheduleDeliveryConfirmations(requestedAt);
      }
      _trackLoginOperation(
        operationId: 'send_otp',
        result: _otpDeliveryTelemetryResult(deliveryState),
        otpPurpose: purpose,
        durationMs: stopwatch.elapsedMilliseconds,
      );
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) return;
      final feedback = _loginFeedback(
        error,
        origin: LoginFailureOrigin.otpSend,
      );
      final runtimeKind = feedback.cloudError?.runtimeFailure.kind;
      final resultUncertain =
          runtimeKind == RuntimeFailureKind.network ||
          runtimeKind == RuntimeFailureKind.timeout ||
          error is TimeoutException ||
          feedback.copyKey == 'loginOtpSendFailed';
      if (resultUncertain) {
        _enterOtpWithUnknownDelivery(
          binding: binding,
          purpose: purpose,
          idempotencyKey: idempotencyKey,
          resendDeadline: defaultResendDeadline,
          pendingExpiresAt: pendingExpiresAt,
          requestedAt: requestedAt,
        );
      } else if (feedback.copyKey == 'loginOtpRateLimited') {
        final seconds = feedback.retryAfterSeconds > 0
            ? feedback.retryAfterSeconds
            : 60;
        _flowController.replace(
          _flow.copyWith(
            operation: LoginOperation.idle,
            otpChallengeState: OtpChallengeState.rateLimited,
            otpDeliveryState: OtpDeliveryState.none,
            resendDeadline: DateTime.now().add(Duration(seconds: seconds)),
            feedback: LoginFeedback(
              message: FoundationText.loginOtpRateLimitedCountdown.replaceFirst(
                '%d',
                seconds.toString(),
              ),
              copyKey: 'loginOtpRateLimited',
              surface: LoginFeedbackSurface.phone,
              recoveryAction: 'waitThenResendOtp',
              cloudError: feedback.cloudError,
              sourceCode: feedback.sourceCode,
              failureKind: feedback.failureKind,
              requestId: feedback.requestId,
              traceId: feedback.traceId,
              retryAfterSeconds: seconds,
            ),
          ),
        );
        unawaited(_clearPendingOtpAttempt());
        _startCountdownTicker();
      } else {
        _flowController.replace(
          _flow.copyWith(
            operation: LoginOperation.idle,
            otpDeliveryState: OtpDeliveryState.none,
            feedback: feedback,
          ),
        );
        unawaited(_clearPendingOtpAttempt());
      }
      final telemetryResult = switch (runtimeKind) {
        RuntimeFailureKind.contract => 'decode_contract_violation',
        _ when feedback.copyKey == 'loginOtpRateLimited' => 'rate_limited',
        _ when resultUncertain => 'delivery_confirming',
        _ => 'failure',
      };
      _trackLoginOperation(
        operationId: 'send_otp',
        result: telemetryResult,
        otpPurpose: purpose,
        durationMs: stopwatch.elapsedMilliseconds,
        error: error,
        feedback: feedback,
      );
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  void _enterOtpWithUnknownDelivery({
    required bool binding,
    required LoginOtpPurpose purpose,
    required String idempotencyKey,
    required DateTime resendDeadline,
    required DateTime pendingExpiresAt,
    required DateTime requestedAt,
  }) {
    _transitionFlow(
      _flow.copyWith(
        step: binding ? LoginStep.socialPhoneOtp : LoginStep.otp,
        operation: LoginOperation.idle,
        otpPurpose: purpose,
        otpChallengeState: OtpChallengeState.active,
        otpDeliveryState: OtpDeliveryState.confirming,
        code: '',
        idempotencyKey: idempotencyKey,
        maskedPhone: _maskPhone(_flow.phone),
        resendDeadline: resendDeadline,
        pendingOtpExpiresAt: pendingExpiresAt,
        feedback: null,
        deliveryConfirmationExhausted: false,
        otpFocusSerial: _flow.otpFocusSerial + 1,
      ),
      action: 'login_state_changed',
      result: 'delivery_confirming',
    );
    _startCountdownTicker();
    unawaited(_persistPendingOtpAttempt(_flow));
    _scheduleDeliveryConfirmations(requestedAt);
  }

  void _scheduleDeliveryConfirmations(DateTime requestedAt) {
    _cancelDeliveryConfirmationTimers();
    _deliveryConfirmationAttempts = 0;
    for (final elapsed in const <Duration>[
      Duration(seconds: 5),
      Duration(seconds: 15),
    ]) {
      final delay = requestedAt.add(elapsed).difference(DateTime.now());
      _deliveryConfirmationTimers.add(
        Timer(delay.isNegative ? Duration.zero : delay, () {
          final finalDeadline = elapsed == const Duration(seconds: 15);
          unawaited(
            _confirmPendingOtpDelivery(
              operationId: finalDeadline
                  ? 'confirm_otp_delivery_15s'
                  : 'confirm_otp_delivery_5s',
              finalDeadline: finalDeadline,
            ),
          );
        }),
      );
    }
  }

  void _cancelDeliveryConfirmationTimers() {
    for (final timer in _deliveryConfirmationTimers) {
      timer.cancel();
    }
    _deliveryConfirmationTimers.clear();
  }

  int? _otpDeliveryElapsedMs(LoginFlowState state, {int minimumMs = 0}) {
    final expiresAt = state.pendingOtpExpiresAt;
    if (expiresAt == null) return null;
    final requestedAt = expiresAt.subtract(_LoginFrameHostState._pendingOtpTtl);
    return DateTime.now()
        .difference(requestedAt)
        .inMilliseconds
        .clamp(minimumMs, 600000);
  }

  Future<void> _confirmPendingOtpDelivery({
    String operationId = 'confirm_otp_delivery',
    bool finalDeadline = false,
  }) async {
    final state = _flow;
    if (!mounted ||
        !state.isOtpStep ||
        (state.otpDeliveryState != OtpDeliveryState.confirming &&
            state.otpDeliveryState != OtpDeliveryState.queued) ||
        state.deliveryConfirmationExhausted ||
        state.idempotencyKey.isEmpty) {
      return;
    }
    if (_deliveryConfirmationAttempts >= 2) {
      if (!finalDeadline) return;
      _flowController.replace(
        _flow.copyWith(
          otpDeliveryState: OtpDeliveryState.confirming,
          deliveryConfirmationExhausted: true,
        ),
      );
      _cancelDeliveryConfirmationTimers();
      _trackLoginOperation(
        operationId: operationId,
        result: 'delivery_confirming',
        durationMs: _otpDeliveryElapsedMs(_flow, minimumMs: 15000),
      );
      await _persistPendingOtpAttempt(_flow);
      return;
    }
    _deliveryConfirmationAttempts += 1;
    final key = state.idempotencyKey;
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      final result = await ref
          .read(authenticationChallengeCommandWriterProvider)
          .sendOtp(
            SendOtpCommand(
              phone: mainlandPhoneE164OrEmpty(state.phone),
              deviceId: session.installId.isNotEmpty
                  ? session.installId
                  : stored.installId,
              platform: otpClientPlatformForRuntime(
                CloudRequestHeaders.platform(),
              ),
              appVersion: CloudRequestHeaders.appVersion,
              sourceOperation: state.isSocialBindingStep
                  ? 'bind_phone'
                  : 'login',
              bindingTicket: state.isSocialBindingStep
                  ? state.bindingTicket
                  : null,
            ),
            idempotencyKey: key,
          )
          .timeout(_LoginFrameHostState._sendOtpTimeout);
      if (!mounted || _flow.idempotencyKey != key) return;
      final deliveryState = _otpDeliveryStateFromWire(result.deliveryStatus);
      _otpAutofillGateway.bindRequestRef(result.requestId);
      final stillPending = deliveryState == OtpDeliveryState.queued;
      final confirmationExhausted = stillPending && finalDeadline;
      _flowController.replace(
        _flow.copyWith(
          otpDeliveryState: confirmationExhausted
              ? OtpDeliveryState.confirming
              : deliveryState,
          challengeId: result.challengeId,
          deliveryRequestId: result.requestId,
          deliveryConfirmationExhausted: confirmationExhausted,
        ),
      );
      if (!stillPending || confirmationExhausted) {
        _cancelDeliveryConfirmationTimers();
      }
      _trackLoginOperation(
        operationId: operationId,
        result: confirmationExhausted
            ? 'delivery_confirming'
            : _otpDeliveryTelemetryResult(deliveryState),
        durationMs: _otpDeliveryElapsedMs(
          _flow,
          minimumMs: finalDeadline ? 15000 : 0,
        ),
      );
      await _persistPendingOtpAttempt(_flow);
    } catch (error) {
      if (!mounted || _flow.idempotencyKey != key) return;
      if (finalDeadline) {
        _flowController.replace(
          _flow.copyWith(
            otpDeliveryState: OtpDeliveryState.confirming,
            deliveryConfirmationExhausted: true,
          ),
        );
        _cancelDeliveryConfirmationTimers();
      }
      _trackLoginOperation(
        operationId: operationId,
        result: 'delivery_confirming',
        durationMs: _otpDeliveryElapsedMs(
          _flow,
          minimumMs: finalDeadline ? 15000 : 0,
        ),
        error: error,
      );
      await _persistPendingOtpAttempt(_flow);
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
    final phoneRateLimited =
        (_flow.step == LoginStep.phoneEntry ||
            _flow.step == LoginStep.socialPhoneEntry) &&
        _flow.otpChallengeState == OtpChallengeState.rateLimited;
    if (!mounted || (!_flow.isOtpStep && !phoneRateLimited)) return;
    final remaining = _flow.remainingResendSeconds(DateTime.now());
    if (remaining <= 0 && phoneRateLimited) {
      _otpCountdownTicker?.cancel();
      _flowController.replace(
        _flow.copyWith(
          otpChallengeState: OtpChallengeState.none,
          resendDeadline: null,
          feedback: null,
        ),
      );
      return;
    }
    if (remaining <= 0 &&
        (_flow.otpChallengeState == OtpChallengeState.active ||
            _flow.otpChallengeState == OtpChallengeState.rateLimited)) {
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
      await _clearPendingOtpAttempt();
      _cancelDeliveryConfirmationTimers();
      await _otpAutofillGateway.stop();
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
    if (feedback.copyKey == 'loginOtpExpired' ||
        feedback.copyKey == 'loginOtpConsumed' ||
        feedback.copyKey == 'loginOtpAttemptsExceeded') {
      next = next.copyWith(
        otpChallengeState: OtpChallengeState.expired,
        resendDeadline: DateTime.now(),
      );
      _cancelDeliveryConfirmationTimers();
      unawaited(_clearPendingOtpAttempt());
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
    _cancelDeliveryConfirmationTimers();
    unawaited(_otpAutofillGateway.stop());
    unawaited(_clearPendingOtpAttempt());
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
          deliveryRequestId: '',
          idempotencyKey: '',
          otpChallengeState: OtpChallengeState.none,
          otpDeliveryState: OtpDeliveryState.none,
          resendDeadline: null,
          pendingOtpExpiresAt: null,
          feedback: null,
          deliveryConfirmationExhausted: false,
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
