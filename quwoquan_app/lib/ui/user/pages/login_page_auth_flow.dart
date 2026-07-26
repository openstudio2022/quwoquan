part of 'login_page.dart';

extension _LoginFrameHostAuthFlow on _LoginFrameHostState {
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
      _updateState(() {
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
      _updateState(() => _showAgreementError = true);
      return;
    }
    final attempt = _beginLoginAttempt();
    final latency = Stopwatch()..start();
    _updateState(() {
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
              .read(accountSessionLifecycleCommandWriterProvider)
              .refreshToken(
                RefreshTokenCommand(refreshToken: stored.refreshToken.trim()),
              );
          if (!_isCurrentLoginAttempt(attempt)) {
            return;
          }
          await ref
              .read(authSessionControllerProvider.notifier)
              .applyRefreshGrant(result);
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
      Future<AuthSessionGrant> submitOneTap({
        required String token,
        required String vendor,
      }) {
        return ref
            .read(accountSessionLoginCommandWriterProvider)
            .loginOneTap(
              LoginOneTapCommand(
              vendor: vendor,
              carrierToken: token,
              deviceId: session.installId.isNotEmpty
                  ? session.installId
                  : stored.installId,
              platform: CloudRequestHeaders.platform(),
              appVersion: CloudRequestHeaders.appVersion,
              agreementVersion: AuthLegalConfig.agreementVersion,
              privacyVersion: AuthLegalConfig.privacyVersion,
              ),
            );
      }

      late AuthSessionGrant result;
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
            .timeout(_LoginFrameHostState._probeTimeout);
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
          .applyRememberedLoginGrant(
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
      _updateState(() => _presentation = entryBeforeSubmit);
      return;
    }
    if (feedback.surface == LoginErrorSurface.agreement) {
      _updateState(() {
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
    _updateState(() {
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

  String _resolvedMaskedPhone(AuthSessionGrant result) {
    final fromResult = result.accountHint?.maskedPhone.trim() ?? '';
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
}
