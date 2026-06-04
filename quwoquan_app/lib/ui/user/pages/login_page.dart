import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({
    super.key,
    this.reason,
    this.redirect,
    this.dismissFallback,
    this.allowGuestDismissPop = true,
  });

  final String? reason;
  final String? redirect;
  final String? dismissFallback;
  final bool allowGuestDismissPop;

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

/// 登录主区域状态机：检测中 -> 一键登录 / 手机号兜底。
///
/// 一键登录检测必须有短超时与失败兜底，禁止主按钮区域长期转圈。
enum LoginPrimaryMode { checking, oneTap, phone }

void _showOtpSendResult(BuildContext context, OtpSendResultData result) {
  if (result.isDebugCodeVisible) {
    final hint = result.deliveryStatus == 'pass_through'
        ? UITextConstants.loginOtpPassThroughDebugHint
        : UITextConstants.loginOtpQueued;
    AppToast.show(
      context,
      '$hint，${UITextConstants.loginOtpDebugCodePrefix}${result.debugCode}',
    );
    return;
  }
  AppToast.show(context, UITextConstants.loginOtpQueued);
}

class WebInlineLoginSurface extends ConsumerStatefulWidget {
  const WebInlineLoginSurface({
    super.key,
    required this.onDismiss,
    required this.onLoggedIn,
    this.reason,
  });

  final VoidCallback onDismiss;
  final VoidCallback onLoggedIn;
  final String? reason;

  @override
  ConsumerState<WebInlineLoginSurface> createState() =>
      _WebInlineLoginSurfaceState();
}

class _WebInlineLoginSurfaceState extends ConsumerState<WebInlineLoginSurface> {
  static const Duration _oneTapProbeTimeout = Duration(milliseconds: 1200);

  bool _agreementAccepted = false;
  bool _isSubmitting = false;
  bool _isSendingOtp = false;
  LoginPrimaryMode _primaryMode = LoginPrimaryMode.checking;
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _otpController = TextEditingController();

  bool get _isActionRequired =>
      widget.reason == AuthPromptReason.actionRequired.name ||
      authGateTitleForReasonName(widget.reason) != null;

  @override
  void initState() {
    super.initState();
    unawaited(_loadOneTapAvailability());
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _loadOneTapAvailability() async {
    var available = false;
    try {
      available = await ref
          .read(oneTapLoginClientProvider)
          .isAvailable()
          .timeout(_oneTapProbeTimeout, onTimeout: () => false);
    } catch (_) {
      available = false;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _primaryMode = available
          ? LoginPrimaryMode.oneTap
          : LoginPrimaryMode.phone;
    });
  }

  @override
  Widget build(BuildContext context) {
    final gateReason = authGateReasonForName(widget.reason);
    final pendingContinuation = ref.watch(authContinuationProvider);
    final gateSemantic = gateReason == null
        ? null
        : authGateSemantic(
            context,
            reason: gateReason,
            continuation: pendingContinuation,
            scope: UiErrorScope.page,
          );
    final title = gateSemantic?.title ?? UITextConstants.loginTitleFirstRun;
    final subtitle =
        gateSemantic?.secondaryMessage ??
        gateSemantic?.message ??
        (_isActionRequired
            ? UITextConstants.loginSubtitleActionRequired
            : UITextConstants.loginSubtitleFirstRun);

    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.iosPageBackground(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
          boxShadow: const <BoxShadow>[
            BoxShadow(
              color: AppColors.webPcLoginSurfaceShadow,
              blurRadius: AppSpacing.webPcToolbarElevationBlurRadius,
              offset: Offset(AppSpacing.zero, AppSpacing.ten),
            ),
          ],
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: AppSpacing.webPcLoginSurfaceWidth,
            maxHeight: AppSpacing.webPcLoginSurfaceMaxHeight,
          ),
          child: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.xl),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      const Spacer(),
                      AppNavigationBarIconButton(
                        icon: CupertinoIcons.xmark,
                        onPressed: _continueAsGuest,
                      ),
                    ],
                  ),
                  _BrandMark(isReturnUser: false),
                  SizedBox(height: AppSpacing.interGroupLg),
                  Text(
                    title,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosTitle2,
                      fontWeight: AppTypography.bold,
                      height: AppSpacing.textLineHeightHeadline,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  Text(
                    subtitle,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosCallout,
                      height: AppSpacing.textLineHeightBody,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupLg),
                  _LoginCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        if (_primaryMode == LoginPrimaryMode.checking)
                          const _LoginModeLoading()
                        else if (_primaryMode == LoginPrimaryMode.oneTap)
                          _PrimaryLoginButton(
                            isSubmitting: _isSubmitting,
                            label: UITextConstants.loginOneTapPrimary,
                            onPressed: _handleOneTapLogin,
                          )
                        else
                          _PhoneLoginForm(
                            phoneController: _phoneController,
                            otpController: _otpController,
                            isSubmitting: _isSubmitting,
                            onSendOtp: _handleSendOtp,
                            onSubmit: _handlePhoneLogin,
                          ),
                      ],
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupMd),
                  _LaterLoginButton(onPressed: _continueAsGuest),
                  SizedBox(height: AppSpacing.interGroupMd),
                  _AgreementRow(
                    accepted: _agreementAccepted,
                    onToggle: () {
                      setState(() => _agreementAccepted = !_agreementAccepted);
                    },
                    onAgreementTap: () =>
                        context.push(AppRoutePaths.legalUserAgreement),
                    onPrivacyTap: () =>
                        context.push(AppRoutePaths.legalPrivacyPolicy),
                  ),
                  SizedBox(height: AppSpacing.interGroupLg),
                  const _OtherLoginMethods(),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  bool _ensureAgreementAccepted() {
    if (_agreementAccepted) {
      return true;
    }
    AppToast.show(context, UITextConstants.authConsentRequired);
    return false;
  }

  UiErrorSemantic _loginActionFailureSemantic({
    required Object error,
    required String title,
    required String message,
  }) {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    return UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: title,
      message: resolved.message.isNotEmpty ? resolved.message : message,
      secondaryMessage: resolved.secondaryMessage,
      primaryAction: const UiErrorAction(
        type: UiErrorActionType.dismiss,
        label: UITextConstants.confirm,
      ),
      secondaryAction: resolved.secondaryAction,
      dismissible: resolved.dismissible,
      sourceCode: resolved.sourceCode,
      failureKind: resolved.failureKind,
      recoveryAction: resolved.recoveryAction,
    );
  }

  Future<void> _handleOneTapLogin() async {
    if (!_ensureAgreementAccepted()) {
      return;
    }
    setState(() => _isSubmitting = true);
    UiErrorSemantic? errorSemantic;
    try {
      final oneTap = await ref
          .read(oneTapLoginClientProvider)
          .requestLoginToken()
          .timeout(_oneTapProbeTimeout);
      final session = ref.read(authSessionControllerProvider);
      final result = await ref
          .read(authRepositoryProvider)
          .loginOneTap(
            vendor: oneTap.vendor,
            carrierToken: oneTap.carrierToken,
            deviceId: session.installId,
            platform: CloudRequestHeaders.platform(),
            agreementVersion: AuthLegalConfig.agreementVersion,
            privacyVersion: AuthLegalConfig.privacyVersion,
          );
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyLoginResult(result);
      widget.onLoggedIn();
    } catch (error) {
      if (mounted) {
        errorSemantic = _loginActionFailureSemantic(
          error: error,
          title: '一键登录未完成',
          message: UITextConstants.loginFailed,
        );
        setState(() => _primaryMode = LoginPrimaryMode.phone);
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
    final semantic = errorSemantic;
    if (semantic != null && mounted) {
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  Future<void> _handlePhoneLogin() async {
    if (!_ensureAgreementAccepted()) {
      return;
    }
    final phone = _phoneController.text.trim();
    final otp = _otpController.text.trim();
    if (phone.isEmpty) {
      AppToast.show(context, UITextConstants.loginPhoneRequired);
      return;
    }
    if (otp.isEmpty) {
      AppToast.show(context, UITextConstants.loginOtpRequired);
      return;
    }
    setState(() => _isSubmitting = true);
    UiErrorSemantic? errorSemantic;
    try {
      final result = await ref
          .read(authRepositoryProvider)
          .login(
            credentialType: 'phone',
            credentialKey: phone,
            otpCode: otp,
            displayLabel: phone,
          );
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyLoginResult(result);
      widget.onLoggedIn();
    } catch (error) {
      if (mounted) {
        errorSemantic = _loginActionFailureSemantic(
          error: error,
          title: '登录未完成',
          message: UITextConstants.loginFailed,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
    final semantic = errorSemantic;
    if (semantic != null && mounted) {
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  Future<void> _handleSendOtp() async {
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      AppToast.show(context, UITextConstants.loginPhoneRequired);
      return;
    }
    if (_isSendingOtp) {
      return;
    }
    setState(() => _isSendingOtp = true);
    UiErrorSemantic? errorSemantic;
    try {
      final result = await ref
          .read(authRepositoryProvider)
          .sendOtp(phone: phone);
      if (!mounted) {
        return;
      }
      _showOtpSendResult(context, result);
    } catch (error) {
      if (mounted) {
        errorSemantic = _loginActionFailureSemantic(
          error: error,
          title: '验证码发送未完成',
          message: UITextConstants.loginFailed,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSendingOtp = false);
      }
    }
    final semantic = errorSemantic;
    if (semantic != null && mounted) {
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  Future<void> _continueAsGuest() async {
    await ref.read(authSessionControllerProvider.notifier).continueAsGuest();
    if (!mounted) return;
    widget.onDismiss();
  }
}

class _LoginPageState extends ConsumerState<LoginPage> {
  /// 一键登录可用性探测的最长等待时间；超时即切手机号兜底。
  static const Duration _oneTapProbeTimeout = Duration(milliseconds: 1200);

  bool _agreementAccepted = false;
  bool _isSubmitting = false;
  bool _isSendingOtp = false;
  LoginPrimaryMode _primaryMode = LoginPrimaryMode.checking;
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _otpController = TextEditingController();

  bool get _isReturnUser =>
      widget.reason == AuthPromptReason.manualLoggedOut.name;

  bool get _isActionRequired =>
      widget.reason == AuthPromptReason.actionRequired.name ||
      authGateTitleForReasonName(widget.reason) != null;

  @override
  void initState() {
    super.initState();
    unawaited(_loadOneTapAvailability());
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _loadOneTapAvailability() async {
    var available = false;
    try {
      available = await ref
          .read(oneTapLoginClientProvider)
          .isAvailable()
          .timeout(_oneTapProbeTimeout, onTimeout: () => false);
    } catch (_) {
      available = false;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _primaryMode = available
          ? LoginPrimaryMode.oneTap
          : LoginPrimaryMode.phone;
    });
  }

  @override
  Widget build(BuildContext context) {
    final gateReason = authGateReasonForName(widget.reason);
    final pendingContinuation = ref.watch(authContinuationProvider);
    final gateSemantic = gateReason == null
        ? null
        : authGateSemantic(
            context,
            reason: gateReason,
            continuation: pendingContinuation,
            scope: UiErrorScope.page,
          );
    final title =
        gateSemantic?.title ??
        (_isReturnUser
            ? UITextConstants.loginTitleReturn
            : UITextConstants.loginTitleFirstRun);
    final subtitle =
        gateSemantic?.secondaryMessage ??
        gateSemantic?.message ??
        (_isActionRequired
            ? UITextConstants.loginSubtitleActionRequired
            : _isReturnUser
            ? UITextConstants.loginSubtitleReturn
            : UITextConstants.loginSubtitleFirstRun);

    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.transparent,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.xmark,
          onPressed: _continueAsGuest,
        ),
        trailing: AppNavigationBarIconButton(
          icon: CupertinoIcons.question_circle,
          onPressed: () => AppToast.show(context, UITextConstants.loginHelp),
        ),
      ),
      body: DefaultTextStyle.merge(
        style: const TextStyle(
          decoration: TextDecoration.none,
          decorationThickness: 0,
        ),
        child: SafeArea(
          child: Stack(
            children: <Widget>[
              const _LoginPageBackdrop(),
              LayoutBuilder(
                builder: (context, constraints) {
                  return SingleChildScrollView(
                    child: ConstrainedBox(
                      constraints: BoxConstraints(
                        minHeight: constraints.maxHeight,
                      ),
                      child: Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.containerLg,
                        ),
                        child: Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(
                              maxWidth: AppSpacing.threeHundredTwenty,
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: <Widget>[
                                SizedBox(height: AppSpacing.interGroupMd),
                                _BrandMark(isReturnUser: _isReturnUser),
                                SizedBox(height: AppSpacing.interGroupLg),
                                Text(
                                  title,
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontSize: AppTypography.iosTitle2,
                                    fontWeight: AppTypography.bold,
                                    height: AppSpacing.textLineHeightHeadline,
                                    color: AppColors.iosLabel(context),
                                  ),
                                ),
                                SizedBox(height: AppSpacing.intraGroupSm),
                                Text(
                                  subtitle,
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontSize: AppTypography.iosCallout,
                                    height: AppSpacing.textLineHeightBody,
                                    color: AppColors.iosSecondaryLabel(context),
                                  ),
                                ),
                                SizedBox(height: AppSpacing.interGroupLg),
                                _LoginCard(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.stretch,
                                    children: <Widget>[
                                      if (_primaryMode ==
                                          LoginPrimaryMode.checking)
                                        const _LoginModeLoading()
                                      else if (_primaryMode ==
                                          LoginPrimaryMode.oneTap)
                                        _PrimaryLoginButton(
                                          isSubmitting: _isSubmitting,
                                          label: UITextConstants
                                              .loginOneTapPrimary,
                                          onPressed: _handleOneTapLogin,
                                        )
                                      else
                                        _PhoneLoginForm(
                                          phoneController: _phoneController,
                                          otpController: _otpController,
                                          isSubmitting: _isSubmitting,
                                          onSendOtp: _handleSendOtp,
                                          onSubmit: _handlePhoneLogin,
                                        ),
                                    ],
                                  ),
                                ),
                                SizedBox(height: AppSpacing.interGroupMd),
                                _LaterLoginButton(onPressed: _continueAsGuest),
                                SizedBox(height: AppSpacing.interGroupMd),
                                // 协议区属于「登录决策区」：位于「稍后登录」之后、
                                // 其他登录方式之前，登录前必须可见、可理解。
                                _AgreementRow(
                                  accepted: _agreementAccepted,
                                  onToggle: () {
                                    setState(
                                      () => _agreementAccepted =
                                          !_agreementAccepted,
                                    );
                                  },
                                  onAgreementTap: () => context.push(
                                    AppRoutePaths.legalUserAgreement,
                                  ),
                                  onPrivacyTap: () => context.push(
                                    AppRoutePaths.legalPrivacyPolicy,
                                  ),
                                ),
                                SizedBox(height: AppSpacing.interGroupLg),
                                const _OtherLoginMethods(),
                                SizedBox(height: AppSpacing.intraGroupSm),
                                CupertinoButton(
                                  padding: EdgeInsets.zero,
                                  onPressed: () => AppToast.show(
                                    context,
                                    UITextConstants.loginHelp,
                                  ),
                                  child: const Text(UITextConstants.loginHelp),
                                ),
                                SizedBox(height: AppSpacing.containerLg),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  bool _ensureAgreementAccepted() {
    if (_agreementAccepted) {
      return true;
    }
    AppToast.show(context, UITextConstants.authConsentRequired);
    return false;
  }

  UiErrorSemantic _loginActionFailureSemantic({
    required Object error,
    required String title,
    required String message,
  }) {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    return UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: title,
      message: resolved.message.isNotEmpty ? resolved.message : message,
      secondaryMessage: resolved.secondaryMessage,
      primaryAction: const UiErrorAction(
        type: UiErrorActionType.dismiss,
        label: UITextConstants.confirm,
      ),
      secondaryAction: resolved.secondaryAction,
      dismissible: resolved.dismissible,
      sourceCode: resolved.sourceCode,
      failureKind: resolved.failureKind,
      recoveryAction: resolved.recoveryAction,
    );
  }

  Future<void> _handleOneTapLogin() async {
    if (!_ensureAgreementAccepted()) {
      return;
    }
    setState(() => _isSubmitting = true);
    UiErrorSemantic? errorSemantic;
    try {
      final oneTap = await ref
          .read(oneTapLoginClientProvider)
          .requestLoginToken()
          .timeout(_oneTapProbeTimeout);
      final session = ref.read(authSessionControllerProvider);
      final result = await ref
          .read(authRepositoryProvider)
          .loginOneTap(
            vendor: oneTap.vendor,
            carrierToken: oneTap.carrierToken,
            deviceId: session.installId,
            platform: CloudRequestHeaders.platform(),
            agreementVersion: AuthLegalConfig.agreementVersion,
            privacyVersion: AuthLegalConfig.privacyVersion,
          );
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyLoginResult(result);
      _goAfterLogin();
    } catch (error) {
      if (mounted) {
        // 一键登录失败不停留在一键登录态，切到手机号兜底，避免按钮区域卡住。
        errorSemantic = _loginActionFailureSemantic(
          error: error,
          title: '一键登录未完成',
          message: UITextConstants.loginFailed,
        );
        setState(() => _primaryMode = LoginPrimaryMode.phone);
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
    final semantic = errorSemantic;
    if (semantic != null && mounted) {
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  Future<void> _handlePhoneLogin() async {
    if (!_ensureAgreementAccepted()) {
      return;
    }
    final phone = _phoneController.text.trim();
    final otp = _otpController.text.trim();
    if (phone.isEmpty) {
      AppToast.show(context, UITextConstants.loginPhoneRequired);
      return;
    }
    if (otp.isEmpty) {
      AppToast.show(context, UITextConstants.loginOtpRequired);
      return;
    }
    setState(() => _isSubmitting = true);
    UiErrorSemantic? errorSemantic;
    try {
      final result = await ref
          .read(authRepositoryProvider)
          .login(
            credentialType: 'phone',
            credentialKey: phone,
            otpCode: otp,
            displayLabel: phone,
          );
      await ref
          .read(authSessionControllerProvider.notifier)
          .applyLoginResult(result);
      _goAfterLogin();
    } catch (error) {
      if (mounted) {
        errorSemantic = _loginActionFailureSemantic(
          error: error,
          title: '登录未完成',
          message: UITextConstants.loginFailed,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
    final semantic = errorSemantic;
    if (semantic != null && mounted) {
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  Future<void> _handleSendOtp() async {
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      AppToast.show(context, UITextConstants.loginPhoneRequired);
      return;
    }
    if (_isSendingOtp) {
      return;
    }
    setState(() => _isSendingOtp = true);
    UiErrorSemantic? errorSemantic;
    try {
      final result = await ref
          .read(authRepositoryProvider)
          .sendOtp(phone: phone);
      if (!mounted) {
        return;
      }
      _showOtpSendResult(context, result);
    } catch (error) {
      if (mounted) {
        errorSemantic = _loginActionFailureSemantic(
          error: error,
          title: '验证码发送未完成',
          message: UITextConstants.loginFailed,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSendingOtp = false);
      }
    }
    final semantic = errorSemantic;
    if (semantic != null && mounted) {
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  void _goAfterLogin() {
    if (!mounted) {
      return;
    }
    final redirect = widget.redirect;
    if (redirect != null && redirect.isNotEmpty) {
      context.go(redirect);
    } else if (widget.allowGuestDismissPop && context.canPop()) {
      // 行内拦截（评论/点赞等）以 push 进入：登录成功后回到原页面原 tab。
      context.pop();
    } else {
      context.go(
        safeLoginDismissFallback(
          redirect: widget.redirect,
          dismissFallback: widget.dismissFallback,
        ),
      );
    }
  }

  Future<void> _continueAsGuest() async {
    await ref.read(authSessionControllerProvider.notifier).continueAsGuest();
    if (!mounted) return;
    _dismissAsGuest();
  }

  /// 游客关闭 / 稍后登录：尽量原路返回，但绝不返回到「需要登录」的受限路由，
  /// 否则路由守卫会立刻再次把登录页弹出来，形成死循环。
  ///
  /// 优先使用显式传入的 [LoginPage.dismissFallback]，否则再从 redirect 推导安全页。
  /// 对底栏强入口（创作/消息）或首页内受限状态（如关注频道）必须禁用 guest pop，
  /// 统一回到稳定可浏览的底层页面，避免再次触发登录门。
  void _dismissAsGuest() {
    final fallback = safeLoginDismissFallback(
      redirect: widget.redirect,
      dismissFallback: widget.dismissFallback,
    );
    if (widget.allowGuestDismissPop && context.canPop()) {
      context.pop();
    } else {
      context.go(fallback);
    }
  }
}

class _PrimaryLoginButton extends StatelessWidget {
  const _PrimaryLoginButton({
    required this.isSubmitting,
    required this.label,
    required this.onPressed,
  });

  final bool isSubmitting;
  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        gradient: const LinearGradient(
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
          colors: <Color>[
            AppColors.brandBlue500,
            AppColors.brandBlue600,
            AppColors.brandBlue700,
          ],
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.primaryColor.withValues(alpha: 0.26),
            blurRadius: AppSpacing.twentyEight,
            offset: const Offset(AppSpacing.zero, AppSpacing.ten),
          ),
        ],
      ),
      child: CupertinoButton(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        color: AppColors.transparent,
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.buttonHeightLg,
        ),
        onPressed: isSubmitting ? null : onPressed,
        child: isSubmitting
            ? const CupertinoActivityIndicator(color: AppColors.white)
            : Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.white,
                ),
              ),
      ),
    );
  }
}

class _LoginPageBackdrop extends StatelessWidget {
  const _LoginPageBackdrop();

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              AppColors.brandBlue50.withValues(alpha: 0.82),
              AppColors.iosPageBackground(context),
              AppColors.iosPageBackground(context),
            ],
          ),
        ),
        child: Stack(
          children: <Widget>[
            Positioned(
              top: -AppSpacing.oneHundred,
              right: -AppSpacing.oneHundred,
              child: _SoftGlow(
                diameter: AppSpacing.twoHundredTwenty,
                color: AppColors.brandBlue100.withValues(alpha: 0.72),
              ),
            ),
            Positioned(
              top: AppSpacing.threeHundredTwenty,
              left: -AppSpacing.oneHundred,
              child: _SoftGlow(
                diameter: AppSpacing.twoHundredTwenty,
                color: AppColors.brandBlue300.withValues(alpha: 0.16),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SoftGlow extends StatelessWidget {
  const _SoftGlow({required this.diameter, required this.color});

  final double diameter;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: diameter,
      height: diameter,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color),
    );
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark({required this.isReturnUser});

  final bool isReturnUser;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: AppSpacing.oneHundred,
        height: AppSpacing.oneHundred,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: <Color>[
              AppColors.white.withValues(alpha: 0.98),
              AppColors.brandBlue50,
            ],
          ),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: AppColors.primaryColor.withValues(alpha: 0.18),
              blurRadius: AppSpacing.thirtySix,
              offset: const Offset(AppSpacing.zero, AppSpacing.ten),
            ),
          ],
        ),
        child: Icon(
          isReturnUser
              ? CupertinoIcons.arrow_counterclockwise_circle_fill
              : CupertinoIcons.person_crop_circle_badge_checkmark,
          size: AppSpacing.avatarUserXl,
          color: AppColors.iosAccent(context),
        ),
      ),
    );
  }
}

class _LoginCard extends StatelessWidget {
  const _LoginCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupXs),
      child: child,
    );
  }
}

class _LoginModeLoading extends StatelessWidget {
  const _LoginModeLoading();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.buttonHeightLg,
      child: Center(
        child: CupertinoActivityIndicator(color: AppColors.iosAccent(context)),
      ),
    );
  }
}

class _LaterLoginButton extends StatelessWidget {
  const _LaterLoginButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.buttonHeightLg,
      ),
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      color: AppColors.iosSecondaryFill(context),
      onPressed: onPressed,
      child: Text(
        UITextConstants.loginLater,
        style: TextStyle(
          fontSize: AppTypography.iosBody,
          fontWeight: AppTypography.semiBold,
          color: AppColors.iosAccent(context),
        ),
      ),
    );
  }
}

class _PhoneLoginForm extends StatelessWidget {
  const _PhoneLoginForm({
    required this.phoneController,
    required this.otpController,
    required this.isSubmitting,
    required this.onSendOtp,
    required this.onSubmit,
  });

  final TextEditingController phoneController;
  final TextEditingController otpController;
  final bool isSubmitting;
  final VoidCallback onSendOtp;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _LoginTextField(
          controller: phoneController,
          placeholder: UITextConstants.loginPhoneNumberPlaceholder,
          keyboardType: TextInputType.phone,
        ),
        SizedBox(height: AppSpacing.intraGroupMd),
        Row(
          children: <Widget>[
            Expanded(
              child: _LoginTextField(
                controller: otpController,
                placeholder: UITextConstants.loginOtpPlaceholder,
                keyboardType: TextInputType.number,
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            CupertinoButton(
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              color: AppColors.iosSecondaryFill(context),
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              onPressed: onSendOtp,
              child: Text(
                UITextConstants.loginSendOtp,
                style: TextStyle(color: AppColors.iosAccent(context)),
              ),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        _PrimaryLoginButton(
          isSubmitting: isSubmitting,
          label: UITextConstants.loginPhoneSubmit,
          onPressed: onSubmit,
        ),
      ],
    );
  }
}

class _LoginTextField extends StatelessWidget {
  const _LoginTextField({
    required this.controller,
    required this.placeholder,
    required this.keyboardType,
  });

  final TextEditingController controller;
  final String placeholder;
  final TextInputType keyboardType;

  @override
  Widget build(BuildContext context) {
    return CupertinoTextField(
      controller: controller,
      keyboardType: keyboardType,
      minLines: 1,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      placeholder: placeholder,
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
    );
  }
}

class _AgreementRow extends StatelessWidget {
  const _AgreementRow({
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
        GestureDetector(
          onTap: onToggle,
          child: Container(
            width: AppSpacing.iconMedium,
            height: AppSpacing.iconMedium,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.iosSeparator(context)),
              color: accepted ? AppColors.primaryColor : AppColors.transparent,
            ),
            child: accepted
                ? Icon(
                    CupertinoIcons.check_mark,
                    size: AppSpacing.iconSmall,
                    color: AppColors.white,
                  )
                : null,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              Text(
                UITextConstants.loginAgreementPrefix,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
              _LinkText(
                text: UITextConstants.userAgreement,
                onTap: onAgreementTap,
              ),
              Text(
                UITextConstants.loginAgreementAnd,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
              _LinkText(
                text: UITextConstants.privacyPolicy,
                onTap: onPrivacyTap,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _LinkText extends StatelessWidget {
  const _LinkText({required this.text, required this.onTap});

  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Text(
        text,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.semiBold,
          color: AppColors.iosAccent(context),
        ),
      ),
    );
  }
}

class _OtherLoginMethods extends StatelessWidget {
  const _OtherLoginMethods();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Text(
          UITextConstants.loginOtherMethods,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosTertiaryLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: const <Widget>[
            _OtherLoginMethod(
              icon: CupertinoIcons.chat_bubble_2_fill,
              label: UITextConstants.loginMethodWechat,
            ),
            _OtherLoginMethod(
              icon: CupertinoIcons.at_circle_fill,
              label: UITextConstants.loginMethodWeibo,
            ),
            _OtherLoginMethod(
              icon: CupertinoIcons.person_2_fill,
              label: UITextConstants.loginMethodQq,
            ),
            _OtherLoginMethod(
              icon: CupertinoIcons.money_yen_circle_fill,
              label: UITextConstants.loginMethodAlipay,
            ),
          ],
        ),
      ],
    );
  }
}

class _OtherLoginMethod extends StatelessWidget {
  const _OtherLoginMethod({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: () => AppToast.show(
        context,
        '$label${UITextConstants.loginMethodComingSoon}',
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, color: AppColors.iosSecondaryLabel(context)),
          SizedBox(height: AppSpacing.xs),
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
      ),
    );
  }
}
