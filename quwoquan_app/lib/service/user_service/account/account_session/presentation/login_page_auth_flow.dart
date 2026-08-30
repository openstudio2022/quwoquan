part of 'login_page.dart';

extension _LoginFrameHostAuthFlow on _LoginFrameHostState {
  void _toggleAgreement() {
    if (_flow.isBusy || _consentSheetVisible) return;
    final next = _flow.consentState == LoginConsentState.accepted
        ? LoginConsentState.unchecked
        : LoginConsentState.accepted;
    _flowController.replace(_flow.copyWith(consentState: next, feedback: null));
    _trackLoginFunnel(
      'login_consent_changed',
      result: next == LoginConsentState.accepted ? 'accepted' : 'unchecked',
    );
  }

  Future<void> _runWithConsent(LoginPendingIntent intent) async {
    if (_flowController.terminalClaimed || _flow.isBusy) return;
    if (_flow.consentState == LoginConsentState.accepted) {
      await _dispatchPendingIntent(intent);
      return;
    }
    _pendingConsentIntent = intent;
    if (_consentSheetVisible) return;
    _consentSheetVisible = true;
    _flowController.replace(
      _flow.copyWith(consentState: LoginConsentState.confirming),
    );
    _trackLoginFunnel('login_consent_sheet', result: 'shown');
    final accepted = await showLoginConsentSheet(
      context,
      onAgreementTap: () => context.push(AppRoutePaths.legalUserAgreement),
      onPrivacyTap: () => context.push(AppRoutePaths.legalPrivacyPolicy),
    );
    _consentSheetVisible = false;
    if (!mounted || _flowController.terminalClaimed) return;
    final pending = _pendingConsentIntent;
    _pendingConsentIntent = null;
    if (accepted != true) {
      _flowController.replace(
        _flow.copyWith(consentState: LoginConsentState.unchecked),
      );
      _trackLoginFunnel('login_consent_sheet', result: 'cancelled');
      return;
    }
    _flowController.replace(
      _flow.copyWith(consentState: LoginConsentState.accepted, feedback: null),
    );
    _trackLoginFunnel('login_consent_sheet', result: 'accepted');
    if (pending != null) await _dispatchPendingIntent(pending);
  }

  Future<void> _dispatchPendingIntent(LoginPendingIntent intent) async {
    switch (intent) {
      case LoginPendingIntent.oneTap:
        await _handleOneTapLogin();
      case LoginPendingIntent.sendOtp:
        await _requestOtp(consentChecked: true);
      case LoginPendingIntent.resendOtp:
        await _requestOtp(resend: true, consentChecked: true);
      case LoginPendingIntent.socialWechat:
        await _handleSocialLogin('wechat', consentChecked: true);
      case LoginPendingIntent.socialQq:
        await _handleSocialLogin('qq', consentChecked: true);
      case LoginPendingIntent.socialAlipay:
        await _handleSocialLogin('alipay', consentChecked: true);
    }
  }

  Future<void> _handleOneTapLogin() async {
    if (_flow.step != LoginStep.oneTap || _flow.isBusy) return;
    final attempt = _beginLoginAttempt(LoginOperation.exchangingTicket);
    final stopwatch = Stopwatch()..start();
    _trackLoginFunnel('login_action_clicked', result: 'started');
    try {
      if (_flow.entryMode == LoginEntryMode.rememberedSession &&
          _quickLoginRefreshToken.isNotEmpty) {
        final result = await ref
            .read(accountSessionLifecycleCommandWriterProvider)
            .refreshToken(
              RefreshTokenCommand(refreshToken: _quickLoginRefreshToken),
            )
            .timeout(_LoginFrameHostState._requestTimeout);
        if (!_isCurrentLoginAttempt(attempt)) return;
        await ref
            .read(authSessionControllerProvider.notifier)
            .applyRefreshGrant(result);
        if (!_isCurrentLoginAttempt(attempt)) return;
        _trackLoginOperation(
          operationId: 'refresh_remembered_session',
          result: 'success',
          durationMs: stopwatch.elapsedMilliseconds,
        );
        _completeLogin();
        return;
      }

      final session = ref.read(authSessionControllerProvider);
      final stored = await ref.read(authSessionStoreProvider).read();
      if (!_isCurrentLoginAttempt(attempt)) return;
      var vendor = _probe?.vendor ?? '';
      var carrierToken = _probe?.carrierToken ?? '';
      if (_probe?.canOfferLogin != true) {
        final fresh = await ref
            .read(oneTapLoginClientProvider)
            .requestLoginToken()
            .timeout(_LoginFrameHostState._probeTimeout);
        vendor = fresh.vendor;
        carrierToken = fresh.carrierToken;
      }
      Future<AuthSessionGrant> submit({
        required String vendor,
        required String carrierToken,
      }) {
        return ref
            .read(accountSessionLoginCommandWriterProvider)
            .loginOneTap(
              LoginOneTapCommand(
                vendor: vendor,
                carrierToken: carrierToken,
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

      late AuthSessionGrant grant;
      try {
        grant = await submit(vendor: vendor, carrierToken: carrierToken);
      } on CloudException catch (error) {
        if (error.code != UserErrorCode.carrierTokenInvalid.code) rethrow;
        final fresh = await ref
            .read(oneTapLoginClientProvider)
            .requestLoginToken()
            .timeout(_LoginFrameHostState._probeTimeout);
        if (!_isCurrentLoginAttempt(attempt)) return;
        vendor = fresh.vendor;
        carrierToken = fresh.carrierToken;
        grant = await submit(vendor: vendor, carrierToken: carrierToken);
      }
      if (!_isCurrentLoginAttempt(attempt)) return;
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyRememberedLoginGrant(
            grant,
            rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
            rememberedLoginMaskedIdentifier: _resolvedMaskedPhone(grant),
          );
      if (!_isCurrentLoginAttempt(attempt)) return;
      _trackLoginOperation(
        operationId: 'login_one_tap',
        result: 'success',
        durationMs: stopwatch.elapsedMilliseconds,
      );
      _completeLogin();
    } catch (error) {
      if (!_isCurrentLoginAttempt(attempt)) return;
      final origin = _flow.entryMode == LoginEntryMode.rememberedSession
          ? LoginFailureOrigin.returningSession
          : LoginFailureOrigin.oneTap;
      final feedback = _loginFeedback(error, origin: origin);
      _trackLoginOperation(
        operationId: _flow.entryMode == LoginEntryMode.rememberedSession
            ? 'refresh_remembered_session'
            : 'login_one_tap',
        result: 'failure',
        durationMs: stopwatch.elapsedMilliseconds,
        error: error,
        feedback: feedback,
      );
      if (feedback.blocksAccountLogin) {
        _transitionFlow(
          _flow.copyWith(
            step: LoginStep.blocked,
            operation: LoginOperation.idle,
            feedback: feedback,
          ),
          action: 'login_state_changed',
          result: 'blocked',
        );
      } else {
        _enterPhoneEntry(feedback: feedback);
      }
    } finally {
      _finishLoginAttempt(attempt);
    }
  }

  void _handleBackOrDismiss() {
    if (_flowController.terminalClaimed) return;
    switch (_flow.step) {
      case LoginStep.resolving:
      case LoginStep.oneTap:
        _dismissLogin();
      case LoginStep.phoneEntry:
        if (_rootStep == LoginStep.oneTap) {
          _restoreRoot();
        } else {
          _dismissLogin();
        }
      case LoginStep.otp:
        _cancelActiveAttempt();
        _otpCountdownTicker?.cancel();
        _cancelDeliveryConfirmationTimers();
        unawaited(_clearPendingOtpAttempt());
        _otpController.clear();
        _transitionFlow(
          _flow.copyWith(
            step: LoginStep.phoneEntry,
            operation: LoginOperation.idle,
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
      case LoginStep.socialAuthorizing:
        _cancelSocialAuthorization();
      case LoginStep.socialFailed:
      case LoginStep.socialPhoneEntry:
      case LoginStep.socialPhoneOtp:
        _cancelSocialBindingAndRestoreRoot();
      case LoginStep.blocked:
        // REQ-012：blocked 终态顶栏为关闭（X），统一执行宿主关闭策略；
        // 换方式登录的出口由页面内动作与 footer 提供，不复用关闭控件。
        _dismissLogin();
      case LoginStep.completing:
        _cancelActiveAttempt();
        _restoreRoot();
    }
  }

  void _restoreRoot() {
    _otpCountdownTicker?.cancel();
    _cancelDeliveryConfirmationTimers();
    unawaited(_otpAutofillGateway.stop());
    unawaited(_clearPendingOtpAttempt());
    _otpController.clear();
    _lastAutoVerifiedCode = '';
    if (_rootStep == LoginStep.oneTap) {
      _transitionFlow(
        LoginFlowState(
          step: LoginStep.oneTap,
          flowId: _flow.flowId,
          consentState: _flow.consentState,
          entryMode: _rootEntryMode,
          maskedPhone: _rootMaskedPhone,
        ),
        action: 'login_state_changed',
      );
      return;
    }
    _enterPhoneEntry();
  }

  String _resolvedMaskedPhone(AuthSessionGrant result) {
    final fromResult = result.accountHint?.maskedPhone.trim() ?? '';
    if (fromResult.isNotEmpty) return fromResult;
    return _flow.maskedPhone.isNotEmpty ? _flow.maskedPhone : _rootMaskedPhone;
  }

  void _completeLogin() {
    if (_flowController.terminalClaimed) {
      _trackLoginFunnel('login_terminal', result: 'duplicate_suppressed');
      return;
    }
    _transitionFlow(
      _flow.copyWith(
        step: LoginStep.completing,
        operation: LoginOperation.idle,
        feedback: null,
      ),
      action: 'login_state_changed',
    );
    if (!_flowController.tryClaimTerminal()) {
      _trackLoginFunnel('login_terminal', result: 'duplicate_suppressed');
      return;
    }
    _activeAttempt = null;
    _otpCountdownTicker?.cancel();
    _cancelDeliveryConfirmationTimers();
    unawaited(_clearPendingOtpAttempt());
    _trackLoginFunnel('login_terminal', result: 'login_success');
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
    if (ref.read(authContinuationProvider) != null &&
        Navigator.of(context).canPop()) {
      context.pop();
      return;
    }
    final router = GoRouter.maybeOf(context);
    if (router != null) router.go(AppRoutePaths.home);
  }

  void _dismissLogin() {
    if (!_flowController.tryClaimTerminal()) {
      _trackLoginFunnel('login_terminal', result: 'duplicate_suppressed');
      return;
    }
    _activeAttempt = null;
    _entryResolutionGeneration += 1;
    _otpCountdownTicker?.cancel();
    _cancelDeliveryConfirmationTimers();
    unawaited(_clearPendingOtpAttempt());
    if (_isAccountSuspensionSurface) {
      ref
          .read(authSessionControllerProvider.notifier)
          .acknowledgeAccountRestrictionNotice();
    }
    ref.read(authContinuationProvider.notifier).clear();
    _trackLoginFunnel('login_terminal', result: 'dismissed');
    final callback = widget.onDismiss;
    if (callback != null) {
      callback();
      return;
    }
    if (_isAccountSuspensionSurface) {
      context.go(AppRoutePaths.home);
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

  Future<void> _openAccountRestrictionSupport() async {
    if (!_isAccountSuspensionSurface || _openingAccountRestrictionSupport) {
      return;
    }
    _openingAccountRestrictionSupport = true;
    _flowController.refresh();
    _trackLoginOperation(
      operationId: 'open_account_restriction_support',
      result: 'started',
      feedback: accountSuspensionLoginFeedback(
        locale: Localizations.localeOf(context).languageCode,
      ),
    );
    final opened = await ref
        .read(accountRestrictionSupportLauncherProvider)
        .openOfficialSupport();
    if (!mounted) return;
    _openingAccountRestrictionSupport = false;
    _flowController.refresh();
    final feedback = opened
        ? accountSuspensionLoginFeedback(
            locale: Localizations.localeOf(context).languageCode,
          )
        : accountSuspensionSupportUnavailableFeedback();
    _trackLoginOperation(
      operationId: 'open_account_restriction_support',
      result: opened ? 'opened' : 'unavailable',
      feedback: feedback,
    );
    if (!opened) {
      _flowController.replace(_flow.copyWith(feedback: feedback));
    }
  }
}
