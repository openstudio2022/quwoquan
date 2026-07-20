part of 'edit_profile_page.dart';

class _PhoneBindPageState extends ConsumerState<_PhoneBindPage> {
  late final TextEditingController _phoneController;
  late final TextEditingController _otpController;
  ProfileCredentialSummaryData? _credential;
  bool _oneTapAvailable = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _credential = widget.initialCredential;
    _phoneController = TextEditingController();
    _otpController = TextEditingController();
    unawaited(_probeOneTap());
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _probeOneTap() async {
    final available = await ref.read(oneTapLoginClientProvider).isAvailable();
    if (mounted) {
      setState(() => _oneTapAvailable = available);
    }
  }

  Future<void> _bindOneTap() async {
    setState(() => _busy = true);
    try {
      final token = await ref
          .read(oneTapLoginClientProvider)
          .requestLoginToken();
      await ref
          .read(appCredentialBindingCommandWriterProvider)
          .bindCarrierPhoneCredential(
            BindCarrierPhoneCredentialCommand(
              vendor: token.vendor,
              carrierToken: token.carrierToken,
              deviceId: ref.read(authSessionControllerProvider).installId,
              platform: CloudRequestHeaders.platform(),
              displayLabel: token.maskedPhone,
            ),
          );
      if (!mounted) {
        return;
      }
      final credential = ProfileCredentialSummaryData(
        credentialType: 'carrier_phone',
        displayLabel: token.maskedPhone,
        isBound: true,
      );
      _trackPhoneAction('carrier_phone_bind', 'succeeded');
      AppToast.show(context, UITextConstants.editProfilePhoneBindSuccess);
      Navigator.of(context).pop(credential);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _busy = false);
      _trackPhoneAction('carrier_phone_bind', 'failed');
      await _showPhoneError(error);
    }
  }

  Future<void> _sendOtp() async {
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      return;
    }
    setState(() => _busy = true);
    try {
      await ref
          .read(authenticationChallengeCommandWriterProvider)
          .sendOtp(
            SendOtpCommand(
              phone: phone,
              platform: CloudRequestHeaders.platform(),
              appVersion: CloudRequestHeaders.appVersion,
              sourceOperation: 'bind_phone',
            ),
          );
      if (mounted) {
        setState(() => _busy = false);
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _busy = false);
      await _showPhoneError(error);
    }
  }

  Future<void> _bindOtp() async {
    final phone = _phoneController.text.trim();
    final otp = _otpController.text.trim();
    if (phone.isEmpty || otp.isEmpty) {
      return;
    }
    setState(() => _busy = true);
    try {
      await ref
          .read(appCredentialBindingCommandWriterProvider)
          .bindPhoneCredential(
            BindPhoneCredentialCommand(phone: phone, otpCode: otp),
          );
      if (!mounted) {
        return;
      }
      final credential = ProfileCredentialSummaryData(
        credentialType: 'phone',
        displayLabel: _maskPhone(phone),
        isBound: true,
      );
      _trackPhoneAction('otp_phone_bind', 'succeeded');
      AppToast.show(context, UITextConstants.editProfilePhoneBindSuccess);
      Navigator.of(context).pop(credential);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _busy = false);
      _trackPhoneAction('otp_phone_bind', 'failed');
      await _showPhoneError(error);
    }
  }

  Future<void> _showPhoneError(Object error) async {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: UITextConstants.editProfilePhoneBindFailedTitle,
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction: resolved.primaryAction,
        secondaryAction: resolved.secondaryAction,
        dismissible: resolved.dismissible,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        copyKey: resolved.copyKey,
        recoveryAction: resolved.recoveryAction,
        presentation: resolved.presentation,
        tone: resolved.tone,
      ),
    );
  }

  void _trackPhoneAction(String action, String outcome) {
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'profile_edit',
            action: 'phone_$action',
            pageName: 'EditProfilePage',
            payload: <String, dynamic>{'result': outcome},
          ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final credential = _credential;
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).pop(),
        ),
        middle: Text(
          UITextConstants.editProfilePhoneTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        children: <Widget>[
          if (credential != null && credential.isBound) ...<Widget>[
            SizedBox(height: AppSpacing.oneHundred),
            Center(
              child: Text(
                '${UITextConstants.editProfilePhoneBoundPrefix}: ${credential.displayLabel}',
                style: TextStyle(
                  fontSize: AppTypography.iosTitle3,
                  color: AppColors.iosLabel(context),
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              UITextConstants.editProfilePhoneBoundHint,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ] else ...<Widget>[
            ProfileIosActionButton(
              label: _oneTapAvailable
                  ? UITextConstants.editProfilePhoneOneTapBind
                  : UITextConstants.editProfilePhoneOneTapUnavailable,
              style: ProfileIosActionStyle.filled,
              height: AppSpacing.buttonHeightLg,
              onPressed: _oneTapAvailable && !_busy ? _bindOneTap : null,
            ),
            SizedBox(height: AppSpacing.containerMd),
            CupertinoTextField(
              controller: _phoneController,
              keyboardType: TextInputType.phone,
              placeholder: UITextConstants.editProfilePhoneInputPlaceholder,
              padding: EdgeInsets.all(AppSpacing.containerMd),
              decoration: _inputDecoration(context),
            ),
            SizedBox(height: AppSpacing.containerSm),
            Row(
              children: <Widget>[
                Expanded(
                  child: CupertinoTextField(
                    controller: _otpController,
                    keyboardType: TextInputType.number,
                    placeholder: UITextConstants.editProfileOtpInputPlaceholder,
                    padding: EdgeInsets.all(AppSpacing.containerMd),
                    decoration: _inputDecoration(context),
                  ),
                ),
                SizedBox(width: AppSpacing.containerSm),
                ProfileIosActionButton(
                  label: UITextConstants.editProfileSendOtp,
                  expand: false,
                  height: AppSpacing.buttonHeightLg,
                  onPressed: _busy ? null : _sendOtp,
                ),
              ],
            ),
            SizedBox(height: AppSpacing.containerMd),
            ProfileIosActionButton(
              label: UITextConstants.editProfileBindNow,
              style: ProfileIosActionStyle.filled,
              height: AppSpacing.buttonHeightLg,
              onPressed: _busy ? null : _bindOtp,
            ),
          ],
        ],
      ),
    );
  }
}

class _QrCardBody extends StatelessWidget {
  const _QrCardBody({required this.card});

  final ProfileQrCardData card;

  @override
  Widget build(BuildContext context) {
    return MyQrCardView(
      card: card,
      onScanPressed: () => context.push(AppRoutePaths.addContactScan),
    );
  }
}
