part of 'login_page.dart';

extension _LoginFrameHostPendingOtp on _LoginFrameHostState {
  OtpDeliveryState _otpDeliveryStateFromWire(OtpDeliveryStatus status) {
    return switch (status) {
      OtpDeliveryStatus.queued => OtpDeliveryState.queued,
      OtpDeliveryStatus.sentUnconfirmed ||
      OtpDeliveryStatus.delivered => OtpDeliveryState.sent,
      OtpDeliveryStatus.failed => OtpDeliveryState.failed,
    };
  }

  String _otpDeliveryTelemetryResult(OtpDeliveryState state) {
    return switch (state) {
      OtpDeliveryState.queued => 'accepted',
      OtpDeliveryState.sent => 'sent_unconfirmed',
      OtpDeliveryState.failed => 'delivery_failed',
      OtpDeliveryState.confirming => 'delivery_confirming',
      OtpDeliveryState.none => 'accepted',
    };
  }

  Future<void> _persistPendingOtpAttempt(LoginFlowState state) async {
    if (state.isSocialBindingStep || state.idempotencyKey.isEmpty) return;
    final expiresAt = state.pendingOtpExpiresAt;
    final resendDeadline = state.resendDeadline;
    if (expiresAt == null || resendDeadline == null) return;
    try {
      await ref
          .read(pendingOtpAttemptStoreProvider)
          .write(
            PendingOtpAttempt(
              phone: state.phone,
              maskedPhone: state.maskedPhone.isNotEmpty
                  ? state.maskedPhone
                  : _maskPhone(state.phone),
              idempotencyKey: state.idempotencyKey,
              challengeId: state.challengeId,
              requestId: state.deliveryRequestId,
              deliveryStatus: state.otpDeliveryState.name,
              resendDeadlineEpochMs: resendDeadline.millisecondsSinceEpoch,
              expiresAtEpochMs: expiresAt.millisecondsSinceEpoch,
            ),
          );
    } catch (error) {
      _trackLoginOperation(
        operationId: 'persist_pending_otp',
        result: 'failure',
        error: error,
      );
    }
  }

  Future<void> _clearPendingOtpAttempt() async {
    try {
      await ref.read(pendingOtpAttemptStoreProvider).clear();
    } catch (error) {
      _trackLoginOperation(
        operationId: 'clear_pending_otp',
        result: 'failure',
        error: error,
      );
    }
  }

  Future<bool> _restorePendingOtpAttempt() async {
    PendingOtpAttempt? attempt;
    try {
      attempt = await ref.read(pendingOtpAttemptStoreProvider).read();
    } catch (error) {
      _trackLoginOperation(
        operationId: 'restore_pending_otp',
        result: 'failure',
        error: error,
      );
      return false;
    }
    if (!mounted || attempt == null) return false;
    final phone = _validFullPhoneOrEmpty(attempt.phone);
    if (phone.isEmpty) {
      await _clearPendingOtpAttempt();
      return false;
    }
    final now = DateTime.now();
    final resendDeadline = DateTime.fromMillisecondsSinceEpoch(
      attempt.resendDeadlineEpochMs,
    );
    final deliveryState = switch (attempt.deliveryStatus) {
      'queued' => OtpDeliveryState.queued,
      'sent' => OtpDeliveryState.sent,
      'failed' => OtpDeliveryState.failed,
      _ => OtpDeliveryState.confirming,
    };
    _phoneController.value = TextEditingValue(
      text: phone,
      selection: TextSelection.collapsed(offset: phone.length),
    );
    _rootStep = LoginStep.phoneEntry;
    _rootEntryMode = LoginEntryMode.phone;
    _transitionFlow(
      LoginFlowState(
        step: LoginStep.otp,
        flowId: _flow.flowId,
        consentState: LoginConsentState.accepted,
        entryMode: LoginEntryMode.phone,
        phone: phone,
        maskedPhone: attempt.maskedPhone,
        challengeId: attempt.challengeId,
        deliveryRequestId: attempt.requestId,
        idempotencyKey: attempt.idempotencyKey,
        otpPurpose: LoginOtpPurpose.login,
        otpChallengeState: resendDeadline.isAfter(now)
            ? OtpChallengeState.active
            : OtpChallengeState.resendAvailable,
        otpDeliveryState: deliveryState,
        resendDeadline: resendDeadline,
        pendingOtpExpiresAt: DateTime.fromMillisecondsSinceEpoch(
          attempt.expiresAtEpochMs,
        ),
        otpFocusSerial: 1,
      ),
      action: 'login_state_changed',
      result: 'pending_otp_restored',
    );
    _startCountdownTicker();
    await _otpAutofillGateway.start((code) {
      if (mounted && _flow.isOtpStep && !_flow.isBusy) {
        _handleOtpChanged(code);
      }
    });
    if (attempt.requestId.isNotEmpty) {
      _otpAutofillGateway.bindRequestRef(attempt.requestId);
    }
    if (deliveryState == OtpDeliveryState.confirming ||
        deliveryState == OtpDeliveryState.queued) {
      final requestedAt = _flow.pendingOtpExpiresAt!.subtract(
        _LoginFrameHostState._pendingOtpTtl,
      );
      _scheduleDeliveryConfirmations(requestedAt);
      unawaited(_confirmPendingOtpDelivery());
    }
    return true;
  }
}
