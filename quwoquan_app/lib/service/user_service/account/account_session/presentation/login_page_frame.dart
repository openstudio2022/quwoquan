part of 'login_page.dart';

class LoginFrame extends StatelessWidget {
  const LoginFrame({
    super.key,
    required this.state,
    required this.phoneEntryHasParent,
    required this.socialMethodAvailability,
    required this.onAgreementToggle,
    required this.onNavigate,
    required this.onOneTap,
    required this.onOtherPhone,
    required this.onPhonePrimary,
    required this.onAgreementTap,
    required this.onPrivacyTap,
    required this.onSocialMethod,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onPhoneEditingComplete,
    required this.onOtpChanged,
    required this.onResendOtp,
    required this.onRetryOtpVerify,
    required this.onChangePhone,
    required this.onRetrySocial,
    required this.onCancelSocial,
    required this.onAccountRestrictionSupport,
    required this.accountRestrictionSupportBusy,
    this.dismissPolicy = LoginDismissPolicy.popPrevious,
    this.isInline = false,
  });

  final LoginFlowState state;
  final bool phoneEntryHasParent;
  final Map<String, NativeAuthCapability> socialMethodAvailability;
  final VoidCallback onAgreementToggle;
  final VoidCallback onNavigate;
  final VoidCallback onOneTap;
  final VoidCallback onOtherPhone;
  final VoidCallback onPhonePrimary;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;
  final ValueChanged<String> onSocialMethod;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final VoidCallback onPhoneEditingComplete;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResendOtp;
  final VoidCallback onRetryOtpVerify;
  final VoidCallback onChangePhone;
  final VoidCallback onRetrySocial;
  final VoidCallback onCancelSocial;
  final VoidCallback onAccountRestrictionSupport;
  final bool accountRestrictionSupportBusy;
  final LoginDismissPolicy dismissPolicy;
  final bool isInline;

  @override
  Widget build(BuildContext context) {
    final frame = DecoratedBox(
      decoration: BoxDecoration(color: AppColors.loginPageBackground(context)),
      child: SafeArea(
        child: Column(
          children: <Widget>[
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: AppSpacing.loginFrameMaxWidth,
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.lg,
                  ),
                  child: _LoginTopBar(
                    onNavigate: onNavigate,
                    showBack: _showsBackNavigation,
                    enabled: state.step != LoginStep.completing,
                  ),
                ),
              ),
            ),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  return SingleChildScrollView(
                    key: const ValueKey<String>('loginMainScroll'),
                    keyboardDismissBehavior:
                        ScrollViewKeyboardDismissBehavior.onDrag,
                    physics: const ClampingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.lg,
                      AppSpacing.md,
                      AppSpacing.lg,
                      AppSpacing.lg,
                    ),
                    child: Center(
                      child: ConstrainedBox(
                        constraints: BoxConstraints(
                          maxWidth: AppSpacing.loginFrameMaxWidth,
                          minHeight: constraints.maxHeight - AppSpacing.lg,
                        ),
                        child: Align(
                          alignment: Alignment.topCenter,
                          child: _buildStep(context),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            LoginMethodFooter(
              onTap: onSocialMethod,
              availableMethods: socialMethodAvailability,
              disabledProvider: _disabledFooterProvider,
            ),
          ],
        ),
      ),
    );
    if (!isInline) return frame;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.loginPageBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: AppColors.webPcLoginSurfaceShadow,
            blurRadius: AppSpacing.webPcToolbarElevationBlurRadius,
            offset: Offset(0, AppSpacing.ten),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        child: frame,
      ),
    );
  }

  bool get _showsBackNavigation => switch (state.step) {
    LoginStep.phoneEntry => phoneEntryHasParent,
    LoginStep.otp ||
    LoginStep.socialAuthorizing ||
    LoginStep.socialFailed ||
    LoginStep.socialPhoneEntry ||
    LoginStep.socialPhoneOtp ||
    LoginStep.blocked => true,
    _ => false,
  };

  String get _disabledFooterProvider => switch (state.step) {
    LoginStep.socialAuthorizing ||
    LoginStep.socialFailed ||
    LoginStep.socialPhoneEntry ||
    LoginStep.socialPhoneOtp => state.provider,
    _ => '',
  };

  Widget _buildStep(BuildContext context) {
    return KeyedSubtree(
      key: ValueKey<String>('loginStep-${state.step.name}'),
      child: switch (state.step) {
        LoginStep.resolving => const _ResolvingLoginStep(),
        LoginStep.oneTap => _OneTapLoginStep(
          state: state,
          onOneTap: onOneTap,
          onOtherPhone: onOtherPhone,
          onAgreementToggle: onAgreementToggle,
          onAgreementTap: onAgreementTap,
          onPrivacyTap: onPrivacyTap,
        ),
        LoginStep.phoneEntry => _PhoneEntryLoginStep(
          state: state,
          controller: phoneController,
          onChanged: onPhoneChanged,
          onEditingComplete: onPhoneEditingComplete,
          onPrimary: onPhonePrimary,
          onAgreementToggle: onAgreementToggle,
          onAgreementTap: onAgreementTap,
          onPrivacyTap: onPrivacyTap,
          showAgreement: true,
        ),
        LoginStep.otp => _OtpLoginStep(
          state: state,
          controller: otpController,
          onChanged: onOtpChanged,
          onResend: onResendOtp,
          onRetryVerify: onRetryOtpVerify,
          onChangePhone: onChangePhone,
        ),
        LoginStep.socialAuthorizing => _SocialAuthorizingStep(
          state: state,
          onCancel: onCancelSocial,
        ),
        LoginStep.socialFailed => _SocialFailedStep(
          state: state,
          onRetry: onRetrySocial,
        ),
        LoginStep.socialPhoneEntry => _PhoneEntryLoginStep(
          state: state,
          controller: phoneController,
          onChanged: onPhoneChanged,
          onEditingComplete: onPhoneEditingComplete,
          onPrimary: onPhonePrimary,
          onAgreementToggle: onAgreementToggle,
          onAgreementTap: onAgreementTap,
          onPrivacyTap: onPrivacyTap,
          showAgreement: false,
          showProvider: true,
        ),
        LoginStep.socialPhoneOtp => _OtpLoginStep(
          state: state,
          controller: otpController,
          onChanged: onOtpChanged,
          onResend: onResendOtp,
          onRetryVerify: onRetryOtpVerify,
          onChangePhone: onChangePhone,
          showProvider: true,
        ),
        LoginStep.blocked => _BlockedLoginStep(
          state: state,
          onChangeMethod: onOtherPhone,
          onSupport: onAccountRestrictionSupport,
          supportBusy: accountRestrictionSupportBusy,
        ),
        LoginStep.completing => const _CompletingLoginStep(),
      },
    );
  }
}

class _LoginHeading extends StatelessWidget {
  const _LoginHeading({
    required this.title,
    required this.subtitle,
    this.provider = '',
  });

  final String title;
  final String subtitle;
  final String provider;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        if (provider.isNotEmpty) ...<Widget>[
          LoginProviderMark(provider: provider),
          const SizedBox(height: AppSpacing.lg),
        ],
        Text(
          title,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.iosLabel(context),
            fontSize: AppTypography.iosProfileTitle,
            fontWeight: AppTypography.bold,
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          subtitle,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.base,
            height: AppTypography.lineHeightCompact,
          ),
        ),
      ],
    );
  }
}

class _ResolvingLoginStep extends StatelessWidget {
  const _ResolvingLoginStep();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
        const _LoginHeading(
          title: FoundationText.login,
          subtitle: FoundationText.loginResolvingHint,
        ),
        const SizedBox(height: AppSpacing.xl),
        AppRequestFeedback.inline(indicatorColor: AppColors.iosAccent(context)),
      ],
    );
  }
}

class _OneTapLoginStep extends StatelessWidget {
  const _OneTapLoginStep({
    required this.state,
    required this.onOneTap,
    required this.onOtherPhone,
    required this.onAgreementToggle,
    required this.onAgreementTap,
    required this.onPrivacyTap,
  });

  final LoginFlowState state;
  final VoidCallback onOneTap;
  final VoidCallback onOtherPhone;
  final VoidCallback onAgreementToggle;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;

  @override
  Widget build(BuildContext context) {
    final phone = state.maskedPhone;
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.twenty),
        _LoginHeading(
          title: FoundationText.loginReturningDefaultName,
          subtitle: phone.isEmpty
              ? FoundationText.loginCarrierDefaultPhone
              : '${FoundationText.loginCarrierDefaultPhone} $phone',
        ),
        const SizedBox(height: AppSpacing.forty),
        LoginActionButton(
          key: const ValueKey<String>('loginOneTapPrimary'),
          label: FoundationText.loginOneTapPrimary,
          busy: state.isBusy,
          onPressed: onOneTap,
        ),
        const SizedBox(height: AppSpacing.md),
        LoginActionButton(
          key: const ValueKey<String>('loginOtherPhoneButton'),
          label: FoundationText.loginMethodPhone,
          outlined: true,
          enabled: !state.isBusy,
          onPressed: onOtherPhone,
        ),
        if (state.feedback case final feedback?) ...<Widget>[
          const SizedBox(height: AppSpacing.md),
          _LoginFeedbackText(feedback: feedback),
        ],
        const SizedBox(height: AppSpacing.md),
        LoginAgreementRow(
          accepted: state.consentState == LoginConsentState.accepted,
          onToggle: onAgreementToggle,
          onAgreementTap: onAgreementTap,
          onPrivacyTap: onPrivacyTap,
        ),
      ],
    );
  }
}

class _PhoneEntryLoginStep extends StatelessWidget {
  const _PhoneEntryLoginStep({
    required this.state,
    required this.controller,
    required this.onChanged,
    required this.onEditingComplete,
    required this.onPrimary,
    required this.onAgreementToggle,
    required this.onAgreementTap,
    required this.onPrivacyTap,
    required this.showAgreement,
    this.showProvider = false,
  });

  final LoginFlowState state;
  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onEditingComplete;
  final VoidCallback onPrimary;
  final VoidCallback onAgreementToggle;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;
  final bool showAgreement;
  final bool showProvider;

  @override
  Widget build(BuildContext context) {
    final binding = state.step == LoginStep.socialPhoneEntry;
    final sendFailed =
        state.feedback?.recoveryAction == 'resendOtp' ||
        state.feedback?.copyKey == 'loginOtpSendFailed';
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.twenty),
        _LoginHeading(
          title: binding
              ? FoundationText.loginBindPhoneTitle
              : FoundationText.loginPhoneTitle,
          subtitle: binding
              ? FoundationText.loginBindPhoneSubtitle
              : FoundationText.loginPhoneSubtitle,
          provider: showProvider ? state.provider : '',
        ),
        const SizedBox(height: AppSpacing.forty),
        LoginPhoneField(
          controller: controller,
          enabled: state.canEditPhone,
          onChanged: onChanged,
          onEditingComplete: onEditingComplete,
        ),
        if (state.feedback case final feedback?) ...<Widget>[
          const SizedBox(height: AppSpacing.md),
          _LoginFeedbackText(feedback: feedback),
        ],
        const SizedBox(height: AppSpacing.twenty),
        LoginActionButton(
          key: const ValueKey<String>('loginPhonePrimary'),
          label: sendFailed
              ? FoundationText.loginOtpRequestRetry
              : FoundationText.loginSendOtp,
          enabled: state.hasValidPhone,
          busy: state.operation == LoginOperation.sendingOtp,
          onPressed: onPrimary,
        ),
        if (showAgreement) ...<Widget>[
          const SizedBox(height: AppSpacing.md),
          LoginAgreementRow(
            accepted: state.consentState == LoginConsentState.accepted,
            onToggle: onAgreementToggle,
            onAgreementTap: onAgreementTap,
            onPrivacyTap: onPrivacyTap,
          ),
        ],
      ],
    );
  }
}

class _OtpLoginStep extends StatelessWidget {
  const _OtpLoginStep({
    required this.state,
    required this.controller,
    required this.onChanged,
    required this.onResend,
    required this.onRetryVerify,
    required this.onChangePhone,
    this.showProvider = false,
  });

  final LoginFlowState state;
  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onResend;
  final VoidCallback onRetryVerify;
  final VoidCallback onChangePhone;
  final bool showProvider;

  @override
  Widget build(BuildContext context) {
    final verifying =
        state.operation == LoginOperation.verifyingOtp ||
        state.operation == LoginOperation.completingBinding;
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.twenty),
        _LoginHeading(
          title: FoundationText.loginOtpTitle,
          subtitle: FoundationText.loginOtpSentTo.replaceFirst(
            '%s',
            state.maskedPhone,
          ),
          provider: showProvider ? state.provider : '',
        ),
        const SizedBox(height: AppSpacing.forty),
        OtpCodeBoxes(
          controller: controller,
          enabled: state.canEditOtp,
          onChanged: onChanged,
          focusRequestSerial: state.otpFocusSerial,
          shakeSerial: state.otpShakeSerial,
        ),
        SizedBox(
          height: AppSpacing.forty,
          child: Center(
            child: verifying
                ? Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      AppRequestFeedback.inline(
                        indicatorColor: AppColors.iosAccent(context),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      Text(
                        FoundationText.loginOtpVerifying,
                        style: TextStyle(
                          color: AppColors.iosAccent(context),
                          fontSize: AppTypography.base,
                        ),
                      ),
                    ],
                  )
                : state.feedback == null
                ? const SizedBox.shrink()
                : _LoginFeedbackText(feedback: state.feedback!),
          ),
        ),
        _OtpResendAction(state: state, onPressed: onResend),
        if (state.feedback?.preserveOtp == true) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            key: const ValueKey<String>('loginOtpRetryVerify'),
            onPressed: onRetryVerify,
            child: Text(FoundationText.loginOtpVerifyRetry),
          ),
        ],
        const SizedBox(height: AppSpacing.xs),
        CupertinoButton(
          key: const ValueKey<String>('loginChangePhone'),
          onPressed: state.isBusy ? null : onChangePhone,
          child: Text(FoundationText.loginPhoneChange),
        ),
      ],
    );
  }
}

class _OtpResendAction extends StatelessWidget {
  const _OtpResendAction({required this.state, required this.onPressed});

  final LoginFlowState state;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final seconds = state.remainingResendSeconds(DateTime.now());
    final ready = seconds <= 0 && !state.isBusy;
    final label = ready
        ? FoundationText.loginOtpResend
        : FoundationText.loginOtpResendCountdown.replaceFirst(
            '%d',
            seconds.toString(),
          );
    return SizedBox(
      key: const ValueKey<String>('loginOtpResendSlot'),
      height: AppSpacing.minInteractiveSize,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: ready ? onPressed : null,
        child: Text(
          label,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: ready
                ? AppColors.iosAccent(context)
                : AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.base,
          ),
        ),
      ),
    );
  }
}

class _SocialAuthorizingStep extends StatelessWidget {
  const _SocialAuthorizingStep({required this.state, required this.onCancel});

  final LoginFlowState state;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final providerLabel = _providerLabel(state.provider);
    final title = switch (state.provider) {
      'wechat' => FoundationText.loginSocialAuthorizingWechat,
      'qq' => FoundationText.loginSocialAuthorizingQq,
      _ => FoundationText.loginSocialAuthorizingAlipay,
    };
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
        _LoginHeading(
          title: title,
          subtitle: FoundationText.loginSocialAuthorizingSubtitle.replaceFirst(
            '%s',
            providerLabel,
          ),
          provider: state.provider,
        ),
        const SizedBox(height: AppSpacing.xl),
        AppRequestFeedback.inline(indicatorColor: AppColors.iosAccent(context)),
        const SizedBox(height: AppSpacing.md),
        CupertinoButton(
          key: const ValueKey<String>('loginSocialCancel'),
          onPressed: onCancel,
          child: Text(FoundationText.loginSocialAuthorizationCancel),
        ),
      ],
    );
  }
}

class _SocialFailedStep extends StatelessWidget {
  const _SocialFailedStep({required this.state, required this.onRetry});

  final LoginFlowState state;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
        _LoginHeading(
          title: FoundationText.loginSocialAuthorizationFailed,
          subtitle: FoundationText.loginSocialAuthorizationFailedSubtitle,
          provider: state.provider,
        ),
        const SizedBox(height: AppSpacing.xl),
        LoginActionButton(
          key: const ValueKey<String>('loginSocialRetry'),
          label: FoundationText.loginSocialAuthorizationRetry,
          busy: state.isBusy,
          onPressed: onRetry,
        ),
      ],
    );
  }
}

class _BlockedLoginStep extends StatelessWidget {
  const _BlockedLoginStep({
    required this.state,
    required this.onChangeMethod,
    required this.onSupport,
    required this.supportBusy,
  });

  final LoginFlowState state;
  final VoidCallback onChangeMethod;
  final VoidCallback onSupport;
  final bool supportBusy;

  @override
  Widget build(BuildContext context) {
    final isAccountSuspended =
        state.feedback?.sourceCode == UserErrorCode.accountSuspended.code;
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
        _LoginHeading(
          title: isAccountSuspended
              ? FoundationText.loginAccountSuspensionTitle
              : FoundationText.login,
          subtitle: isAccountSuspended
              ? FoundationText.loginAccountSuspensionSubtitle
              : FoundationText.loginServiceUnavailable,
        ),
        const SizedBox(height: AppSpacing.lg),
        if (state.feedback case final feedback?)
          _LoginFeedbackText(feedback: feedback),
        const SizedBox(height: AppSpacing.lg),
        if (isAccountSuspended) ...<Widget>[
          LoginActionButton(
            key: const ValueKey<String>('loginAccountSuspensionSupport'),
            label: FoundationText.loginAccountSuspensionSupport,
            busy: supportBusy,
            onPressed: onSupport,
          ),
          const SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            key: const ValueKey<String>('loginAccountSuspensionOtherAccount'),
            onPressed: supportBusy ? null : onChangeMethod,
            child: Text(FoundationText.loginAccountSuspensionUseOtherAccount),
          ),
        ] else
          LoginActionButton(
            label: FoundationText.loginMethodPhone,
            onPressed: onChangeMethod,
          ),
      ],
    );
  }
}

class _CompletingLoginStep extends StatelessWidget {
  const _CompletingLoginStep();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
        const _LoginHeading(
          title: FoundationText.loginSubmitting,
          subtitle: FoundationText.loginRedirecting,
        ),
        const SizedBox(height: AppSpacing.xl),
        AppRequestFeedback.inline(indicatorColor: AppColors.iosAccent(context)),
      ],
    );
  }
}

class _LoginFeedbackText extends StatelessWidget {
  const _LoginFeedbackText({required this.feedback});

  final LoginFeedback feedback;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      label: feedback.message,
      child: Text(
        feedback.message,
        key: ValueKey<String>('loginFeedback-${feedback.copyKey}'),
        textAlign: TextAlign.center,
        style: TextStyle(
          color: AppColors.errorForeground(context),
          fontSize: AppTypography.inlineError,
          fontWeight: AppTypography.inlineErrorWeight,
        ),
      ),
    );
  }
}

String _providerLabel(String provider) => switch (provider) {
  'wechat' => FoundationText.loginMethodWechat,
  'qq' => FoundationText.loginMethodQq,
  _ => FoundationText.loginMethodAlipay,
};
