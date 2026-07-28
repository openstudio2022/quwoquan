part of 'login_page.dart';

class LoginFrame extends StatelessWidget {
  const LoginFrame({
    super.key,
    required this.reason,
    required this.presentation,
    required this.agreementAccepted,
    required this.showAgreementError,
    required this.socialMethodAvailability,
    required this.socialMethodFeedback,
    required this.onAgreementToggle,
    required this.onDismiss,
    required this.onPrimary,
    required this.onAgreementTap,
    required this.onPrivacyTap,
    required this.onOtherMethod,
    required this.phoneController,
    required this.otpController,
    required this.onPhoneChanged,
    required this.onPhoneEditingComplete,
    required this.onOtpChanged,
    required this.onResendOtp,
    required this.onChangePhone,
    this.dismissPolicy = LoginDismissPolicy.popPrevious,
    this.isInline = false,
  });

  final String? reason;
  final LoginEntryPresentation presentation;
  final bool agreementAccepted;
  final bool showAgreementError;
  final Map<String, NativeAuthCapability> socialMethodAvailability;
  final String socialMethodFeedback;
  final VoidCallback onAgreementToggle;
  final VoidCallback onDismiss;
  final VoidCallback onPrimary;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;
  final ValueChanged<String> onOtherMethod;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final VoidCallback onPhoneEditingComplete;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResendOtp;
  final VoidCallback onChangePhone;

  /// 导航语义由入口决定；错误状态不得改变返回或关闭图标。
  final LoginDismissPolicy dismissPolicy;
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
                            dismissPolicy: dismissPolicy,
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
                            onPhoneEditingComplete: onPhoneEditingComplete,
                            onOtpChanged: onOtpChanged,
                            onResendOtp: onResendOtp,
                            onChangePhone: onChangePhone,
                          ),
                          if (_showsProcessFeedback(presentation)) ...<Widget>[
                            const SizedBox(height: AppSpacing.sm),
                            _TopLevelErrorBanner(
                              message:
                                  presentation.feedback?.message ??
                                  presentation.message,
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
                            showError: showAgreementError,
                            onToggle: onAgreementToggle,
                            onAgreementTap: onAgreementTap,
                            onPrivacyTap: onPrivacyTap,
                          ),
                          const Spacer(),
                          const SizedBox(
                            height: AppSpacing.loginAgreementToOtherGap,
                          ),
                          if (socialMethodFeedback
                              .trim()
                              .isNotEmpty) ...<Widget>[
                            AppFormErrorCard(
                              key: const ValueKey<String>(
                                'login-social-method-feedback',
                              ),
                              semantic: UiErrorSemantic(
                                category: UiErrorCategory.submit,
                                scope: UiErrorScope.form,
                                title: '',
                                message: socialMethodFeedback,
                                presentation:
                                    UiErrorPresentation.formInlineCard,
                              ),
                              density: AppFormErrorCardDensity.compact,
                            ),
                            const SizedBox(height: AppSpacing.sm),
                          ],
                          OtherLoginMethodGrid(
                            onTap: onOtherMethod,
                            enabled:
                                presentation.kind != LoginEntryKind.submitting,
                            availableMethods: socialMethodAvailability,
                            excludedMethod:
                                presentation.resolvedPrimaryAction ==
                                    LoginPrimaryAction.socialReauth
                                ? presentation.primaryProvider
                                : '',
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

/// 历史会话与一键登录失败共用 Account Area 下方的唯一流程反馈槽。
bool _showsProcessFeedback(LoginEntryPresentation presentation) {
  final feedback = presentation.feedback;
  final message = feedback?.message ?? presentation.message;
  if (message.trim().isEmpty || feedback?.isSilent == true) {
    return false;
  }
  return feedback == null ||
      feedback.surface == LoginErrorSurface.topLevel ||
      feedback.surface == LoginErrorSurface.fallbackNotice;
}

class _TopLevelErrorBanner extends StatelessWidget {
  const _TopLevelErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return AppFormErrorCard(
      key: const ValueKey<String>('login-process-feedback'),
      semantic: UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.form,
        title: '',
        message: message,
        presentation: UiErrorPresentation.formInlineCard,
      ),
      density: AppFormErrorCardDensity.compact,
    );
  }
}

LoginReasonCopy _loginHeroCopyForPresentation(
  LoginEntryPresentation presentation,
  String? routeReason,
) {
  return loginReasonCopyForName(routeReason);
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
          label: FoundationText.loginBrandIconSemanticLabel,
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
          FoundationText.loginBrandName,
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
    required this.onPhoneEditingComplete,
    required this.onOtpChanged,
    required this.onResendOtp,
    required this.onChangePhone,
  });

  final LoginEntryPresentation presentation;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final VoidCallback onPhoneEditingComplete;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResendOtp;
  final VoidCallback onChangePhone;

  @override
  Widget build(BuildContext context) {
    final child = switch (presentation.kind) {
      LoginEntryKind.returningAccount => ReturningAccountPanel(
        hint: presentation.accountHint ?? presentation.carrierHint?.accountHint,
      ),
      LoginEntryKind.carrierPhone => CarrierPhonePanel(
        hint: presentation.carrierHint,
      ),
      LoginEntryKind.phoneOtp =>
        (presentation.phoneOtpState?.isBlocked ?? false)
            ? AccountBlockedPanel(
                state:
                    presentation.phoneOtpState ??
                    const LoginPhoneOtpState.idle(),
              )
            : PhoneOtpPanel(
                state:
                    presentation.phoneOtpState ??
                    const LoginPhoneOtpState.idle(),
                phoneController: phoneController,
                otpController: otpController,
                onPhoneChanged: onPhoneChanged,
                onPhoneEditingComplete: onPhoneEditingComplete,
                onOtpChanged: onOtpChanged,
                onResend: onResendOtp,
                onChangePhone: onChangePhone,
              ),
      LoginEntryKind.submitting => _submittingPanel(),
      LoginEntryKind.resolving => const _ResolvingPanel(),
    };
    final areaHeight = _heightForPresentation(presentation);
    if (areaHeight == null) {
      return child;
    }
    return SizedBox(height: areaHeight, child: child);
  }

  Widget _submittingPanel() {
    if (presentation.accountHint != null) {
      return ReturningAccountPanel(hint: presentation.accountHint);
    }
    if (presentation.carrierHint != null) {
      return CarrierPhonePanel(hint: presentation.carrierHint);
    }
    if (presentation.phoneOtpState != null) {
      return PhoneOtpPanel(
        state: presentation.phoneOtpState!,
        phoneController: phoneController,
        otpController: otpController,
        onPhoneChanged: onPhoneChanged,
        onPhoneEditingComplete: onPhoneEditingComplete,
        onOtpChanged: onOtpChanged,
        onResend: onResendOtp,
        onChangePhone: onChangePhone,
      );
    }
    return const _ResolvingPanel();
  }

  double? _heightForPresentation(LoginEntryPresentation presentation) {
    if (presentation.kind == LoginEntryKind.phoneOtp) {
      return null;
    }
    return AppSpacing.loginAccountAreaHeight;
  }
}

class AccountBlockedPanel extends StatelessWidget {
  const AccountBlockedPanel({super.key, required this.state});

  final LoginPhoneOtpState state;

  @override
  Widget build(BuildContext context) {
    return AppFormErrorCard(
      key: const ValueKey<String>('loginAccountBlocked'),
      semantic: UiErrorSemantic(
        category: UiErrorCategory.validation,
        scope: UiErrorScope.form,
        title: '',
        message: state.message,
        presentation: UiErrorPresentation.formInlineCard,
      ),
    );
  }
}

class ReturningAccountPanel extends StatelessWidget {
  const ReturningAccountPanel({super.key, required this.hint});

  final LoginAccountHint? hint;

  @override
  Widget build(BuildContext context) {
    final displayName =
        hint?.nicknameCustomized == true && hint?.displayName.isNotEmpty == true
        ? hint!.displayName
        : FoundationText.loginReturningDefaultName;
    final maskedPhone = hint?.maskedPhone ?? '';
    return Column(
      key: const ValueKey<String>('returningAccount'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        _Avatar(avatarUrl: hint?.avatarUrl ?? ''),
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
        if (maskedPhone.isNotEmpty) ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          Text(
            maskedPhone,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
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
          phone.isEmpty ? FoundationText.loginCarrierDefaultPhone : phone,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosProfileTitle,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          FoundationText.loginCarrierCreateHint,
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
    required this.onChangePhone,
    this.onPhoneEditingComplete,
  });

  final LoginPhoneOtpState state;
  final TextEditingController phoneController;
  final TextEditingController otpController;
  final ValueChanged<String> onPhoneChanged;
  final ValueChanged<String> onOtpChanged;
  final VoidCallback onResend;
  final VoidCallback onChangePhone;
  final VoidCallback? onPhoneEditingComplete;

  @override
  Widget build(BuildContext context) {
    final showsDestination = state.otpWasDelivered;
    final showsCode = state._showsCode || state.code.isNotEmpty;
    final fieldError = _fieldErrorForState();
    final statusMessage = _statusMessageForState();
    final formError = _formErrorForState();
    return AutofillGroup(
      child: Column(
        key: const ValueKey<String>('phoneOtp-panel'),
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          if (!showsDestination)
            PhoneNumberField(
              controller: phoneController,
              enabled: state.isPhoneEditable,
              hasError: state.phase == LoginPhoneOtpPhase.invalid,
              onChanged: onPhoneChanged,
              onEditingComplete: onPhoneEditingComplete,
            )
          else
            _OtpDestinationSummary(
              message: _otpSentLine(),
              onChangePhone: onChangePhone,
            ),
          if (!showsDestination &&
              state.phase == LoginPhoneOtpPhase.invalid &&
              fieldError.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Align(
              alignment: Alignment.centerLeft,
              child: AppInlineFieldError(message: fieldError),
            ),
          ],
          if (showsCode) ...<Widget>[
            const SizedBox(height: AppSpacing.ten),
            OtpCodeBoxes(
              controller: otpController,
              enabled: !state.isCodeDisabled,
              hasError: state.phase == LoginPhoneOtpPhase.codeError,
              onChanged: onOtpChanged,
            ),
            if (state.phase == LoginPhoneOtpPhase.codeError &&
                fieldError.isNotEmpty) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Align(
                alignment: Alignment.centerLeft,
                child: AppInlineFieldError(message: fieldError),
              ),
            ],
            const SizedBox(height: AppSpacing.sm),
            _OtpResendAction(
              resendSeconds: state.resendSeconds,
              enabled: state.canSendCode,
              onResend: onResend,
            ),
          ],
          if (formError != null) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            AppFormErrorCard(
              key: const ValueKey<String>('login-phone-form-error'),
              semantic: formError,
              density: AppFormErrorCardDensity.compact,
            ),
          ] else if (statusMessage.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              statusMessage,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _fieldErrorForState() {
    if (state.phase != LoginPhoneOtpPhase.invalid &&
        state.phase != LoginPhoneOtpPhase.codeError) {
      return '';
    }
    if (state.message.isNotEmpty) return state.message;
    return state.phase == LoginPhoneOtpPhase.invalid
        ? FoundationText.loginPhoneInvalid
        : FoundationText.loginOtpMismatch;
  }

  String _statusMessageForState() {
    if (state.phase == LoginPhoneOtpPhase.success) {
      return FoundationText.loginRedirecting;
    }
    return state.phase == LoginPhoneOtpPhase.sendingCode
        ? FoundationText.loginSendOtpSubmitting
        : '';
  }

  UiErrorSemantic? _formErrorForState() {
    final isFormError = switch (state.phase) {
      LoginPhoneOtpPhase.sendFailed ||
      LoginPhoneOtpPhase.rateLimited ||
      LoginPhoneOtpPhase.codeExpired ||
      LoginPhoneOtpPhase.loginLocked ||
      LoginPhoneOtpPhase.accountSuspended ||
      LoginPhoneOtpPhase.accountDeleted => true,
      _ => false,
    };
    if (!isFormError) return null;
    final fallback = switch (state.phase) {
      LoginPhoneOtpPhase.rateLimited => FoundationText.loginOtpRateLimited,
      LoginPhoneOtpPhase.codeExpired => FoundationText.loginOtpExpired,
      LoginPhoneOtpPhase.loginLocked => FoundationText.loginPhoneLoginLocked,
      LoginPhoneOtpPhase.accountSuspended =>
        FoundationText.loginAccountSuspended,
      LoginPhoneOtpPhase.accountDeleted => FoundationText.loginAccountDeleted,
      _ => FoundationText.loginOtpSendFailed,
    };
    return UiErrorSemantic(
      category: state.phase == LoginPhoneOtpPhase.rateLimited
          ? UiErrorCategory.rateLimited
          : UiErrorCategory.submit,
      scope: UiErrorScope.form,
      title: '',
      message: state.message.isEmpty ? fallback : state.message,
      presentation: UiErrorPresentation.formInlineCard,
    );
  }

  String _otpSentLine() {
    final maskedPhone = state.maskedPhone.isEmpty
        ? _maskPhone(state.phone)
        : state.maskedPhone;
    final base = FoundationText.loginOtpSentTo.replaceFirst('%s', maskedPhone);
    return base;
  }
}

class _OtpDestinationSummary extends StatelessWidget {
  const _OtpDestinationSummary({
    required this.message,
    required this.onChangePhone,
  });

  final String message;
  final VoidCallback onChangePhone;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        Flexible(
          child: Text(
            message,
            key: const ValueKey<String>('loginOtpDestinationSummary'),
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.xs),
        CupertinoButton(
          key: const ValueKey<String>('loginChangePhoneAction'),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
          minimumSize: const Size(
            AppSpacing.minInteractiveSize,
            AppSpacing.minInteractiveSize,
          ),
          onPressed: onChangePhone,
          child: const Text(FoundationText.loginPhoneChange),
        ),
      ],
    );
  }
}
