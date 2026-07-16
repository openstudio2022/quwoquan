import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import '../../../support/fakes/test_auth_repository.dart';

void main() {
  testWidgets('游客手机号登录：发码、六位输入与显式提交后回到目标表面', (tester) async {
    final repository = _JourneyAuthRepository();
    var targetResumed = false;

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStoreProvider.overrideWithValue(_JourneyAuthStore()),
          authRepositoryProvider.overrideWithValue(repository),
          oneTapLoginClientProvider.overrideWithValue(
            const _JourneyUnavailableOneTapClient(),
          ),
          opsEventRepositoryProvider.overrideWithValue(
            MockOpsEventRepository(),
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

    expect(repository.sendOtpCalls, 1);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);
    await tester.enterText(find.byType(CupertinoTextField).last, '000000');
    await tester.pump();
    expect(repository.loginCalls, 0, reason: '六位验证码完成后不得自动提交');

    await tester.tap(find.text(UITextConstants.loginPhoneSubmit));
    await tester.pump(const Duration(milliseconds: 350));

    expect(repository.loginCalls, 1);
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
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authSessionStoreProvider.overrideWithValue(authStore),
        authRepositoryProvider.overrideWithValue(_JourneyAuthRepository()),
        oneTapLoginClientProvider.overrideWithValue(oneTapClient),
        opsEventRepositoryProvider.overrideWithValue(MockOpsEventRepository()),
      ],
      child: const CupertinoApp(
        home: LoginFrameHost(dismissPolicy: LoginDismissPolicy.safeFallback),
      ),
    ),
  );
  await tester.pump();
}

class _JourneyAuthRepository extends TestAuthRepository {
  int sendOtpCalls = 0;
  int loginCalls = 0;

  @override
  Future<OtpSendResultData> sendOtp({
    required String phone,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? sourceOperation,
  }) async {
    sendOtpCalls += 1;
    return super.sendOtp(
      phone: phone,
      deviceId: deviceId,
      platform: platform,
      appVersion: appVersion,
      sourceOperation: sourceOperation,
    );
  }

  @override
  Future<AuthLoginResultDto> login({
    required String credentialType,
    required String credentialKey,
    String? otpCode,
    String? displayLabel,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? agreementVersion,
    String? privacyVersion,
  }) async {
    loginCalls += 1;
    return super.login(
      credentialType: credentialType,
      credentialKey: credentialKey,
      otpCode: otpCode,
      displayLabel: displayLabel,
      deviceId: deviceId,
      platform: platform,
      appVersion: appVersion,
      agreementVersion: agreementVersion,
      privacyVersion: privacyVersion,
    );
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
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
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
