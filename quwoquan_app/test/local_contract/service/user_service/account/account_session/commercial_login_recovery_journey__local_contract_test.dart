// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/otp_autofill_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/pending_otp_attempt_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/user_service/account/account_session/test_auth_facets.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

void main() {
  testWidgets('游客手机号登录：发码、六位输入自动验证后回到目标表面', (tester) async {
    final facets = _JourneyAuthFacets();
    var targetResumed = false;

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStoreProvider.overrideWithValue(_JourneyAuthStore()),
          accountSessionLoginCommandWriterProvider.overrideWithValue(facets),
          accountSessionLifecycleCommandWriterProvider.overrideWithValue(
            facets,
          ),
          authenticationChallengeCommandWriterProvider.overrideWithValue(
            facets,
          ),
          oneTapLoginClientProvider.overrideWithValue(
            const _JourneyUnavailableOneTapClient(),
          ),
          otpAutofillGatewayProvider.overrideWithValue(
            const SystemOtpAutofillGateway(),
          ),
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          pendingOtpAttemptStoreProvider.overrideWithValue(
            _JourneyPendingOtpAttemptStore(),
          ),
          appTelemetryReporterProvider.overrideWithValue(
            RecordingAppTelemetryRecorder(),
          ),
        ],
        child: CupertinoApp(
          home: LoginFrameHost(
            dismissPolicy: LoginDismissPolicy.safeFallback,
            onDismiss: () {},
            onLoggedIn: () => targetResumed = true,
          ),
        ),
      ),
    );
    await _pumpUntilFound(
      tester,
      find.byKey(const ValueKey<String>('loginPhoneField')),
    );

    await tester.enterText(
      find.byKey(const ValueKey<String>('loginPhoneField')),
      '18013813909',
    );
    final agreementToggle = find.descendant(
      of: find.byType(LoginAgreementRow),
      matching: find.byIcon(CupertinoIcons.circle),
    );
    await tester.ensureVisible(agreementToggle);
    await tester.tap(agreementToggle);
    await tester.pump();
    expect(
      find.descendant(
        of: find.byType(LoginAgreementRow),
        matching: find.byIcon(CupertinoIcons.check_mark_circled_solid),
      ),
      findsOneWidget,
    );
    await _pumpUntilPhoneReady(tester);
    final sendOtp = find.descendant(
      of: find.byKey(const ValueKey<String>('loginPhonePrimary')),
      matching: find.byType(CupertinoButton),
    );
    await tester.ensureVisible(sendOtp);
    await tester.tap(sendOtp);
    await _pumpUntilFound(tester, find.byType(OtpCodeBoxes));

    expect(facets.sendOtpCalls, 1);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);
    expect(find.text(FoundationText.loginPhoneSubmit), findsNothing);
    await tester.enterText(
      find.byKey(const ValueKey<String>('loginOtpHiddenField')),
      '000000',
    );
    await tester.pump(const Duration(milliseconds: 350));

    expect(facets.loginCalls, 1);
    expect(targetResumed, isTrue);
  });

  testWidgets('一键入口与手机号降级在手机、平板和宽屏均完整可达', (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    for (final size in const <Size>[
      Size(430, 932),
      Size(834, 1194),
      Size(1280, 800),
    ]) {
      await tester.binding.setSurfaceSize(size);

      await _pumpJourneyLogin(
        tester,
        authStore: _JourneyReturningAuthStore(),
        oneTapClient: const _JourneyUnavailableOneTapClient(),
      );
      await _pumpUntilFound(
        tester,
        find.byKey(const ValueKey<String>('loginOneTapPrimary')),
      );
      final returningPrimary = tester.getRect(
        find.byKey(const ValueKey<String>('loginOneTapPrimary')),
      );

      expect(returningPrimary.left, greaterThanOrEqualTo(0));
      expect(returningPrimary.right, lessThanOrEqualTo(size.width));
      expect(find.text(FoundationText.loginOtherMethods), findsOneWidget);

      await _pumpJourneyLogin(
        tester,
        authStore: _JourneyAuthStore(),
        oneTapClient: const _JourneyUnavailableOneTapClient(),
      );
      await _pumpUntilFound(
        tester,
        find.byKey(const ValueKey<String>('loginPhonePrimary')),
      );
      final phonePrimary = tester.getRect(
        find.text(FoundationText.loginSendOtp),
      );
      expect(phonePrimary.left, greaterThanOrEqualTo(0));
      expect(phonePrimary.right, lessThanOrEqualTo(size.width));
      expect(find.byType(CupertinoTextField), findsOneWidget);
      expect(find.text(FoundationText.loginOtherMethods), findsOneWidget);
    }
  });
}

Future<void> _pumpUntilFound(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 2),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (finder.evaluate().isEmpty && DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 20));
  }
  expect(finder, findsOneWidget);
}

Future<void> _pumpUntilPhoneReady(WidgetTester tester) async {
  final primary = find.byKey(const ValueKey<String>('loginPhonePrimary'));
  for (var attempt = 0; attempt < 8; attempt++) {
    if (primary.evaluate().isNotEmpty) {
      final button = tester.widget<LoginActionButton>(primary);
      if (!button.busy &&
          button.enabled &&
          button.label == FoundationText.loginSendOtp) {
        return;
      }
    }
    await tester.pump(const Duration(milliseconds: 20));
  }
  expect(primary, findsOneWidget);
  final button = tester.widget<LoginActionButton>(primary);
  expect(button.busy, isFalse);
  expect(button.enabled, isTrue);
  expect(button.label, FoundationText.loginSendOtp);
}

Future<void> _pumpJourneyLogin(
  WidgetTester tester, {
  required AuthSessionStore authStore,
  required OneTapLoginClient oneTapClient,
}) async {
  final facets = _JourneyAuthFacets();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authSessionStoreProvider.overrideWithValue(authStore),
        accountSessionLoginCommandWriterProvider.overrideWithValue(facets),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(facets),
        authenticationChallengeCommandWriterProvider.overrideWithValue(facets),
        oneTapLoginClientProvider.overrideWithValue(oneTapClient),
        otpAutofillGatewayProvider.overrideWithValue(
          const SystemOtpAutofillGateway(),
        ),
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile,
        ),
        pendingOtpAttemptStoreProvider.overrideWithValue(
          _JourneyPendingOtpAttemptStore(),
        ),
        appTelemetryReporterProvider.overrideWithValue(
          RecordingAppTelemetryRecorder(),
        ),
      ],
      child: CupertinoApp(
        home: LoginFrameHost(
          key: ValueKey<int>(identityHashCode(authStore)),
          dismissPolicy: LoginDismissPolicy.safeFallback,
        ),
      ),
    ),
  );
  await tester.pump();
}

class _JourneyAuthFacets extends TestAuthFacets {
  int sendOtpCalls = 0;
  int loginCalls = 0;

  @override
  Future<OtpChallengeIssueResult> sendOtp(
    SendOtpCommand command, {
    required String idempotencyKey,
  }) async {
    sendOtpCalls += 1;
    return super.sendOtp(command, idempotencyKey: idempotencyKey);
  }

  @override
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command) async {
    loginCalls += 1;
    return super.loginWithPhone(command);
  }
}

class _JourneyAuthStore extends AuthSessionStore {
  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: '',
    ownerId: '',
    activePersonaId: '',
    accountState: '',
    identityOrigin: '',
    installId: 'uat-install',
    manualLoggedOut: true,
    launchPromptDismissed: true,
  );

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}
}

class _JourneyReturningAuthStore extends _JourneyAuthStore {
  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: '',
    ownerId: 'remembered-owner',
    activePersonaId: 'remembered-persona',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'uat-install',
    rememberedLoginMaskedIdentifier: '180****3909',
    rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
    rememberedDisplayName: '登录验收用户',
    rememberedRefreshToken: 'remembered-refresh',
    quickLoginExpiresAtEpochMs: 4102444800000,
    manualLoggedOut: true,
    launchPromptDismissed: true,
  );
}

class _JourneyUnavailableOneTapClient implements OneTapLoginClient {
  const _JourneyUnavailableOneTapClient();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<OneTapLoginProbe> probe() async => const OneTapLoginProbe(
    availability: OneTapAvailability.unsupportedPlatform,
  );

  @override
  Future<OneTapLoginResult> requestLoginToken() {
    throw UnimplementedError();
  }
}

final class _JourneyPendingOtpAttemptStore implements PendingOtpAttemptStore {
  PendingOtpAttempt? _attempt;

  @override
  Future<PendingOtpAttempt?> read() async => _attempt;

  @override
  Future<void> write(PendingOtpAttempt attempt) async {
    _attempt = attempt;
  }

  @override
  Future<void> clear() async {
    _attempt = null;
  }
}
