part of 'login_page.dart';

extension _LoginPageSocialActions on _LoginFrameHostState {
  void _handleSocialMethod(String method) {
    final capability = _socialMethodAvailability[method];
    if (capability?.isAvailable != true) return;
    if (_flow.isBusy) {
      if (_flow.step != LoginStep.socialAuthorizing ||
          _flow.provider == method) {
        return;
      }
      _cancelActiveAttempt();
      _restoreRoot();
    }
    final intent = switch (method) {
      'wechat' => LoginPendingIntent.socialWechat,
      'qq' => LoginPendingIntent.socialQq,
      'alipay' => LoginPendingIntent.socialAlipay,
      _ => null,
    };
    if (intent != null) unawaited(_runWithConsent(intent));
  }

  Future<Map<String, NativeAuthCapability>>
  _loadSocialMethodAvailability() async {
    final bridge = ref.read(nativeAuthBridgeProvider);
    final platformCapabilities = ref.read(platformCapabilitiesProvider);
    final staticallyAvailable = <NativeAuthProvider, bool>{
      NativeAuthProvider.wechat: platformCapabilities.wechatNativeLogin,
      NativeAuthProvider.alipay: platformCapabilities.alipayNativeLogin,
      NativeAuthProvider.qq: platformCapabilities.qqNativeLogin,
    };
    final capabilities = await Future.wait(
      <NativeAuthProvider>[
        NativeAuthProvider.wechat,
        NativeAuthProvider.qq,
        NativeAuthProvider.alipay,
      ].map((provider) async {
        if (staticallyAvailable[provider] != true) {
          return NativeAuthCapability(
            provider: provider,
            availability: NativeAuthAvailability.unsupportedPlatform,
            reason: 'platform_capability_unavailable',
          );
        }
        try {
          return await bridge
              .getCapability(provider)
              .timeout(_LoginFrameHostState._probeTimeout);
        } on TimeoutException {
          return NativeAuthCapability(
            provider: provider,
            availability: NativeAuthAvailability.probeTimeout,
            reason: 'timeout',
          );
        } catch (_) {
          return NativeAuthCapability(
            provider: provider,
            availability: NativeAuthAvailability.sdkUnavailable,
            reason: 'runtime_failure',
          );
        }
      }),
    );
    return <String, NativeAuthCapability>{
      for (final capability in capabilities)
        capability.provider.name: capability,
    };
  }

  NativeAuthProvider _nativeAuthProviderFor(String method) {
    return switch (method) {
      'wechat' => NativeAuthProvider.wechat,
      'alipay' => NativeAuthProvider.alipay,
      'qq' => NativeAuthProvider.qq,
      _ => throw ArgumentError.value(method, 'method', 'unsupported provider'),
    };
  }

  Future<FederatedLoginOutcome> _socialLoginByMethod(
    String method,
    String authCode,
    String deviceId,
    String platform,
  ) {
    final writer = ref.read(accountSessionLoginCommandWriterProvider);
    return switch (method) {
      'wechat' => writer.loginWithWechat(
        LoginWithWechatCommand(
          wechatCode: authCode,
          deviceId: deviceId,
          platform: platform,
          appVersion: CloudRequestHeaders.appVersion,
          agreementVersion: AuthLegalConfig.agreementVersion,
          privacyVersion: AuthLegalConfig.privacyVersion,
        ),
      ),
      'alipay' => writer.loginWithAlipay(
        LoginWithAlipayCommand(
          alipayAuthCode: authCode,
          deviceId: deviceId,
          platform: platform,
          appVersion: CloudRequestHeaders.appVersion,
          agreementVersion: AuthLegalConfig.agreementVersion,
          privacyVersion: AuthLegalConfig.privacyVersion,
        ),
      ),
      'qq' => writer.loginWithQq(
        LoginWithQqCommand(
          qqAuthCode: authCode,
          deviceId: deviceId,
          platform: platform,
          appVersion: CloudRequestHeaders.appVersion,
          agreementVersion: AuthLegalConfig.agreementVersion,
          privacyVersion: AuthLegalConfig.privacyVersion,
        ),
      ),
      _ => throw ArgumentError.value(method, 'method', 'unsupported provider'),
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

  Future<void> _handleSocialLogin(
    String method, {
    bool consentChecked = false,
  }) async {
    if (_flow.isBusy || _flowController.terminalClaimed) return;
    final capability = _socialMethodAvailability[method];
    if (capability?.isAvailable != true) return;
    if (_flow.consentState != LoginConsentState.accepted && !consentChecked) {
      _handleSocialMethod(method);
      return;
    }
    final attempt = _beginLoginAttempt(LoginOperation.openingProvider);
    final stopwatch = Stopwatch()..start();
    _transitionFlow(
      _flow.copyWith(
        step: LoginStep.socialAuthorizing,
        provider: method,
        operation: LoginOperation.openingProvider,
        entryMode: LoginEntryMode.social,
        feedback: null,
      ),
      action: 'login_social_authorization',
      result: 'started',
    );
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      if (!_isCurrentLoginAttempt(attempt)) return;
      final authorizationPayload = method == 'alipay'
          ? (await ref
                    .read(authenticationChallengeCommandWriterProvider)
                    .createAlipayAuthorizationRequest(
                      CreateAlipayAuthorizationRequestCommand(
                        platform: CloudRequestHeaders.platform(),
                        appVersion: CloudRequestHeaders.appVersion,
                      ),
                    )
                    .timeout(_LoginFrameHostState._requestTimeout))
                .authorizationPayload
          : '';
      if (!_isCurrentLoginAttempt(attempt)) return;
      final ticket = await ref
          .read(nativeAuthBridgeProvider)
          .signIn(
            _nativeAuthProviderFor(method),
            authorizationPayload: authorizationPayload,
          )
          .timeout(_LoginFrameHostState._providerTimeout);
      if (!_isCurrentLoginAttempt(attempt)) return;
      final authCode = ticket.ticket.trim();
      if (authCode.isEmpty) {
        throw StateError('$method authorization ticket is empty');
      }
      _flowController.replace(
        _flow.copyWith(operation: LoginOperation.exchangingTicket),
      );
      final outcome = await _socialLoginByMethod(
        method,
        authCode,
        session.installId.isNotEmpty ? session.installId : stored.installId,
        CloudRequestHeaders.platform(),
      ).timeout(_LoginFrameHostState._requestTimeout);
      if (!_isCurrentLoginAttempt(attempt)) return;
      if (outcome.status == FederatedLoginStatus.authenticated) {
        final grant = outcome.session;
        if (grant == null) {
          throw const FormatException(
            'authenticated social outcome is missing session',
          );
        }
        await ref
            .read(authSessionControllerProvider.notifier)
            .applyRememberedLoginGrant(
              grant,
              rememberedLoginMethod: _rememberedMethodFor(method),
              rememberedLoginMaskedIdentifier: ticket.maskedAccount,
            );
        if (!_isCurrentLoginAttempt(attempt)) return;
        _trackLoginOperation(
          operationId: 'login_social_$method',
          result: 'success',
          provider: method,
          durationMs: stopwatch.elapsedMilliseconds,
        );
        _completeLogin();
        return;
      }
      final bindingTicket = outcome.bindingTicket?.trim() ?? '';
      if (bindingTicket.isEmpty || outcome.expiresInSeconds <= 0) {
        throw const FormatException(
          'phone binding outcome is missing a valid ticket',
        );
      }
      _phoneController.clear();
      _otpController.clear();
      _lastAutoVerifiedCode = '';
      _transitionFlow(
        LoginFlowState(
          step: LoginStep.socialPhoneEntry,
          flowId: _flow.flowId,
          consentState: LoginConsentState.accepted,
          otpPurpose: LoginOtpPurpose.bindPhone,
          entryMode: LoginEntryMode.social,
          provider: method,
          bindingTicket: bindingTicket,
          bindingDeadline: DateTime.now().add(
            Duration(seconds: outcome.expiresInSeconds),
          ),
        ),
        action: 'login_phone_binding',
        result: 'required',
      );
      unawaited(_checkOtpDeliveryReadiness());
      _trackLoginOperation(
        operationId: 'login_social_$method',
        result: 'binding_required',
        provider: method,
        durationMs: stopwatch.elapsedMilliseconds,
      );
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) return;
      final normalized = _normalizeSocialError(error);
      final feedback = _loginFeedback(
        normalized,
        origin: LoginFailureOrigin.social,
      );
      _trackLoginOperation(
        operationId: 'login_social_$method',
        result: feedback.isSilent ? 'cancelled' : 'failure',
        provider: method,
        durationMs: stopwatch.elapsedMilliseconds,
        error: normalized,
        feedback: feedback,
      );
      if (feedback.isSilent) {
        _restoreRoot();
      } else {
        _showSocialFailure(feedback: feedback, provider: method);
      }
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  void _showSocialFailure({LoginFeedback? feedback, String? provider}) {
    final method = provider ?? _flow.provider;
    _transitionFlow(
      _flow.copyWith(
        step: LoginStep.socialFailed,
        operation: LoginOperation.idle,
        provider: method,
        bindingTicket: '',
        bindingDeadline: null,
        feedback:
            feedback ??
            const LoginFeedback(
              message: FoundationText.loginSocialAuthorizationFailed,
              copyKey: 'loginSocialAuthorizationFailed',
              surface: LoginFeedbackSurface.social,
              recoveryAction: 'retryAuthorization',
            ),
      ),
      action: 'login_state_changed',
      result: 'failure',
    );
  }

  Future<void> _retrySocialAuthorization() async {
    final method = _flow.provider;
    if (method.isEmpty) {
      _restoreRoot();
      return;
    }
    await _handleSocialLogin(method, consentChecked: true);
  }

  void _cancelSocialAuthorization() {
    _cancelActiveAttempt();
    _trackLoginFunnel(
      'login_social_authorization',
      result: 'cancelled',
      provider: _flow.provider,
    );
    _restoreRoot();
  }

  void _cancelSocialBindingAndRestoreRoot() {
    _cancelActiveAttempt();
    _otpCountdownTicker?.cancel();
    _phoneController.clear();
    _otpController.clear();
    _trackLoginFunnel(
      'login_phone_binding',
      result: 'cancelled',
      provider: _flow.provider,
      otpPurpose: LoginOtpPurpose.bindPhone,
    );
    _restoreRoot();
  }

  Object _normalizeSocialError(Object error) {
    if (error is PlatformException &&
        error.code.toLowerCase().contains('cancel')) {
      return CloudException(
        type: CloudErrorType.unknown,
        message: 'social authorization cancelled',
        code: UserErrorCode.socialProviderCancelled.code,
        runtimeFailure: RuntimeFailure(
          code: UserErrorCode.socialProviderCancelled.code,
          origin: RuntimeFailureOrigin.user,
          kind: RuntimeFailureKind.cancelled,
          nature: RuntimeFailureNature.permanent,
          location: const RuntimeFailureLocation(
            businessObject: 'user.auth',
            functionModule: 'social_authorization',
          ),
          context: const RuntimeFailureContext(),
        ),
      );
    }
    return error;
  }

  void _trackLoginFunnel(
    String action, {
    required String result,
    LoginStep? fromStep,
    LoginStep? toStep,
    String provider = '',
    LoginOtpPurpose? otpPurpose,
    String? countdownBucket,
    int? durationMs,
  }) {
    final state = _flow;
    unawaited(
      _journeyTracker.trackLoginFunnel(
        action: action,
        flowId: state.flowId,
        step: (toStep ?? state.step).name,
        result: result,
        entryMode: state.entryMode.name,
        fromStep: fromStep?.name,
        toStep: toStep?.name,
        provider: provider.isEmpty ? state.provider : provider,
        otpPurpose: (otpPurpose ?? state.otpPurpose).name,
        consentState: state.consentState.name,
        durationMs: durationMs,
        attemptIndex: state.attemptIndex,
        countdownBucket: countdownBucket,
        motionReduced: mounted
            ? MediaQuery.maybeOf(context)?.disableAnimations ?? false
            : false,
        dismissPolicy: widget.dismissPolicy.name,
        pageName: _LoginFrameHostState._loginPageName,
      ),
    );
  }

  void _trackLoginOperation({
    required String operationId,
    required String result,
    String provider = '',
    LoginOtpPurpose? otpPurpose,
    int? durationMs,
    Object? error,
    LoginFeedback? feedback,
  }) {
    final state = _flow;
    unawaited(
      _journeyTracker.trackLoginOperation(
        operationId: operationId,
        surfaceId: 'login',
        result: result,
        flowId: state.flowId,
        step: state.step.name,
        provider: provider.isEmpty ? state.provider : provider,
        otpPurpose: (otpPurpose ?? state.otpPurpose).name,
        durationMs: durationMs,
        attemptIndex: state.attemptIndex,
        failReasonCode: feedback?.sourceCode,
        failureKind: feedback?.failureKind,
        recoveryAction: feedback?.recoveryAction,
        copyKey: feedback?.copyKey,
        feedbackSurface: feedback?.surface.name,
        requestId: feedback?.requestId,
        traceId: feedback?.traceId,
        error: error,
        pageName: _LoginFrameHostState._loginPageName,
      ),
    );
  }
}
