part of 'login_page.dart';

class LoginFrame extends StatelessWidget {
  const LoginFrame({
    super.key,
    required this.reason,
    required this.presentation,
    required this.agreementAccepted,
    required this.onAgreementToggle,
    required this.onDismiss,
    required this.onPrimary,
    required this.onAgreementTap,
    required this.onPrivacyTap,
    required this.onOtherMethod,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onOtpChanged,
    required this.onResendOtp,
    this.allowGuestDismissPop = true,
    this.isInline = false,
  });

  final String? reason;
  final LoginEntryPresentation presentation;
  final bool agreementAccepted;
  final VoidCallback onAgreementToggle;
  final VoidCallback onDismiss;
  final VoidCallback onPrimary;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;
  final ValueChanged<String> onOtherMethod;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResendOtp;

  /// 关闭语义：强登录入口（`allowGuestDismissPop == false`，关闭走安全兜底而非
  /// 原路 pop）按 iOS Modal leading 语义用 `xmark`；可 pop 回上一页的软入口用 `back`。
  final bool allowGuestDismissPop;
  final bool isInline;

  @override
  Widget build(BuildContext context) {
    final copy = _loginHeroCopyForPresentation(presentation, reason);
    final content = DecoratedBox(
      decoration: BoxDecoration(color: AppColors.loginPageBackground(context)),
      // 单屏布局：内容按设计已收紧到常见 iPhone 一屏可容纳，弹性 Spacer 把
      // "其他登录方式"贴底完整展示；ClampingScrollPhysics 去掉 iOS 回弹/阻尼，
      // 内容适配时不可滑动，仅在极小屏作为兜底（不裁切）。
      child: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              physics: const ClampingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: AppSpacing.loginFrameMaxWidth,
                    minHeight: constraints.maxHeight,
                  ),
                  child: IntrinsicHeight(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.loginFrameHorizontalPadding,
                        vertical: AppSpacing.loginFrameVerticalPadding,
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.max,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: <Widget>[
                          _LoginTopBar(
                            onDismiss: onDismiss,
                            allowGuestDismissPop: allowGuestDismissPop,
                          ),
                          const SizedBox(
                            height: AppSpacing.loginTopBarToHeroGap,
                          ),
                          LoginHeroBrand(
                            title: copy.title,
                            subtitle: copy.subtitle,
                          ),
                          const SizedBox(
                            height: AppSpacing.loginHeroToAccountGap,
                          ),
                          LoginAccountArea(
                            presentation: presentation,
                            phoneController: phoneController,
                            otpController: otpController,
                            onPhoneChanged: onPhoneChanged,
                            onOtpChanged: onOtpChanged,
                            onResendOtp: onResendOtp,
                          ),
                          if (_showsTopLevelError(presentation)) ...<Widget>[
                            const SizedBox(height: AppSpacing.sm),
                            // 入口级（returning/carrier）失败均为可恢复降级提示，用中性语气；
                            // 真正阻断态（锁定/封禁/注销）已路由到验证码面板按 phase 取红色。
                            _TopLevelErrorBanner(
                              message: presentation.message,
                              tone: LoginMessageTone.neutral,
                            ),
                          ],
                          const SizedBox(
                            height: AppSpacing.loginAccountToButtonGap,
                          ),
                          PrimaryLoginButton(
                            label: presentation.primaryLabel,
                            isSubmitting:
                                presentation.kind == LoginEntryKind.submitting,
                            enabled: presentation.canSubmit,
                            onPressed: onPrimary,
                          ),
                          const SizedBox(
                            height: AppSpacing.loginButtonToAgreementGap,
                          ),
                          LoginAgreementRow(
                            accepted: agreementAccepted,
                            onToggle: onAgreementToggle,
                            onAgreementTap: onAgreementTap,
                            onPrivacyTap: onPrivacyTap,
                          ),
                          const Spacer(),
                          const SizedBox(
                            height: AppSpacing.loginAgreementToOtherGap,
                          ),
                          OtherLoginMethodGrid(
                            onTap: onOtherMethod,
                            mode: presentation.kind == LoginEntryKind.phoneOtp
                                ? OtherLoginMethodMode.phoneOtp
                                : OtherLoginMethodMode.returning,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
    if (!isInline) {
      return content;
    }
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.loginPageBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: AppColors.webPcLoginSurfaceShadow,
            blurRadius: AppSpacing.webPcToolbarElevationBlurRadius,
            offset: Offset(AppSpacing.zero, AppSpacing.ten),
          ),
        ],
      ),
      child: content,
    );
  }
}

/// 顶层（非手机号输入）态的错误是否需要就近横幅展示。
/// phoneOtp 由 PhoneOtpPanel 内部自带 message，不在此重复。
bool _showsTopLevelError(LoginEntryPresentation presentation) {
  if (presentation.kind == LoginEntryKind.phoneOtp) {
    return false;
  }
  return presentation.message.trim().isNotEmpty;
}

class _TopLevelErrorBanner extends StatelessWidget {
  const _TopLevelErrorBanner({
    required this.message,
    this.tone = LoginMessageTone.neutral,
  });

  final String message;

  /// 顶层提示语气。一键/三方登录失败后的降级提示通常可恢复（中性/琥珀），
  /// 红色仅用于真正阻断态（此类已路由到验证码面板，几乎不会经此横幅）。
  final LoginMessageTone tone;

  @override
  Widget build(BuildContext context) {
    final color = loginMessageToneColor(context, tone);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.loginInputRadius),
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          height: AppSpacing.textLineHeightBody,
          color: color,
        ),
      ),
    );
  }
}

LoginReasonCopy _loginHeroCopyForPresentation(
  LoginEntryPresentation presentation,
  String? routeReason,
) {
  return switch (presentation.kind) {
    LoginEntryKind.returningAccount => LoginReasonCopy(
      title: UITextConstants.loginReturningHeroTitle,
      subtitle: presentation.oneTapCredentialAvailable
          ? UITextConstants.loginReturningHeroSubtitle
          : UITextConstants.loginSessionExpiredHint,
      source: LoginReasonCopySource.localSession,
    ),
    LoginEntryKind.carrierPhone => const LoginReasonCopy(
      title: UITextConstants.loginCarrierHeroTitle,
      subtitle: UITextConstants.loginCarrierHeroSubtitle,
      source: LoginReasonCopySource.cloudHint,
    ),
    _ => loginReasonCopyForName(routeReason),
  };
}

class LoginHeroBrand extends StatelessWidget {
  const LoginHeroBrand({
    super.key,
    required this.title,
    required this.subtitle,
  });

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Semantics(
          image: true,
          label: UITextConstants.loginBrandIconSemanticLabel,
          child: Container(
            width: AppSpacing.loginBrandMarkSize,
            height: AppSpacing.loginBrandMarkSize,
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(
                AppSpacing.loginBrandMarkRadius,
              ),
              boxShadow: const <BoxShadow>[
                BoxShadow(
                  color: AppColors.webPcLoginSurfaceShadow,
                  blurRadius: AppSpacing.ten,
                  offset: Offset(AppSpacing.zero, AppSpacing.six),
                ),
              ],
            ),
            child: CustomPaint(
              painter: WelcomeAppIconPainter(
                appearance: WelcomeAppearance.brandMark(),
              ),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.ten),
        Text(
          UITextConstants.loginBrandName,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosTitle3,
            fontWeight: AppTypography.bold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.loginBrandToTitleGap),
        Text(
          title,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            fontWeight: AppTypography.semiBold,
            height: AppTypography.lineHeightTight,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.six),
        Text(
          subtitle,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            height: AppSpacing.textLineHeightBody,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class LoginAccountArea extends StatelessWidget {
  const LoginAccountArea({
    super.key,
    required this.presentation,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onOtpChanged,
    required this.onResendOtp,
  });

  final LoginEntryPresentation presentation;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResendOtp;

  @override
  Widget build(BuildContext context) {
    final child = switch (presentation.kind) {
      LoginEntryKind.returningAccount => ReturningAccountPanel(
        hint: presentation.accountHint ?? presentation.carrierHint?.accountHint,
      ),
      LoginEntryKind.carrierPhone => CarrierPhonePanel(
        hint: presentation.carrierHint,
      ),
      LoginEntryKind.phoneOtp => PhoneOtpPanel(
        state: presentation.phoneOtpState ?? const LoginPhoneOtpState.idle(),
        phoneController: phoneController,
        otpController: otpController,
        onPhoneChanged: onPhoneChanged,
        onOtpChanged: onOtpChanged,
        onResend: onResendOtp,
      ),
      LoginEntryKind.resolving ||
      LoginEntryKind.submitting => const _ResolvingPanel(),
      LoginEntryKind.error => UnavailablePanel(message: presentation.message),
      LoginEntryKind.unavailable => UnavailablePanel(
        message: presentation.message,
      ),
    };
    final areaHeight = _heightForPresentation(presentation);
    if (areaHeight == null) {
      return child;
    }
    return SizedBox(height: areaHeight, child: child);
  }

  double? _heightForPresentation(LoginEntryPresentation presentation) {
    if (presentation.kind == LoginEntryKind.phoneOtp) {
      return null;
    }
    return AppSpacing.loginAccountAreaHeight;
  }
}

class ReturningAccountPanel extends StatelessWidget {
  const ReturningAccountPanel({super.key, required this.hint});

  final LoginAccountHint? hint;

  @override
  Widget build(BuildContext context) {
    final displayName = hint?.displayName.isNotEmpty == true
        ? hint!.displayName
        : UITextConstants.loginReturningDefaultName;
    final maskedPhone = hint?.maskedPhone ?? '';
    return Column(
      key: const ValueKey<String>('returningAccount'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        _Avatar(avatarUrl: hint?.avatarUrl ?? '', displayName: displayName),
        const SizedBox(height: AppSpacing.sm),
        Text(
          displayName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.xl,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          maskedPhone.isEmpty
              ? UITextConstants.loginReturningDefaultAccount
              : maskedPhone,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class CarrierPhonePanel extends StatelessWidget {
  const CarrierPhonePanel({super.key, required this.hint});

  final CarrierPhoneHint? hint;

  @override
  Widget build(BuildContext context) {
    final phone = hint?.maskedPhone ?? '';
    return Column(
      key: const ValueKey<String>('carrierPhone'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        Text(
          phone.isEmpty ? UITextConstants.loginCarrierDefaultPhone : phone,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosProfileTitle,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          UITextConstants.loginCarrierCreateHint,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class PhoneOtpPanel extends StatelessWidget {
  const PhoneOtpPanel({
    super.key,
    required this.state,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onOtpChanged,
    required this.onResend,
  });

  final LoginPhoneOtpState state;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResend;

  @override
  Widget build(BuildContext context) {
    final showsCode = state._showsCode || state.code.isNotEmpty;
    final message = _messageForState();
    return AutofillGroup(
      child: Column(
        key: const ValueKey<String>('phoneOtp-panel'),
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          PhoneNumberField(
            controller: phoneController,
            enabled: state.isPhoneEditable,
            hasError: state.phase == LoginPhoneOtpPhase.invalid,
            onChanged: onPhoneChanged,
          ),
          if (showsCode) ...<Widget>[
            const SizedBox(height: AppSpacing.ten),
            Text(
              _otpSentLine(),
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            const SizedBox(height: AppSpacing.ten),
            OtpCodeBoxes(
              controller: otpController,
              enabled: !state.isCodeDisabled,
              hasError: state.phase == LoginPhoneOtpPhase.codeError,
              onChanged: onOtpChanged,
            ),
            const SizedBox(height: AppSpacing.sm),
            _OtpResendAction(
              resendSeconds: state.resendSeconds,
              enabled: state.canSendCode,
              onResend: onResend,
            ),
          ],
          if (message.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: loginMessageToneColor(
                  context,
                  loginMessageToneForPhase(state.phase),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _messageForState() {
    if (state.phase == LoginPhoneOtpPhase.success) {
      return UITextConstants.loginRedirecting;
    }
    if (state.message.isNotEmpty) {
      return state.message;
    }
    // 兜底文案：异常/过渡态在 state.message 缺失时（例如纯构造或离线）仍给出
    // 明确、可指引下一步的提示，杜绝空白提示导致用户不知所措。
    return switch (state.phase) {
      LoginPhoneOtpPhase.editing => UITextConstants.loginPhoneRequired,
      LoginPhoneOtpPhase.invalid => UITextConstants.loginPhoneInvalid,
      LoginPhoneOtpPhase.sendingCode => UITextConstants.loginSendOtpSubmitting,
      LoginPhoneOtpPhase.codeError => UITextConstants.loginOtpMismatch,
      LoginPhoneOtpPhase.codeExpired => UITextConstants.loginOtpExpired,
      LoginPhoneOtpPhase.rateLimited =>
        UITextConstants.loginOtpRateLimited.replaceFirst(
          '%d',
          '${state.resendSeconds > 0 ? state.resendSeconds : 60}',
        ),
      LoginPhoneOtpPhase.sendFailed => UITextConstants.loginOtpSendFailed,
      LoginPhoneOtpPhase.loginLocked => UITextConstants.loginPhoneLoginLocked,
      LoginPhoneOtpPhase.accountSuspended =>
        UITextConstants.loginAccountSuspended,
      LoginPhoneOtpPhase.accountDeleted => UITextConstants.loginAccountDeleted,
      _ => '',
    };
  }

  String _otpSentLine() {
    final maskedPhone = state.maskedPhone.isEmpty
        ? _maskPhone(state.phone)
        : state.maskedPhone;
    final base = UITextConstants.loginOtpSentTo.replaceFirst('%s', maskedPhone);
    if (state.debugCode.isEmpty) {
      return base;
    }
    return '$base  ${UITextConstants.loginOtpDebugCodePrefix}${state.debugCode}';
  }
}
