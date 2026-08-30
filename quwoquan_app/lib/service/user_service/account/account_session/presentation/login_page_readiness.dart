part of 'login_page.dart';

extension _LoginFrameHostReadiness on _LoginFrameHostState {
  Future<void> _handlePhonePrimary() async {
    if (_flow.otpReadinessState != OtpReadinessState.ready) {
      await _checkOtpDeliveryReadiness();
      return;
    }
    await _requestOtp();
  }

  Future<void> _checkOtpDeliveryReadiness() async {
    if (!mounted || _flow.isBusy || _flow.isOtpStep) return;
    final generation = _entryResolutionGeneration;
    _flowController.replace(
      _flow.copyWith(
        otpReadinessState: OtpReadinessState.checking,
        feedback: null,
      ),
    );
    try {
      final readiness = await ref
          .read(authenticationChallengeCommandWriterProvider)
          .getOtpDeliveryReadiness()
          .timeout(_LoginFrameHostState._probeTimeout);
      if (!mounted || generation != _entryResolutionGeneration) return;
      const unavailableFeedback = LoginFeedback(
        message: FoundationText.loginOtpServiceUnavailable,
        copyKey: 'loginOtpServiceUnavailable',
        surface: LoginFeedbackSurface.phone,
        recoveryAction: 'retryReadiness',
      );
      _flowController.replace(
        _flow.copyWith(
          otpReadinessState: readiness.isReady
              ? OtpReadinessState.ready
              : OtpReadinessState.unavailable,
          feedback: readiness.isReady ? null : unavailableFeedback,
        ),
      );
      if (!readiness.isReady) {
        _trackLoginOperation(
          operationId: 'get_otp_delivery_readiness',
          result: 'temporarily_unavailable',
          feedback: unavailableFeedback,
        );
      }
    } catch (error) {
      if (!mounted || generation != _entryResolutionGeneration) return;
      _flowController.replace(
        _flow.copyWith(
          otpReadinessState: OtpReadinessState.unavailable,
          feedback: const LoginFeedback(
            message: FoundationText.loginOtpServiceUnavailable,
            copyKey: 'loginOtpServiceUnavailable',
            surface: LoginFeedbackSurface.phone,
            recoveryAction: 'retryReadiness',
          ),
        ),
      );
      _trackLoginOperation(
        operationId: 'get_otp_delivery_readiness',
        result: 'temporarily_unavailable',
        error: error,
      );
    }
  }
}
