part of 'login_page.dart';

extension _LoginPageSocialActions on _LoginFrameHostState {
  void _handleOtherMethod(String method) {
    _trackLoginEvent(
      'login_method_clicked',
      targetKey: method,
      payload: <String, dynamic>{'state': _presentation.kind.name},
    );
    if (method == 'phone') {
      _setSocialMethodFeedback('');
      _enterPhoneOtp();
      return;
    }
    if (method == 'wechat' || method == 'alipay' || method == 'qq') {
      unawaited(_handleSocialLogin(method));
      return;
    }
    _replacePresentation(
      LoginEntryPresentation(
        kind: _presentation.kind,
        accountHint: _presentation.accountHint,
        carrierHint: _presentation.carrierHint,
        phoneOtpState: _presentation.phoneOtpState,
        message: FoundationText.loginQuickLoginUnavailableHint,
        primaryAction: _presentation.primaryAction,
        primaryProvider: _presentation.primaryProvider,
        quickLoginPhone: _presentation.quickLoginPhone,
      ),
    );
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
        NativeAuthProvider.alipay,
        NativeAuthProvider.qq,
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
          _trackLoginEvent(
            'login_social_capability_unavailable',
            targetKey: provider.name,
            payload: const <String, dynamic>{'reason': 'timeout'},
          );
          return NativeAuthCapability(
            provider: provider,
            availability: NativeAuthAvailability.probeTimeout,
            reason: 'timeout',
          );
        } catch (error) {
          _trackLoginEvent(
            'login_social_capability_unavailable',
            targetKey: provider.name,
            payload: <String, dynamic>{
              'reason': 'runtime_failure',
              'errorType': error.runtimeType.toString(),
            },
          );
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

  String _socialMethodForRemembered(AuthRememberedLoginMethod method) {
    return switch (method) {
      AuthRememberedLoginMethod.wechat => 'wechat',
      AuthRememberedLoginMethod.qq => 'qq',
      AuthRememberedLoginMethod.alipay => 'alipay',
      _ => '',
    };
  }

  void _setSocialMethodFeedback(String message) {
    _replaceSocialMethodFeedback(message);
  }

  String _socialCapabilityMessage(NativeAuthAvailability availability) {
    return switch (availability) {
      NativeAuthAvailability.notConfigured =>
        FoundationText.loginSocialNotConfigured,
      NativeAuthAvailability.clientNotInstalled =>
        FoundationText.loginSocialClientNotInstalled,
      NativeAuthAvailability.probeTimeout =>
        FoundationText.loginSocialProbeTimeout,
      NativeAuthAvailability.sdkUnavailable =>
        FoundationText.loginSocialSdkUnavailable,
      NativeAuthAvailability.unsupportedPlatform ||
      NativeAuthAvailability.available => '',
    };
  }

  NativeAuthProvider _nativeAuthProviderFor(String method) {
    return switch (method) {
      'wechat' => NativeAuthProvider.wechat,
      'alipay' => NativeAuthProvider.alipay,
      'qq' => NativeAuthProvider.qq,
      _ => throw ArgumentError.value(method, 'method', 'not a social provider'),
    };
  }

  Future<AuthSessionGrant> _socialLoginByMethod(
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
        ),
      ),
      'alipay' => writer.loginWithAlipay(
        LoginWithAlipayCommand(
          alipayAuthCode: authCode,
          deviceId: deviceId,
          platform: platform,
          appVersion: CloudRequestHeaders.appVersion,
        ),
      ),
      'qq' => writer.loginWithQq(
        LoginWithQqCommand(
          qqAuthCode: authCode,
          deviceId: deviceId,
          platform: platform,
          appVersion: CloudRequestHeaders.appVersion,
        ),
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

  Future<void> _handleSocialLogin(String method) async {
    if (_presentation.kind == LoginEntryKind.submitting) {
      return;
    }
    final capability = _socialMethodAvailability[method];
    if (capability == null || !capability.isAvailable) {
      final message = capability == null
          ? FoundationText.loginSocialProbeTimeout
          : _socialCapabilityMessage(capability.availability);
      _setSocialMethodFeedback(message);
      _trackLoginEvent(
        'login_social_capability_unavailable',
        targetKey: method,
        payload: <String, dynamic>{
          'reason': capability?.availability.name ?? 'resolving',
        },
      );
      return;
    }
    _setSocialMethodFeedback('');
    if (!_agreementAccepted) {
      _showAgreementValidation();
      return;
    }
    _invalidateEntryResolution();
    final attempt = _beginLoginAttempt();
    final latency = Stopwatch()..start();
    final entryBeforeSubmit = _presentation;
    _replacePresentation(
      LoginEntryPresentation(
        kind: LoginEntryKind.submitting,
        accountHint: entryBeforeSubmit.accountHint,
        carrierHint: entryBeforeSubmit.carrierHint,
        phoneOtpState: entryBeforeSubmit.phoneOtpState,
        primaryAction: entryBeforeSubmit.primaryAction,
        primaryProvider: entryBeforeSubmit.primaryProvider,
        quickLoginPhone: entryBeforeSubmit.quickLoginPhone,
      ),
    );
    try {
      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      final deviceId = session.installId.isNotEmpty
          ? session.installId
          : stored.installId;
      final bridge = ref.read(nativeAuthBridgeProvider);
      final authorizationPayload = method == 'alipay'
          ? (await ref
                    .read(authenticationChallengeCommandWriterProvider)
                    .createAlipayAuthorizationRequest(
                      CreateAlipayAuthorizationRequestCommand(
                        platform: CloudRequestHeaders.platform(),
                        appVersion: CloudRequestHeaders.appVersion,
                      ),
                    ))
                .authorizationPayload
          : '';
      final ticket = await bridge.signIn(
        _nativeAuthProviderFor(method),
        authorizationPayload: authorizationPayload,
      );
      if (!mounted || _activeAttempt != attempt) {
        return;
      }
      if (ticket.ticket.trim().isEmpty) {
        throw StateError('$method authorization ticket is empty');
      }
      final result = await _socialLoginByMethod(
        method,
        ticket.ticket.trim(),
        deviceId,
        CloudRequestHeaders.platform(),
      );
      if (!mounted || _activeAttempt != attempt) {
        return;
      }
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginGrant(
            result,
            rememberedLoginMethod: _rememberedMethodFor(method),
            rememberedLoginMaskedIdentifier: ticket.maskedAccount,
          );
      _trackLoginEvent(
        'login_success',
        targetKey: method,
        payload: <String, dynamic>{
          'state': entryBeforeSubmit.kind.name,
          'durationMs': latency.elapsedMilliseconds,
        },
      );
      _completeLogin();
    } catch (error) {
      if (!mounted || _activeAttempt != attempt) {
        return;
      }
      final normalizedError = _normalizeSocialError(error);
      final feedback = _loginFeedback(
        normalizedError,
        origin: LoginFailureOrigin.social,
      );
      if (feedback.isSilent) {
        _replacePresentation(entryBeforeSubmit);
        _trackLoginEvent(
          'login_social_cancelled',
          targetKey: method,
          payload: <String, dynamic>{
            ...feedback.telemetry,
            'durationMs': latency.elapsedMilliseconds,
          },
        );
        return;
      }
      _setSocialMethodFeedback(feedback.message);
      _applyTopLevelLoginFailure(
        entryBeforeSubmit,
        normalizedError,
        fallbackMessage: UserErrorCode.socialProviderUnavailable.defaultMessage,
        preserveEntry: true,
        origin: LoginFailureOrigin.social,
        provider: method,
        durationMs: latency.elapsedMilliseconds,
      );
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  Object _normalizeSocialError(Object error) {
    if (error is PlatformException) {
      final code = error.code.toLowerCase();
      if (code.contains('cancel')) {
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
    }
    return error;
  }

  void _trackLoginEvent(
    String action, {
    String targetKey = '',
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) {
    final platform = ref.read(platformTelemetryNameProvider);
    unawaited(
      _journeyTracker.trackAction(
        journey: _LoginFrameHostState._loginJourney,
        action: action,
        pageName: _LoginFrameHostState._loginPageName,
        targetType: 'login',
        targetKey: targetKey,
        payload: buildLoginTelemetryPayload(
          environment: CloudRuntimeConfig.appRuntimeEnv,
          platform: platform,
          action: action,
          provider: targetKey,
          raw: payload,
        ),
      ),
    );
  }
}
