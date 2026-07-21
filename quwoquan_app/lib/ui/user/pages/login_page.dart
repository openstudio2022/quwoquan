import 'dart:async';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
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
import 'package:quwoquan_app/core/di/login_dependencies.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show
        accountSessionLifecycleCommandWriterProvider,
        accountSessionLoginCommandWriterProvider,
        authenticationChallengeCommandWriterProvider;
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';
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

class _LoginFrameHostState extends ConsumerState<LoginFrameHost> {
  static const Duration _probeTimeout = Duration(milliseconds: 1200);
  static const String _loginJourney = 'two_state_login',
      _loginPageName = 'LoginPage';
  bool _agreementAccepted = false;
  bool _showAgreementError = false;
  LoginEntryPresentation _presentation =
      const LoginEntryPresentation.resolving();
  OneTapLoginProbe? _probe;
  int _attemptSerial = 0;
  int? _activeAttempt;
  int _entryResolutionGeneration = 0;
  Map<String, NativeAuthCapability> _socialMethodAvailability =
      const <String, NativeAuthCapability>{};
  String _socialMethodFeedback = '';
  late final JourneyEventTracker _journeyTracker;
  late final TextEditingController _phoneController, _otpController;
  Timer? _otpCountdownTimer;
  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(loginJourneyEventTrackerProvider);
    _phoneController = TextEditingController();
    _otpController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackLoginEvent('login_page_exposed');
    });
    unawaited(_resolveEntryState());
  }

  @override
  void dispose() {
    _activeAttempt = null;
    _entryResolutionGeneration += 1;
    _otpCountdownTimer?.cancel();
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  void _updateState(VoidCallback update) {
    if (!mounted) {
      return;
    }
    setState(update);
  }

  @override
  Widget build(BuildContext context) {
    final content = LoginFrame(
      reason: widget.reason,
      presentation: _presentation,
      agreementAccepted: _agreementAccepted,
      showAgreementError: _showAgreementError,
      socialMethodAvailability: _socialMethodAvailability,
      socialMethodFeedback: _socialMethodFeedback,
      dismissPolicy: widget.dismissPolicy,
      isInline: widget.surfaceMode == LoginSurfaceMode.inline,
      phoneController: _phoneController,
      otpController: _otpController,
      onAgreementToggle: () => setState(() {
        _agreementAccepted = !_agreementAccepted;
        if (_agreementAccepted) {
          _showAgreementError = false;
        }
      }),
      onDismiss: _dismissAsGuest,
      onPrimary: _handlePrimaryLogin,
      onAgreementTap: () => context.push(AppRoutePaths.legalUserAgreement),
      onPrivacyTap: () => context.push(AppRoutePaths.legalPrivacyPolicy),
      onOtherMethod: _handleOtherMethod,
      onPhoneChanged: _handlePhoneChanged,
      onPhoneEditingComplete: _handlePhoneEditingComplete,
      onOtpChanged: _handleOtpChanged,
      onResendOtp: _resendPhoneOtp,
      onChangePhone: _resetPhoneOtpToIdle,
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
