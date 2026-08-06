part of 'login_page.dart';

Future<bool?> showLoginConsentSheet(
  BuildContext context, {
  required VoidCallback onAgreementTap,
  required VoidCallback onPrivacyTap,
}) {
  return showCupertinoModalPopup<bool>(
    context: context,
    barrierDismissible: true,
    builder: (sheetContext) {
      return DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.iosSystemBackground(sheetContext),
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(AppSpacing.radiusTen),
          ),
        ),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.sm,
              AppSpacing.lg,
              AppSpacing.md,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Container(
                  width: AppSpacing.forty,
                  height: AppSpacing.three,
                  decoration: BoxDecoration(
                    color: AppColors.iosTertiaryLabel(sheetContext),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
                  ),
                ),
                const SizedBox(height: AppSpacing.lg),
                Text(
                  FoundationText.loginConsentSheetTitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.iosLabel(sheetContext),
                    fontSize: AppTypography.iosTitle3,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  FoundationText.loginConsentSheetSubtitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.iosSecondaryLabel(sheetContext),
                    fontSize: AppTypography.base,
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                _AgreementLinks(
                  onAgreementTap: onAgreementTap,
                  onPrivacyTap: onPrivacyTap,
                ),
                const SizedBox(height: AppSpacing.lg),
                LoginActionButton(
                  key: const ValueKey<String>('loginConsentConfirm'),
                  label: FoundationText.loginConsentSheetConfirm,
                  onPressed: () => Navigator.of(sheetContext).pop(true),
                ),
                CupertinoButton(
                  key: const ValueKey<String>('loginConsentCancel'),
                  onPressed: () => Navigator.of(sheetContext).pop(false),
                  child: Text(
                    FoundationText.loginConsentSheetCancel,
                    style: TextStyle(color: AppColors.iosAccent(sheetContext)),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    },
  );
}

class LoginActionButton extends StatelessWidget {
  const LoginActionButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.enabled = true,
    this.busy = false,
    this.outlined = false,
  });

  final String label;
  final VoidCallback onPressed;
  final bool enabled;
  final bool busy;
  final bool outlined;

  @override
  Widget build(BuildContext context) {
    final canPress = enabled && !busy;
    final accent = AppColors.iosAccent(context);
    final foreground = outlined
        ? canPress
              ? accent
              : AppColors.iosSecondaryLabel(context)
        : AppColors.white;
    final background = outlined
        ? AppColors.transparent
        : canPress
        ? accent
        : AppColors.loginPrimaryDisabled(context);
    return Semantics(
      button: true,
      enabled: canPress,
      label: label,
      child: SizedBox(
        width: double.infinity,
        height: AppSpacing.loginPrimaryButtonHeight,
        child: DecoratedBox(
          decoration: BoxDecoration(
            border: outlined
                ? Border.all(
                    color: canPress
                        ? accent
                        : AppColors.loginInputBorder(context),
                  )
                : null,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
          ),
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
            color: background,
            disabledColor: background,
            onPressed: canPress ? onPressed : null,
            child: Stack(
              alignment: Alignment.center,
              children: <Widget>[
                AnimatedOpacity(
                  opacity: busy ? 0 : 1,
                  duration: const Duration(milliseconds: 120),
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: canPress || outlined
                          ? foreground
                          : AppColors.white.withValues(alpha: 0.72),
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
                if (busy)
                  AppRequestFeedback.inline(
                    indicatorColor: outlined ? accent : AppColors.white,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LoginPhoneField extends StatelessWidget {
  const LoginPhoneField({
    super.key,
    required this.controller,
    required this.enabled,
    required this.onChanged,
    required this.onEditingComplete,
  });

  final TextEditingController controller;
  final bool enabled;
  final ValueChanged<String> onChanged;
  final VoidCallback onEditingComplete;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      textField: true,
      label: FoundationText.loginPhoneNumberPlaceholder,
      child: Container(
        height: AppSpacing.loginPhoneFieldHeight,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.loginInputSurface(context),
          border: Border.all(color: AppColors.loginInputBorder(context)),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: Row(
          children: <Widget>[
            Text(
              '+86',
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.lg,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Icon(
              CupertinoIcons.chevron_down,
              size: AppTypography.xs,
              color: AppColors.iosSecondaryLabel(context),
            ),
            const SizedBox(width: AppSpacing.md),
            Container(
              width: AppSpacing.one,
              height: AppSpacing.twenty,
              color: AppColors.iosSeparator(context),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: CupertinoTextField(
                key: const ValueKey<String>('loginPhoneField'),
                controller: controller,
                enabled: enabled,
                decoration: null,
                padding: EdgeInsets.zero,
                placeholder: FoundationText.loginPhoneNumberPlaceholder,
                placeholderStyle: TextStyle(
                  color: AppColors.iosTertiaryLabel(context),
                  fontSize: AppTypography.lg,
                ),
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.lg,
                ),
                keyboardType: TextInputType.phone,
                textInputAction: TextInputAction.done,
                autofillHints: const <String>[AutofillHints.telephoneNumber],
                inputFormatters: <TextInputFormatter>[
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(11),
                ],
                onChanged: onChanged,
                onEditingComplete: onEditingComplete,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class OtpCodeBoxes extends StatefulWidget {
  const OtpCodeBoxes({
    super.key,
    required this.controller,
    required this.enabled,
    required this.onChanged,
    required this.focusRequestSerial,
    required this.shakeSerial,
  });

  final TextEditingController controller;
  final bool enabled;
  final ValueChanged<String> onChanged;
  final int focusRequestSerial;
  final int shakeSerial;

  @override
  State<OtpCodeBoxes> createState() => _OtpCodeBoxesState();
}

class _OtpCodeBoxesState extends State<OtpCodeBoxes>
    with SingleTickerProviderStateMixin {
  late final FocusNode _focusNode;
  late final AnimationController _shakeController;
  late final Animation<double> _shakeOffset;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode();
    _shakeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 280),
    );
    _shakeOffset = TweenSequence<double>(<TweenSequenceItem<double>>[
      TweenSequenceItem(tween: Tween(begin: 0, end: -6), weight: 1),
      TweenSequenceItem(tween: Tween(begin: -6, end: 6), weight: 2),
      TweenSequenceItem(tween: Tween(begin: 6, end: -4), weight: 2),
      TweenSequenceItem(tween: Tween(begin: -4, end: 4), weight: 2),
      TweenSequenceItem(tween: Tween(begin: 4, end: 0), weight: 1),
    ]).animate(_shakeController);
    _scheduleFocus();
  }

  @override
  void didUpdateWidget(covariant OtpCodeBoxes oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.focusRequestSerial != widget.focusRequestSerial &&
        widget.enabled) {
      _scheduleFocus();
    }
    if (oldWidget.shakeSerial != widget.shakeSerial &&
        !(MediaQuery.maybeOf(context)?.disableAnimations ?? false)) {
      _shakeController.forward(from: 0);
    }
  }

  void _scheduleFocus() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && widget.enabled) _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _focusNode.dispose();
    _shakeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final code = widget.controller.text;
    final activeIndex = widget.enabled ? code.length.clamp(0, 5) : -1;
    return Semantics(
      textField: true,
      label: FoundationText.loginOtpPlaceholder,
      value: '${code.length}/6',
      child: AnimatedBuilder(
        animation: _shakeOffset,
        builder: (context, child) => Transform.translate(
          offset: Offset(_shakeOffset.value, 0),
          child: child,
        ),
        child: SizedBox(
          height: AppSpacing.loginOtpBoxSize,
          child: Stack(
            children: <Widget>[
              Row(
                children: List<Widget>.generate(6, (index) {
                  final digit = index < code.length ? code[index] : '';
                  return Expanded(
                    child: Padding(
                      padding: EdgeInsets.only(
                        right: index == 5 ? 0 : AppSpacing.loginOtpBoxGap,
                      ),
                      child: Container(
                        key: ValueKey<String>('loginOtpBox$index'),
                        height: AppSpacing.loginOtpBoxSize,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: AppColors.loginInputSurface(context),
                          border: Border.all(
                            color: index == activeIndex
                                ? AppColors.loginInputFocusedBorder(context)
                                : AppColors.loginInputBorder(context),
                            width: index == activeIndex
                                ? AppSpacing.two
                                : AppSpacing.one,
                          ),
                          borderRadius: BorderRadius.circular(
                            AppSpacing.radiusTen,
                          ),
                        ),
                        child: Text(
                          digit,
                          style: TextStyle(
                            color: AppColors.iosLabel(context),
                            fontSize: AppTypography.xl,
                            fontWeight: AppTypography.medium,
                          ),
                        ),
                      ),
                    ),
                  );
                }),
              ),
              Positioned.fill(
                child: Opacity(
                  opacity: 0.01,
                  child: CupertinoTextField(
                    key: const ValueKey<String>('loginOtpHiddenField'),
                    controller: widget.controller,
                    focusNode: _focusNode,
                    enabled: widget.enabled,
                    decoration: null,
                    keyboardType: TextInputType.number,
                    textInputAction: TextInputAction.done,
                    autofillHints: const <String>[AutofillHints.oneTimeCode],
                    inputFormatters: <TextInputFormatter>[
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(6),
                    ],
                    onChanged: widget.onChanged,
                  ),
                ),
              ),
            ],
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
    return Semantics(
      checked: accepted,
      button: true,
      label: FoundationText.loginAgreementRequired,
      child: Wrap(
        alignment: WrapAlignment.center,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xs,
        children: <Widget>[
          GestureDetector(
            onTap: onToggle,
            behavior: HitTestBehavior.opaque,
            child: SizedBox(
              width: AppSpacing.minInteractiveSize,
              height: AppSpacing.minInteractiveSize,
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
          ),
          _AgreementLinks(
            onAgreementTap: onAgreementTap,
            onPrivacyTap: onPrivacyTap,
          ),
        ],
      ),
    );
  }
}

class _AgreementLinks extends StatelessWidget {
  const _AgreementLinks({
    required this.onAgreementTap,
    required this.onPrivacyTap,
  });

  final VoidCallback onAgreementTap;
  final VoidCallback onPrivacyTap;

  @override
  Widget build(BuildContext context) {
    final base = TextStyle(
      color: AppColors.iosSecondaryLabel(context),
      fontSize: AppTypography.iosCaption1,
    );
    final link = base.copyWith(color: AppColors.iosAccent(context));
    return Text.rich(
      TextSpan(
        style: base,
        children: <InlineSpan>[
          const TextSpan(text: FoundationText.loginAgreementPrefix),
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size.square(AppSpacing.minInteractiveSize),
              onPressed: onAgreementTap,
              child: Text(FoundationText.userAgreement, style: link),
            ),
          ),
          const TextSpan(text: FoundationText.loginAgreementAnd),
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size.square(AppSpacing.minInteractiveSize),
              onPressed: onPrivacyTap,
              child: Text(FoundationText.privacyPolicy, style: link),
            ),
          ),
        ],
      ),
      textAlign: TextAlign.center,
    );
  }
}

class LoginMethodFooter extends StatelessWidget {
  const LoginMethodFooter({
    super.key,
    required this.onTap,
    required this.availableMethods,
    this.disabledProvider = '',
  });

  final ValueChanged<String> onTap;
  final Map<String, NativeAuthCapability> availableMethods;
  final String disabledProvider;

  @override
  Widget build(BuildContext context) {
    const methods = <String>['wechat', 'qq', 'alipay'];
    return Container(
      key: const ValueKey<String>('loginMethodFooter'),
      width: double.infinity,
      constraints: const BoxConstraints(minHeight: 132),
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.sm,
        AppSpacing.lg,
        AppSpacing.sm,
      ),
      color: AppColors.loginPageBackground(context),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: AppSpacing.loginFrameMaxWidth,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
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
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                    ),
                    child: Text(
                      FoundationText.loginOtherMethods,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: AppColors.iosSecondaryLabel(context),
                        fontSize: AppTypography.iosFootnote,
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
              const SizedBox(height: AppSpacing.sm),
              Row(
                children: methods
                    .map((method) {
                      final capability = availableMethods[method];
                      final current = disabledProvider == method;
                      final enabled =
                          capability?.isAvailable == true && !current;
                      return Expanded(
                        child: _LoginMethodButton(
                          method: method,
                          enabled: enabled,
                          current: current,
                          onPressed: () => onTap(method),
                        ),
                      );
                    })
                    .toList(growable: false),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LoginMethodButton extends StatelessWidget {
  const _LoginMethodButton({
    required this.method,
    required this.enabled,
    required this.current,
    required this.onPressed,
  });

  final String method;
  final bool enabled;
  final bool current;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final label = switch (method) {
      'wechat' => FoundationText.loginMethodWechat,
      'qq' => FoundationText.loginMethodQq,
      _ => FoundationText.loginMethodAlipay,
    };
    final semantic = current
        ? switch (method) {
            'wechat' => FoundationText.loginWechatCurrent,
            'qq' => FoundationText.loginQqCurrent,
            _ => FoundationText.loginAlipayCurrent,
          }
        : enabled
        ? switch (method) {
            'wechat' => FoundationText.loginMethodWechatSemanticLabel,
            'qq' => FoundationText.loginMethodQqSemanticLabel,
            _ => FoundationText.loginMethodAlipaySemanticLabel,
          }
        : switch (method) {
            'wechat' => FoundationText.loginWechatUnavailable,
            'qq' => FoundationText.loginQqUnavailable,
            _ => FoundationText.loginAlipayUnavailable,
          };
    final icon = switch (method) {
      'wechat' => SimpleIcons.wechat,
      'qq' => SimpleIcons.qq,
      _ => SimpleIcons.alipay,
    };
    final color = switch (method) {
      'wechat' => AppColors.loginMethodWechatBrand,
      'qq' => AppColors.loginMethodQqBrand,
      _ => AppColors.loginMethodAlipayBrand,
    };
    return Semantics(
      button: true,
      enabled: enabled,
      label: semantic,
      child: ExcludeSemantics(
        child: Opacity(
          opacity: enabled ? 1 : 0.35,
          child: CupertinoButton(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
            onPressed: enabled ? onPressed : null,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Container(
                  width: AppSpacing.loginOtherMethodSize,
                  height: AppSpacing.loginOtherMethodSize,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    icon,
                    size: AppSpacing.loginOtherMethodIconSize,
                    color: AppColors.white,
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: AppColors.iosSecondaryLabel(context),
                    fontSize: AppTypography.iosCaption1,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LoginProviderMark extends StatelessWidget {
  const LoginProviderMark({super.key, required this.provider});

  final String provider;

  @override
  Widget build(BuildContext context) {
    final icon = switch (provider) {
      'wechat' => SimpleIcons.wechat,
      'qq' => SimpleIcons.qq,
      _ => SimpleIcons.alipay,
    };
    final color = switch (provider) {
      'wechat' => AppColors.loginMethodWechatBrand,
      'qq' => AppColors.loginMethodQqBrand,
      _ => AppColors.loginMethodAlipayBrand,
    };
    return Container(
      width: AppSpacing.loginOtherMethodSize,
      height: AppSpacing.loginOtherMethodSize,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      child: Icon(
        icon,
        size: AppSpacing.loginOtherMethodIconSize,
        color: AppColors.white,
      ),
    );
  }
}
