import 'dart:async';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_legal_config.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/di/login_dependencies.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show
        accountSessionLifecycleCommandWriterProvider,
        accountSessionLoginCommandWriterProvider,
        appCredentialBindingCommandWriterProvider,
        authenticationChallengeCommandWriterProvider;
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:simple_icons/simple_icons.dart';
part 'login_page_top_bar.dart';
part 'login_page_models.dart';
part 'login_page_entry_surfaces.dart';
part 'login_page_frame.dart';
part 'login_page_form_controls.dart';
part 'login_page_social_actions.dart';

part 'login_page_phone_flow.dart';
part 'login_page_auth_flow.dart';

class LoginFrameHost extends ConsumerStatefulWidget {
  const LoginFrameHost({
    super.key,
    this.reason,
    this.redirect,
    this.dismissFallback,
    this.dismissPolicy = LoginDismissPolicy.popPrevious,
    this.onDismiss,
    this.onLoggedIn,
    this.surfaceMode = LoginSurfaceMode.page,
  });
  final String? reason;
  final String? redirect;
  final String? dismissFallback;
  final LoginDismissPolicy dismissPolicy;
  final VoidCallback? onDismiss, onLoggedIn;
  final LoginSurfaceMode surfaceMode;
  @override
  ConsumerState<LoginFrameHost> createState() => _LoginFrameHostState();
}

class _LoginFrameHostState extends ConsumerState<LoginFrameHost>
    with WidgetsBindingObserver {
  static const Duration _probeTimeout = Duration(milliseconds: 1200);
  static const Duration _requestTimeout = Duration(seconds: 15);
  static const Duration _providerTimeout = Duration(seconds: 60);
  static const Duration _stateDwellThreshold = Duration(seconds: 90);
  static const String _loginPageName = 'LoginPage';
  late final LoginFlowController _flowController;
  OneTapLoginProbe? _probe;
  int _attemptSerial = 0;
  int? _activeAttempt;
  int _entryResolutionGeneration = 0;
  String _quickLoginRefreshToken = '';
  String _rememberedPhone = '';
  LoginStep _rootStep = LoginStep.phoneEntry;
  LoginEntryMode _rootEntryMode = LoginEntryMode.phone;
  String _rootMaskedPhone = '';
  LoginPendingIntent? _pendingConsentIntent;
  bool _consentSheetVisible = false;
  bool _openingAccountRestrictionSupport = false;
  String _lastAutoVerifiedCode = '';
  Map<String, NativeAuthCapability> _socialMethodAvailability =
      const <String, NativeAuthCapability>{};
  late final JourneyEventTracker _journeyTracker;
  late final TextEditingController _phoneController, _otpController;
  Timer? _otpCountdownTicker;
  Timer? _stateDwellWatchdog;
  final Stopwatch _stateDwellStopwatch = Stopwatch()..start();

  LoginFlowState get _flow => _flowController.state;

  bool get _isAccountSuspensionEntry =>
      authPromptReasonForName(widget.reason) ==
      AuthPromptReason.accountSuspended;

  bool get _isAccountSuspensionSurface =>
      _isAccountSuspensionEntry ||
      _flow.feedback?.sourceCode == UserErrorCode.accountSuspended.code;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _journeyTracker = ref.read(loginJourneyEventTrackerProvider);
    _flowController = LoginFlowController(
      flowId:
          'login-${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}-${identityHashCode(this).toRadixString(36)}',
    )..addListener(_handleFlowChanged);
    _phoneController = TextEditingController();
    _otpController = TextEditingController();
    _armStateDwellWatchdog();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _trackLoginFunnel('login_flow_exposed', result: 'exposed');
      unawaited(_resolveEntryState());
    });
  }

  void _handleFlowChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshCountdownFromDeadline(trackResume: true);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _activeAttempt = null;
    _entryResolutionGeneration += 1;
    _otpCountdownTicker?.cancel();
    _stateDwellWatchdog?.cancel();
    _phoneController.dispose();
    _otpController.dispose();
    _flowController
      ..removeListener(_handleFlowChanged)
      ..dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final content = PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _handleBackOrDismiss();
      },
      child: LoginFrame(
        state: _flow,
        phoneEntryHasParent:
            _flow.step == LoginStep.phoneEntry && _rootStep == LoginStep.oneTap,
        socialMethodAvailability: _socialMethodAvailability,
        dismissPolicy: widget.dismissPolicy,
        isInline: widget.surfaceMode == LoginSurfaceMode.inline,
        phoneController: _phoneController,
        otpController: _otpController,
        onAgreementToggle: _toggleAgreement,
        onNavigate: _handleBackOrDismiss,
        onOneTap: () => unawaited(_runWithConsent(LoginPendingIntent.oneTap)),
        onOtherPhone: () => _enterPhoneEntry(preserveRoot: true),
        onPhonePrimary: () => unawaited(_requestOtp()),
        onAgreementTap: () => context.push(AppRoutePaths.legalUserAgreement),
        onPrivacyTap: () => context.push(AppRoutePaths.legalPrivacyPolicy),
        onSocialMethod: _handleSocialMethod,
        onPhoneChanged: _handlePhoneChanged,
        onPhoneEditingComplete: _handlePhoneEditingComplete,
        onOtpChanged: _handleOtpChanged,
        onResendOtp: () => unawaited(_requestOtp(resend: true)),
        onRetryOtpVerify: () => unawaited(_verifyOtp()),
        onChangePhone: _changePhone,
        onRetrySocial: () => unawaited(_retrySocialAuthorization()),
        onCancelSocial: _cancelSocialAuthorization,
        onAccountRestrictionSupport: () =>
            unawaited(_openAccountRestrictionSupport()),
        accountRestrictionSupportBusy: _openingAccountRestrictionSupport,
      ),
    );
    if (widget.surfaceMode == LoginSurfaceMode.inline) {
      return content;
    }
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      child: content,
    );
  }
}
