part of 'login_page.dart';

/// 重发验证码动作：倒计时进行中显示禁用倒计时文案；倒计时结束且可发码时
/// 显示可点击的"重新获取"，让用户在任何"想换一份验证码"的态下都有明确出口。
class _OtpResendAction extends StatelessWidget {
  const _OtpResendAction({
    required this.resendSeconds,
    required this.enabled,
    required this.onResend,
  });

  final int resendSeconds;
  final bool enabled;
  final VoidCallback onResend;

  @override
  Widget build(BuildContext context) {
    final counting = resendSeconds > 0;
    final label = counting
        ? UITextConstants.loginOtpResendCountdown.replaceFirst(
            '%d',
            '$resendSeconds',
          )
        : UITextConstants.loginOtpResend;
    final canTap = enabled && !counting;
    return Semantics(
      button: true,
      enabled: canTap,
      label: UITextConstants.loginOtpResend,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: canTap ? onResend : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          child: Text(
            label,
            key: const ValueKey<String>('loginOtpResendAction'),
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: canTap
                  ? AppColors.iosAccent(context)
                  : AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
      ),
    );
  }
}

class PhoneNumberField extends StatefulWidget {
  const PhoneNumberField({
    super.key,
    required this.controller,
    required this.enabled,
    required this.hasError,
    required this.onChanged,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool hasError;
  final ValueChanged<String> onChanged;

  @override
  State<PhoneNumberField> createState() => _PhoneNumberFieldState();
}

class _LoginInputDecorationSpec {
  const _LoginInputDecorationSpec({
    required this.surface,
    required this.border,
    required this.borderWidth,
    required this.shadow,
  });

  final Color surface;
  final Color border;
  final double borderWidth;
  final List<BoxShadow> shadow;
}

_LoginInputDecorationSpec _loginInputDecorationForState(
  BuildContext context, {
  required bool focused,
  required bool hasError,
  bool enabled = true,
}) {
  final border = hasError
      ? AppColors.iosDestructive(context)
      : focused
      ? AppColors.loginInputFocusedBorder(context)
      : AppColors.loginInputBorder(context);
  return _LoginInputDecorationSpec(
    surface: AppColors.loginInputSurface(context),
    border: border,
    borderWidth: focused || hasError ? AppSpacing.oneHalf : AppSpacing.one,
    shadow: <BoxShadow>[
      if (focused && enabled)
        BoxShadow(
          color: AppColors.loginInputFocusedBorder(
            context,
          ).withValues(alpha: 0.10),
          blurRadius: AppSpacing.ten,
          offset: const Offset(AppSpacing.zero, AppSpacing.three),
        ),
    ],
  );
}

class _PhoneNumberFieldState extends State<PhoneNumberField> {
  late final FocusNode _focusNode;
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode();
    _focusNode.addListener(_handleFocusChanged);
  }

  @override
  void dispose() {
    _focusNode.removeListener(_handleFocusChanged);
    _focusNode.dispose();
    super.dispose();
  }

  void _handleFocusChanged() {
    if (mounted) {
      setState(() => _focused = _focusNode.hasFocus);
    }
  }

  @override
  Widget build(BuildContext context) {
    final decoration = _loginInputDecorationForState(
      context,
      focused: _focused,
      hasError: widget.hasError,
      enabled: widget.enabled,
    );
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.enabled ? () => _focusNode.requestFocus() : null,
      child: Container(
        height: AppSpacing.loginPhoneFieldHeight,
        decoration: BoxDecoration(
          color: decoration.surface,
          borderRadius: BorderRadius.circular(AppSpacing.loginInputRadius),
          border: Border.all(
            color: decoration.border,
            width: decoration.borderWidth,
          ),
          boxShadow: decoration.shadow,
        ),
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Row(
          children: <Widget>[
            Text(
              '+86',
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosLabel(context),
                fontWeight: AppTypography.semiBold,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Container(
              width: AppSpacing.one,
              height: AppSpacing.twenty,
              color: AppColors.iosSeparator(context),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: CupertinoTextField.borderless(
                controller: widget.controller,
                enabled: widget.enabled,
                focusNode: _focusNode,
                keyboardType: TextInputType.phone,
                autofillHints: const <String>[AutofillHints.telephoneNumber],
                placeholder: UITextConstants.loginPhoneNumberPlaceholder,
                inputFormatters: <TextInputFormatter>[
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(11),
                ],
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: widget.enabled
                      ? AppColors.iosLabel(context)
                      : AppColors.iosSecondaryLabel(context),
                ),
                placeholderStyle: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: AppColors.iosTertiaryLabel(context),
                ),
                onChanged: widget.onChanged,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class OtpCodeBoxes extends StatelessWidget {
  const OtpCodeBoxes({
    super.key,
    required this.controller,
    required this.enabled,
    required this.hasError,
    required this.onChanged,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool hasError;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return _OtpCodeBoxesBody(
      controller: controller,
      enabled: enabled,
      hasError: hasError,
      onChanged: onChanged,
    );
  }
}

class _OtpCodeBoxesBody extends StatefulWidget {
  const _OtpCodeBoxesBody({
    required this.controller,
    required this.enabled,
    required this.hasError,
    required this.onChanged,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool hasError;
  final ValueChanged<String> onChanged;

  @override
  State<_OtpCodeBoxesBody> createState() => _OtpCodeBoxesBodyState();
}

class _OtpCodeBoxesBodyState extends State<_OtpCodeBoxesBody> {
  late final FocusNode _focusNode;
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode();
    _focusNode.addListener(_handleFocusChanged);
  }

  @override
  void dispose() {
    _focusNode.removeListener(_handleFocusChanged);
    _focusNode.dispose();
    super.dispose();
  }

  void _handleFocusChanged() {
    if (mounted) {
      setState(() => _focused = _focusNode.hasFocus);
    }
  }

  @override
  Widget build(BuildContext context) {
    final decoration = _loginInputDecorationForState(
      context,
      focused: _focused,
      hasError: widget.hasError,
      enabled: widget.enabled,
    );
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.enabled ? () => _focusNode.requestFocus() : null,
      child: SizedBox(
        height: AppSpacing.loginOtpBoxSize,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            LayoutBuilder(
              builder: (context, constraints) {
                final defaultGap = AppSpacing.loginOtpBoxGap;
                final availableWidth = constraints.maxWidth.isFinite
                    ? constraints.maxWidth
                    : AppSpacing.loginOtpBoxSize * 6 + defaultGap * 5;
                final minimumBoxWidth = AppSpacing.loginOtpBoxMinSize * 6;
                // 窄宽度下优先压缩格间距，保证 6 格仍在同一行内且尽量维持 44x44 热区。
                final gap = availableWidth <= minimumBoxWidth
                    ? AppSpacing.zero
                    : ((availableWidth - minimumBoxWidth) / 5).clamp(
                        AppSpacing.zero,
                        defaultGap,
                      );
                final boxSize = ((availableWidth - gap * 5) / 6).clamp(
                  availableWidth >= minimumBoxWidth
                      ? AppSpacing.loginOtpBoxMinSize
                      : AppSpacing.zero,
                  AppSpacing.loginOtpBoxSize,
                );
                return Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: List<Widget>.generate(6, (index) {
                    final value = index < widget.controller.text.length
                        ? widget.controller.text[index]
                        : '';
                    return Padding(
                      padding: EdgeInsets.only(
                        right: index == 5 ? AppSpacing.zero : gap,
                      ),
                      child: Container(
                        width: boxSize,
                        height: boxSize,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: decoration.surface,
                          borderRadius: BorderRadius.circular(
                            AppSpacing.loginOtpBoxRadius,
                          ),
                          border: Border.all(
                            color: decoration.border,
                            width: decoration.borderWidth,
                          ),
                          boxShadow: decoration.shadow,
                        ),
                        child: Text(
                          value,
                          style: TextStyle(
                            fontSize: AppTypography.iosTitle3,
                            fontWeight: AppTypography.semiBold,
                            color: AppColors.iosLabel(context),
                          ),
                        ),
                      ),
                    );
                  }),
                );
              },
            ),
            Opacity(
              opacity: 0.01,
              child: SizedBox(
                height: AppSpacing.loginOtpBoxSize,
                child: CupertinoTextField.borderless(
                  controller: widget.controller,
                  enabled: widget.enabled,
                  focusNode: _focusNode,
                  autofocus: false,
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.done,
                  autofillHints: const <String>[AutofillHints.oneTimeCode],
                  enableInteractiveSelection: true,
                  inputFormatters: <TextInputFormatter>[
                    FilteringTextInputFormatter.digitsOnly,
                    LengthLimitingTextInputFormatter(6),
                  ],
                  onChanged: widget.onChanged,
                  onSubmitted: widget.onChanged,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class UnavailablePanel extends StatelessWidget {
  const UnavailablePanel({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const ValueKey<String>('unavailable'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        Icon(
          CupertinoIcons.device_phone_portrait,
          size: AppSpacing.forty,
          color: AppColors.iosSecondaryLabel(context),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          message.isEmpty ? UITextConstants.loginCarrierUnavailable : message,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosCallout,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class _ResolvingPanel extends StatelessWidget {
  const _ResolvingPanel();

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const ValueKey<String>('resolving'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        CupertinoActivityIndicator(color: AppColors.iosAccent(context)),
        const SizedBox(height: AppSpacing.loginOtherTitleToIconsGap),
        Text(
          UITextConstants.loginResolvingHint,
          style: TextStyle(
            fontSize: AppTypography.iosCallout,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.avatarUrl, required this.displayName});

  final String avatarUrl;
  final String displayName;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSpacing.loginAvatarSize,
      height: AppSpacing.loginAvatarSize,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: AppColors.iosAccent(context).withValues(alpha: 0.16),
      ),
      clipBehavior: Clip.antiAlias,
      alignment: Alignment.center,
      child: avatarUrl.isEmpty
          ? Text(
              displayName.isEmpty
                  ? UITextConstants.loginDefaultAvatarGlyph
                  : displayName.characters.first,
              style: TextStyle(
                fontSize: AppTypography.iosProfileTitle,
                fontWeight: AppTypography.bold,
                color: AppColors.iosAccent(context),
              ),
            )
          : AppAvatarImage(
              imageUrl: avatarUrl,
              size: AppSpacing.loginAvatarSize,
              fit: BoxFit.cover,
              errorWidget: Text(
                UITextConstants.loginDefaultAvatarGlyph,
                style: TextStyle(
                  fontSize: AppTypography.iosProfileTitle,
                  fontWeight: AppTypography.bold,
                  color: AppColors.iosAccent(context),
                ),
              ),
            ),
    );
  }
}

class PrimaryLoginButton extends StatelessWidget {
  const PrimaryLoginButton({
    super.key,
    required this.label,
    required this.isSubmitting,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final bool isSubmitting;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      enabled: enabled && !isSubmitting,
      label: label,
      child: CupertinoButton(
        minimumSize: const Size(
          AppSpacing.loginPrimaryButtonHeight,
          AppSpacing.loginPrimaryButtonHeight,
        ),
        padding: EdgeInsets.zero,
        color: enabled
            ? AppColors.iosAccent(context)
            : AppColors.loginPrimaryDisabled(context),
        disabledColor: AppColors.loginPrimaryDisabled(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
        onPressed: enabled && !isSubmitting ? onPressed : null,
        child: isSubmitting
            ? const CupertinoActivityIndicator(color: CupertinoColors.white)
            : Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: FontWeight.w600,
                  color: enabled
                      ? CupertinoColors.white
                      : CupertinoColors.white.withValues(alpha: 0.76),
                ),
              ),
      ),
    );
  }
}

class LoginAgreementRow extends StatelessWidget {
  const LoginAgreementRow({
    super.key,
    required this.accepted,
    required this.onToggle,
    required this.onAgreementTap,
    required this.onPrivacyTap,
  });

  final bool accepted;
  final VoidCallback onToggle;
  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.minInteractiveSize),
          onPressed: onToggle,
          child: Icon(
            accepted
                ? CupertinoIcons.check_mark_circled_solid
                : CupertinoIcons.circle,
            size: AppSpacing.twenty,
            color: accepted
                ? AppColors.iosAccent(context)
                : AppColors.iosSecondaryLabel(context),
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Wrap(
              children: <Widget>[
                Text(
                  UITextConstants.loginAgreementPrefix,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
                _AgreementLink(
                  label: UITextConstants.userAgreement,
                  onTap: onAgreementTap,
                ),
                Text(
                  UITextConstants.loginAgreementAnd,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
                _AgreementLink(
                  label: UITextConstants.privacyPolicy,
                  onTap: onPrivacyTap,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _AgreementLink extends StatelessWidget {
  const _AgreementLink({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.base,
          color: AppColors.iosAccent(context),
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }
}

enum OtherLoginMethodMode { returning, phoneOtp }

class OtherLoginMethodGrid extends StatelessWidget {
  const OtherLoginMethodGrid({
    super.key,
    required this.onTap,
    this.mode = OtherLoginMethodMode.phoneOtp,
  });

  final ValueChanged<String> onTap;
  final OtherLoginMethodMode mode;

  @override
  Widget build(BuildContext context) {
    final entries = mode == OtherLoginMethodMode.returning
        ? const <
            ({
              String id,
              IconData icon,
              Color background,
              Color iconColor,
              double iconSize,
              String label,
              String semanticLabel,
            })
          >[
            (
              id: 'wechat',
              icon: SimpleIcons.wechat,
              background: AppColors.loginMethodWechatBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodWechatFull,
              semanticLabel: UITextConstants.loginMethodWechatSemanticLabel,
            ),
            (
              id: 'qq',
              icon: SimpleIcons.qq,
              background: AppColors.loginMethodQqBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodQqFull,
              semanticLabel: UITextConstants.loginMethodQqSemanticLabel,
            ),
            (
              id: 'phone',
              icon: Icons.phone_iphone,
              background: AppColors.loginMethodPhoneCircle,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodPhoneFull,
              semanticLabel: UITextConstants.loginMethodPhoneSemanticLabel,
            ),
          ]
        : const <
            ({
              String id,
              IconData icon,
              Color background,
              Color iconColor,
              double iconSize,
              String label,
              String semanticLabel,
            })
          >[
            (
              id: 'phone',
              icon: Icons.phone_iphone,
              background: AppColors.loginMethodPhoneCircle,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodPhone,
              semanticLabel: UITextConstants.loginMethodPhoneSemanticLabel,
            ),
            (
              id: 'wechat',
              icon: SimpleIcons.wechat,
              background: AppColors.loginMethodWechatBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodWechat,
              semanticLabel: UITextConstants.loginMethodWechatSemanticLabel,
            ),
            (
              id: 'qq',
              icon: SimpleIcons.qq,
              background: AppColors.loginMethodQqBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodQq,
              semanticLabel: UITextConstants.loginMethodQqSemanticLabel,
            ),
            (
              id: 'alipay',
              icon: SimpleIcons.alipay,
              background: AppColors.loginMethodAlipayBrand,
              iconColor: AppColors.white,
              iconSize: AppSpacing.loginOtherMethodIconSize,
              label: UITextConstants.loginMethodAlipay,
              semanticLabel: UITextConstants.loginMethodAlipaySemanticLabel,
            ),
          ];
    return Column(
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Container(
                height: AppSpacing.one,
                color: AppColors.loginOtherDivider(context),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              child: Text(
                UITextConstants.loginOtherMethods,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ),
            Expanded(
              child: Container(
                height: AppSpacing.one,
                color: AppColors.loginOtherDivider(context),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        Align(
          alignment: Alignment.center,
          child: SizedBox(
            width: mode == OtherLoginMethodMode.returning
                ? AppSpacing.loginOtherMethodsThreeColumnWidth
                : double.infinity,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: entries
                  .map((entry) {
                    return Semantics(
                      button: true,
                      label: entry.semanticLabel,
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () => onTap(entry.id),
                        child: Column(
                          children: <Widget>[
                            Container(
                              width: AppSpacing.loginOtherMethodSize,
                              height: AppSpacing.loginOtherMethodSize,
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: entry.background,
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                entry.icon,
                                size: entry.iconSize,
                                color: entry.iconColor,
                              ),
                            ),
                            const SizedBox(height: AppSpacing.xs),
                            Text(
                              entry.label,
                              style: TextStyle(
                                fontSize: AppTypography.iosCaption1,
                                color: AppColors.iosSecondaryLabel(context),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  })
                  .toList(growable: false),
            ),
          ),
        ),
      ],
    );
  }
}
