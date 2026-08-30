part of 'login_page.dart';

class LoginFrame extends StatelessWidget {
  const LoginFrame({
    super.key,
    required this.state,
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
                  // 左侧收窄到光学对齐 inset，使图标视觉左缘与正文左边距对齐。
                  padding: const EdgeInsets.only(
                    left: AppSpacing.loginTopBarLeadingInset,
                    right: AppSpacing.lg,
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

  // REQ-012：仅 blocked 终态显示关闭（X）并执行宿主关闭策略；其余全部步骤
  // （含根步骤）统一显示返回箭头，根步骤箭头即按宿主 LoginDismissPolicy 关闭。
  bool get _showsBackNavigation => state.step != LoginStep.blocked;

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
        if (subtitle.isNotEmpty) ...<Widget>[
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
        const SizedBox(height: AppSpacing.forty),
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
        const SizedBox(height: AppSpacing.sm),
        _LoginFeedbackSlot(feedback: state.feedback),
        const SizedBox(height: AppSpacing.sm),
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
    final cooldownSeconds = state.remainingResendSeconds(DateTime.now());
    final rateLimited =
        state.otpChallengeState == OtpChallengeState.rateLimited &&
        cooldownSeconds > 0;
    final readinessChecking =
        state.otpReadinessState == OtpReadinessState.checking;
    final readinessUnavailable =
        state.otpReadinessState == OtpReadinessState.unavailable;
    final visibleFeedback = rateLimited
        ? LoginFeedback(
            message: FoundationText.loginOtpRateLimitedCountdown.replaceFirst(
              '%d',
              cooldownSeconds.toString(),
            ),
            copyKey: 'loginOtpRateLimited',
            surface: LoginFeedbackSurface.phone,
            recoveryAction: 'waitThenResendOtp',
            retryAfterSeconds: cooldownSeconds,
          )
        : state.feedback;
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
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
        const SizedBox(height: AppSpacing.sm),
        _LoginFeedbackSlot(feedback: visibleFeedback),
        const SizedBox(height: AppSpacing.sm),
        LoginActionButton(
          key: const ValueKey<String>('loginPhonePrimary'),
          label: state.operation == LoginOperation.sendingOtp
              ? FoundationText.loginSendOtpSubmitting
              : readinessChecking
              ? FoundationText.loginOtpReadinessChecking
              : readinessUnavailable
              ? FoundationText.loginOtpReadinessRetry
              : sendFailed
              ? FoundationText.loginOtpRequestRetry
              : FoundationText.loginSendOtp,
          enabled:
              !rateLimited &&
              (readinessUnavailable ||
                  (state.hasValidPhone &&
                      state.otpReadinessState == OtpReadinessState.ready)),
          busy:
              state.operation == LoginOperation.sendingOtp || readinessChecking,
          outlined: readinessUnavailable,
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
    final presentation = OtpPagePresentation.fromState(state, DateTime.now());
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
        _LoginHeading(
          title: FoundationText.loginOtpTitle,
          subtitle: '',
          provider: showProvider ? state.provider : '',
        ),
        const SizedBox(height: AppSpacing.sm),
        _OtpSubtitleRow(
          subtitle: presentation.subtitle,
          enabled: !state.isBusy,
          onChangePhone: onChangePhone,
        ),
        const SizedBox(height: AppSpacing.lg),
        OtpCodeBoxes(
          controller: controller,
          enabled: state.canEditOtp,
          onChanged: onChanged,
          focusRequestSerial: state.otpFocusSerial,
          shakeSerial: state.otpShakeSerial,
        ),
        const SizedBox(height: AppSpacing.sm),
        _OtpStatusRegion(presentation: presentation),
        const SizedBox(height: AppSpacing.sm),
        AnimatedSize(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          child: presentation.hasRecoveryActions
              ? _OtpRecoveryActionGroup(
                  presentation: presentation,
                  busy: state.isBusy,
                  onResend: onResend,
                  onRetryVerify: onRetryVerify,
                  onChangePhone: onChangePhone,
                )
              : _OtpResendPrompt(
                  remainingSeconds: presentation.resendRemainingSeconds,
                  busy: state.isBusy,
                  onResend: onResend,
                ),
        ),
      ],
    );
  }
}

/// OTP 步副标题区：承载验证码发送状态与脱敏手机号，「更换手机号」为行内
/// 动作（REQ-003）。文案只反映发送事实，用户输入时不清空、不移位。
class _OtpSubtitleRow extends StatelessWidget {
  const _OtpSubtitleRow({
    required this.subtitle,
    required this.enabled,
    required this.onChangePhone,
  });

  final String subtitle;
  final bool enabled;
  final VoidCallback onChangePhone;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: AppSpacing.xs,
      children: <Widget>[
        Text(
          subtitle,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.base,
            height: AppTypography.lineHeightCompact,
          ),
        ),
        SizedBox(
          height: AppSpacing.minInteractiveSize,
          child: CupertinoButton(
            key: const ValueKey<String>('loginChangePhone'),
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            onPressed: enabled ? onChangePhone : null,
            child: Text(
              FoundationText.loginPhoneChange,
              style: const TextStyle(fontSize: AppTypography.base),
            ),
          ),
        ),
      ],
    );
  }
}

/// 输入格下方唯一的反馈/状态占位区（REQ-006）：固定最小高度，错误与
/// 「正在验证」只出现在这里；出现、消失或切换不移动输入格及其上方内容。
class _OtpStatusRegion extends StatelessWidget {
  const _OtpStatusRegion({required this.presentation});

  final OtpPagePresentation presentation;

  @override
  Widget build(BuildContext context) {
    final Widget content;
    if (presentation.message.isEmpty) {
      content = const SizedBox.shrink();
    } else {
      final color = presentation.tone == OtpPresentationTone.error
          ? AppColors.errorForeground(context)
          : AppColors.iosSecondaryLabel(context);
      content = Semantics(
        key: ValueKey<String>(presentation.announceKey),
        liveRegion: true,
        label: presentation.message,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            if (presentation.showDeliveryProgress) ...<Widget>[
              AppRequestFeedback.inline(
                indicatorColor: AppColors.iosAccent(context),
              ),
              const SizedBox(width: AppSpacing.sm),
            ],
            Flexible(
              child: Text(
                presentation.message,
                key: const ValueKey<String>('loginOtpStatusMessage'),
                maxLines: 2,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: color,
                  fontSize: AppTypography.inlineError,
                  fontWeight: presentation.tone == OtpPresentationTone.error
                      ? AppTypography.inlineErrorWeight
                      : AppTypography.regular,
                ),
              ),
            ),
          ],
        ),
      );
    }
    return ConstrainedBox(
      constraints: const BoxConstraints(
        minHeight: AppSpacing.loginFeedbackSlotMinHeight,
      ),
      child: Center(child: content),
    );
  }
}

/// 一键登录与手机号步骤的反馈固定占位区：空态保留最小高度，反馈出现或
/// 消失不移动输入框、主按钮与协议行（REQ-003）。
class _LoginFeedbackSlot extends StatelessWidget {
  const _LoginFeedbackSlot({required this.feedback});

  final LoginFeedback? feedback;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(
        minHeight: AppSpacing.loginFeedbackSlotMinHeight,
      ),
      child: Center(
        child: switch (feedback) {
          final present? => _LoginFeedbackText(feedback: present),
          null => const SizedBox.shrink(),
        },
      ),
    );
  }
}

class _OtpRecoveryActionGroup extends StatelessWidget {
  const _OtpRecoveryActionGroup({
    required this.presentation,
    required this.busy,
    required this.onResend,
    required this.onRetryVerify,
    required this.onChangePhone,
  });

  final OtpPagePresentation presentation;
  final bool busy;
  final VoidCallback onResend;
  final VoidCallback onRetryVerify;
  final VoidCallback onChangePhone;

  @override
  Widget build(BuildContext context) {
    final actions = <OtpRecoveryAction>[
      ?presentation.primaryAction,
      ?presentation.secondaryAction,
    ];
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          children: <Widget>[
            for (var index = 0; index < actions.length; index++) ...<Widget>[
              if (index > 0) const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: LoginActionButton(
                  key: ValueKey<String>(
                    'loginOtpRecovery-${actions[index].name}',
                  ),
                  label: _otpRecoveryActionLabel(actions[index]),
                  outlined: true,
                  enabled: !busy,
                  onPressed: () => _runOtpRecoveryAction(
                    actions[index],
                    onResend: onResend,
                    onRetryVerify: onRetryVerify,
                    onChangePhone: onChangePhone,
                  ),
                ),
              ),
            ],
          ],
        ),
        if (presentation.primaryAction == OtpRecoveryAction.retryVerify &&
            presentation.resendRemainingSeconds > 0) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          Text(
            FoundationText.loginOtpResendCountdown.replaceFirst(
              '%d',
              presentation.resendRemainingSeconds.toString(),
            ),
            style: TextStyle(
              color: AppColors.iosSecondaryLabel(context),
              fontSize: AppTypography.base,
            ),
          ),
        ],
      ],
    );
  }
}

class _OtpResendPrompt extends StatelessWidget {
  const _OtpResendPrompt({
    required this.remainingSeconds,
    required this.busy,
    required this.onResend,
  });

  final int remainingSeconds;
  final bool busy;
  final VoidCallback onResend;

  @override
  Widget build(BuildContext context) {
    final ready = remainingSeconds <= 0 && !busy;
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: <Widget>[
        Text(
          FoundationText.loginOtpNotReceived,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.base,
          ),
        ),
        if (ready)
          SizedBox(
            height: AppSpacing.minInteractiveSize,
            child: CupertinoButton(
              key: const ValueKey<String>('loginOtpResend'),
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
              onPressed: onResend,
              child: Text(
                FoundationText.loginOtpResend,
                // 与前面「未收到验证码？」正文字号一致，避免行内字阶跳跃。
                style: const TextStyle(fontSize: AppTypography.base),
              ),
            ),
          )
        else
          Text(
            FoundationText.loginOtpResendCountdown.replaceFirst(
              '%d',
              remainingSeconds.toString(),
            ),
            style: TextStyle(
              color: AppColors.iosSecondaryLabel(context),
              fontSize: AppTypography.base,
            ),
          ),
      ],
    );
  }
}

String _otpRecoveryActionLabel(OtpRecoveryAction action) => switch (action) {
  OtpRecoveryAction.retryVerify => FoundationText.loginOtpVerifyRetry,
  OtpRecoveryAction.resend => FoundationText.loginOtpResend,
  OtpRecoveryAction.contactSupport =>
    FoundationText.loginAccountSuspensionSupport,
  OtpRecoveryAction.changePhone => FoundationText.loginPhoneChange,
};

void _runOtpRecoveryAction(
  OtpRecoveryAction action, {
  required VoidCallback onResend,
  required VoidCallback onRetryVerify,
  required VoidCallback onChangePhone,
}) {
  switch (action) {
    case OtpRecoveryAction.retryVerify:
      onRetryVerify();
      return;
    case OtpRecoveryAction.resend:
      onResend();
      return;
    case OtpRecoveryAction.contactSupport:
    case OtpRecoveryAction.changePhone:
      onChangePhone();
      return;
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
    final subtitle = isAccountSuspended
        ? FoundationText.loginAccountSuspensionSubtitle
        : FoundationText.loginServiceUnavailable;
    return Column(
      children: <Widget>[
        const SizedBox(height: AppSpacing.forty),
        _LoginHeading(
          title: isAccountSuspended
              ? FoundationText.loginAccountSuspensionTitle
              : FoundationText.login,
          subtitle: subtitle,
        ),
        const SizedBox(height: AppSpacing.lg),
        // 具体错误原因与副标题同句时不重复渲染，避免同屏两遍同一句话。
        if (state.feedback case final feedback? when feedback.message != subtitle)
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
