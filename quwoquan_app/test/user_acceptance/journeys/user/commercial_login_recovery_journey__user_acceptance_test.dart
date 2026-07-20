import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/fakes/test_auth_facets.dart';
import '../../../support/recording_app_telemetry_recorder.dart';

void main() {
  testWidgets('游客手机号登录：发码、六位输入与显式提交后回到目标表面', (tester) async {
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
    await tester.pump(const Duration(milliseconds: 50));

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '18013813909',
    );
    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));

    expect(facets.sendOtpCalls, 1);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);
    await tester.enterText(find.byType(CupertinoTextField).last, '000000');
    await tester.pump();
    expect(facets.loginCalls, 0, reason: '六位验证码完成后不得自动提交');

    await tester.tap(find.text(UITextConstants.loginPhoneSubmit));
    await tester.pump(const Duration(milliseconds: 350));

    expect(facets.loginCalls, 1);
    expect(targetResumed, isTrue);
  });

  testWidgets('登录两状态在手机、平板和宽屏均提供完整可达入口', (tester) async {
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
      await tester.pump(const Duration(milliseconds: 50));
      final returningPrimary = tester.getRect(
        find.text(UITextConstants.loginContinue),
      );

      expect(returningPrimary.left, greaterThanOrEqualTo(0));
      expect(returningPrimary.right, lessThanOrEqualTo(size.width));
      expect(find.text(UITextConstants.loginOtherMethods), findsOneWidget);
    }
    await tester.binding.setSurfaceSize(null);
  });
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
        appTelemetryReporterProvider.overrideWithValue(
          RecordingAppTelemetryRecorder(),
        ),
      ],
      child: const CupertinoApp(
        home: LoginFrameHost(dismissPolicy: LoginDismissPolicy.safeFallback),
      ),
    ),
  );
  await tester.pump();
}

class _JourneyAuthFacets extends TestAuthFacets {
  int sendOtpCalls = 0;
  int loginCalls = 0;

  @override
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command) async {
    sendOtpCalls += 1;
    return super.sendOtp(command);
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
    activeSubAccountId: '',
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
    refreshToken: 'remembered-refresh',
    ownerId: 'remembered-owner',
    activeSubAccountId: 'remembered-persona',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'uat-install',
    rememberedLoginMaskedIdentifier: '180****3909',
    rememberedDisplayName: '登录验收用户',
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
