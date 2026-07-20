import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons, Theme, ThemeData;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/di/login_dependencies.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
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
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:simple_icons/simple_icons.dart';
import '../../../support/runtime_failure_fixtures.dart';
import '../../../support/recording_app_telemetry_recorder.dart';

const String _defaultNicknameSample = '新同学_260622_6698692';

void main() {
  setUpAll(() async {
    final fonts = <(String, String)>[
      ('Noto Sans SC', 'assets/fonts/noto_sans_sc/NotoSansSC[wght].ttf'),
      (
        'packages/cupertino_icons/CupertinoIcons',
        'packages/cupertino_icons/assets/CupertinoIcons.ttf',
      ),
      (
        'packages/simple_icons/SimpleIcons',
        'packages/simple_icons/fonts/SimpleIcons.ttf',
      ),
      ('MaterialIcons', 'fonts/MaterialIcons-Regular.otf'),
    ];
    await Future.wait(
      fonts.map((font) {
        final loader = FontLoader(font.$1)..addFont(rootBundle.load(font.$2));
        return loader.load();
      }),
    );
  });

  test('登录事件 payload 仅保留环境、平台、provider、阶段、结果、错误码和耗时', () {
    final payload = buildLoginTelemetryPayload(
      environment: 'prod',
      platform: 'ios',
      action: 'login_phone_login_failed',
      provider: 'phone',
      raw: const <String, dynamic>{
        'code': 'USER.AUTH.otp_mismatch',
        'durationMs': 321,
        'phone': '18013813909',
        'otpCode': '123456',
        'token': 'secret-token',
        'requestId': 'request-123',
        'traceId': 'trace-456',
        'message': 'provider raw error',
      },
    );

    expect(payload.keys.toSet(), <String>{
      'environment',
      'platform',
      'provider',
      'stage',
      'result',
      'errorCode',
      'durationMs',
    });
    expect(payload['provider'], 'phone');
    expect(payload['result'], 'failure');
    expect(payload['errorCode'], 'USER.AUTH.otp_mismatch');
    expect(payload['durationMs'], 321);
    expect(payload.values, isNot(contains('18013813909')));
    expect(payload.values, isNot(contains('123456')));
    expect(payload.values, isNot(contains('secret-token')));
  });

  test('nicknameCustomized 只接受真实布尔 true，缺失或异常类型均按 false', () {
    expect(
      LoginAccountHint.fromMap(const <String, dynamic>{
        'nicknameCustomized': true,
      }).nicknameCustomized,
      isTrue,
    );
    for (final value in <dynamic>[null, false, 'true', 1]) {
      expect(
        LoginAccountHint.fromMap(<String, dynamic>{
          'nicknameCustomized': value,
        }).nicknameCustomized,
        isFalse,
      );
    }
  });

  test('返回账号必须同时具备具体账号线索，系统昵称或单独头像不构成入口', () {
    expect(
      const LoginAccountHint(
        displayName: '欢迎回来',
        maskedPhone: '',
        avatarUrl: 'https://cdn.example/avatar.png',
      ).hasConcreteIdentifier,
      isFalse,
    );
    expect(
      const LoginAccountHint(
        displayName: '真实昵称',
        maskedPhone: '',
        nicknameCustomized: true,
      ).hasConcreteIdentifier,
      isTrue,
    );
    expect(
      const LoginAccountHint(
        displayName: '',
        maskedPhone: '180****9016',
      ).hasConcreteIdentifier,
      isTrue,
    );
  });

  test('运营商入口必须有完整正向能力和可提交 token', () {
    expect(
      const OneTapLoginProbe(
        availability: OneTapAvailability.available,
        vendor: 'aliyun',
      ).canOfferLogin,
      isFalse,
    );
    expect(
      const OneTapLoginProbe(
        availability: OneTapAvailability.available,
        vendor: 'aliyun',
        carrierToken: 'short-lived-token',
      ).canOfferLogin,
      isTrue,
    );
  });

  test('短信验证码入口与过期提示使用统一完整文案', () {
    expect(UITextConstants.loginReturningSmsPrimary, '短信验证码登录');
    expect(UITextConstants.loginPhoneSubmit, '验证并登录');
    expect(UITextConstants.loginSessionExpiredHint, '登录信息已过期，请用短信验证码重新登录');
  });

  test('登录原因主副标题覆盖全部 reason 且不重复', () {
    for (final reason in AuthGateReason.values) {
      final copy = loginReasonCopyForName(reason.name);
      expect(copy.title.trim(), isNotEmpty, reason: reason.name);
      expect(copy.subtitle.trim(), isNotEmpty, reason: reason.name);
      expect(copy.title, isNot(copy.subtitle), reason: reason.name);
      expect(copy.source, LoginReasonCopySource.localApp);
    }
    for (final reason in AuthPromptReason.values) {
      final copy = loginReasonCopyForName(reason.name);
      expect(copy.title.trim(), isNotEmpty, reason: reason.name);
      expect(copy.subtitle.trim(), isNotEmpty, reason: reason.name);
      expect(copy.title, isNot(copy.subtitle), reason: reason.name);
    }
  });

  testWidgets('关闭登录页会清理待续接动作并回到宿主安全态', (tester) async {
    var dismissed = false;
    final authFacets = _RecordingAuthFacets();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionStoreProvider.overrideWithValue(_GuestLoginStore()),
          accountSessionLoginCommandWriterProvider.overrideWithValue(
            authFacets,
          ),
          accountSessionLifecycleCommandWriterProvider.overrideWithValue(
            authFacets,
          ),
          authenticationChallengeCommandWriterProvider.overrideWithValue(
            authFacets,
          ),
          oneTapLoginClientProvider.overrideWithValue(
            const _UnavailableOneTapLoginClient(),
          ),
          loginJourneyEventTrackerProvider.overrideWithValue(
            JourneyEventTracker(
              telemetryReporter: RecordingAppTelemetryRecorder(),
            ),
          ),
        ],
        child: CupertinoApp(
          home: LoginFrameHost(
            onDismiss: () => dismissed = true,
            dismissPolicy: LoginDismissPolicy.safeFallback,
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 50));
    final container = ProviderScope.containerOf(
      tester.element(find.byType(LoginFrameHost)),
    );
    container
        .read(authContinuationProvider.notifier)
        .set(
          const StartDirectCallContinuation(
            targetUserId: 'target-persona',
            callType: 'video',
          ),
          ownerToken: 'profile-call-entry',
        );
    expect(container.read(authContinuationProvider), isNotNull);

    await tester.tap(find.byIcon(CupertinoIcons.xmark));
    await tester.pump();

    expect(dismissed, isTrue);
    expect(container.read(authContinuationProvider), isNull);
  });

  test('登录错误仅由位置决定，不维护红/琥珀/灰语气分支', () {
    expect(
      loginErrorSurfaceForCode(
        UserErrorCode.otpRateLimited,
        origin: LoginFailureOrigin.otpSend,
      ),
      LoginErrorSurface.otpField,
    );
    expect(
      loginErrorSurfaceForCode(
        UserErrorCode.socialProviderUnavailable,
        origin: LoginFailureOrigin.social,
      ),
      LoginErrorSurface.socialMethod,
    );
    expect(
      loginErrorSurfaceForCode(
        UserErrorCode.accountSuspended,
        origin: LoginFailureOrigin.oneTap,
      ),
      LoginErrorSurface.accountBlocked,
    );
  });

  testWidgets('登录页 hero 使用真实趣我圈花瓣品牌标识与品牌库第三方图标', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _TestNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byIcon(CupertinoIcons.circle_grid_hex_fill), findsNothing);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is CustomPaint && widget.painter is WelcomeAppIconPainter,
      ),
      findsOneWidget,
    );
    expect(find.byIcon(SimpleIcons.wechat), findsOneWidget);
    expect(find.byIcon(SimpleIcons.qq), findsOneWidget);
    expect(find.byIcon(SimpleIcons.alipay), findsOneWidget);
    expect(find.byIcon(Icons.phone_iphone), findsNothing);
  });

  testWidgets('返回账号无头像时完全隐藏头像且其他方式名称不重复登录', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _SoftLoggedOutStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _TestNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(AppAvatarImage), findsNothing);
    expect(find.byIcon(CupertinoIcons.person_fill), findsNothing);
    expect(
      find.bySemanticsLabel(UITextConstants.loginAccountAvatarSemanticLabel),
      findsNothing,
    );
    expect(find.text('欢'), findsNothing);
    expect(find.text(UITextConstants.loginMethodWechat), findsOneWidget);
    expect(find.text(UITextConstants.loginMethodQq), findsOneWidget);
    expect(find.text(UITextConstants.loginMethodPhone), findsOneWidget);
    expect(find.text('微信登录'), findsNothing);
    expect(find.text('QQ登录'), findsNothing);
    expect(find.text('其他手机号登录'), findsNothing);
  });

  testWidgets('系统默认昵称加空标识不会生成幽灵返回账号页', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GhostSummaryStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.loginReturningDefaultName), findsNothing);
    expect(
      find.text(UITextConstants.loginReturningDefaultAccount),
      findsNothing,
    );
    expect(find.text(UITextConstants.loginContinue), findsNothing);
    expect(find.text(UITextConstants.loginOneTap), findsNothing);
    expect(find.byType(PhoneNumberField), findsOneWidget);
  });

  testWidgets('探测已初始化但没有预登录 token 时静默隐藏运营商入口', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _IncompleteProbeOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.loginOneTapPrimary), findsNothing);
    expect(find.byType(PhoneNumberField), findsOneWidget);
    expect(find.byType(AppFormErrorCard), findsNothing);
  });

  for (final scenario in <({String name, Size size, Brightness brightness})>[
    (
      name: 'light_phone',
      size: const Size(390, 844),
      brightness: Brightness.light,
    ),
    (
      name: 'dark_phone',
      size: const Size(390, 844),
      brightness: Brightness.dark,
    ),
    (name: 'narrow', size: const Size(320, 568), brightness: Brightness.light),
    (name: 'wide', size: const Size(1024, 768), brightness: Brightness.light),
  ]) {
    testWidgets('返回登录视觉基线 ${scenario.name}', (tester) async {
      await tester.binding.setSurfaceSize(scenario.size);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await _pumpLogin(
        tester,
        authStore: _SoftLoggedOutStore(),
        authRepository: _RecordingAuthFacets(),
        oneTapClient: const _UnavailableOneTapLoginClient(),
        nativeAuthBridge: const _TestNativeAuthBridge(),
        capabilities: CapabilityProfile.mobile,
        brightness: scenario.brightness,
        fontFamily: 'Noto Sans SC',
      );
      await tester.pump(const Duration(milliseconds: 50));

      await expectLater(
        find.byKey(const ValueKey<String>('login-page-test-boundary')),
        matchesGoldenFile('goldens/login_returning_${scenario.name}.png'),
      );
    });
  }

  testWidgets('登录页输入框、验证码格和其他方式图标使用同一高保 token', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _TestNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '18013813909',
    );
    await tester.pump();
    expect(
      tester.getSize(find.byType(PhoneNumberField)),
      const Size(374, AppSpacing.loginPhoneFieldHeight),
    );
    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));

    expect(find.byType(PhoneNumberField), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('loginOtpDestinationSummary')),
      findsOneWidget,
    );

    final otpContainers = tester
        .widgetList<Container>(
          find.descendant(
            of: find.byType(OtpCodeBoxes),
            matching: find.byType(Container),
          ),
        )
        .where((container) {
          final decoration = container.decoration;
          final constraints = container.constraints;
          return decoration is BoxDecoration &&
              constraints?.minWidth == AppSpacing.loginOtpBoxSize &&
              constraints?.minHeight == AppSpacing.loginOtpBoxSize &&
              decoration.borderRadius != null;
        })
        .toList();
    expect(otpContainers, hasLength(6));
    final otpDecoration = otpContainers.first.decoration! as BoxDecoration;
    final otpSurface = otpDecoration.color!;
    expect(otpSurface, isA<CupertinoDynamicColor>());
    expect(
      (otpSurface as CupertinoDynamicColor).color,
      AppColors.loginInputSurfaceLight,
    );
    expect(otpDecoration.border, isA<Border>());

    final wechatIcon = tester.widget<Icon>(find.byIcon(SimpleIcons.wechat));
    final qqIcon = tester.widget<Icon>(find.byIcon(SimpleIcons.qq));
    // 手机号验证码态只保留社交方式，品牌图标统一尺寸与白色字形。
    expect(wechatIcon.size, AppSpacing.loginOtherMethodIconSize);
    expect(qqIcon.size, AppSpacing.loginOtherMethodIconSize);
    expect(wechatIcon.color, AppColors.white);
    expect(qqIcon.color, AppColors.white);
    expect(find.byIcon(Icons.phone_iphone), findsNothing);
  });

  testWidgets('手机号输入框可输入，按钮只随手机号合法性启用', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _TestNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    final primaryButton = find.widgetWithText(
      CupertinoButton,
      UITextConstants.loginSendOtp,
    );
    expect(tester.widget<CupertinoButton>(primaryButton).onPressed, isNull);

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '18013813909',
    );
    await tester.pump();
    expect(find.text('18013813909'), findsOneWidget);
    expect(tester.widget<CupertinoButton>(primaryButton).onPressed, isNotNull);
  });

  test('登录错误码经 LoginFeedback 唯一输出状态、展示面与文案', () {
    const cases =
        <
          ({
            UserErrorCode code,
            LoginFailureOrigin origin,
            LoginErrorSurface surface,
          })
        >[
          (
            code: UserErrorCode.otpMismatch,
            origin: LoginFailureOrigin.otpLogin,
            surface: LoginErrorSurface.otpField,
          ),
          (
            code: UserErrorCode.otpExpired,
            origin: LoginFailureOrigin.otpLogin,
            surface: LoginErrorSurface.otpField,
          ),
          (
            code: UserErrorCode.otpAttemptsExceeded,
            origin: LoginFailureOrigin.otpLogin,
            surface: LoginErrorSurface.otpField,
          ),
          (
            code: UserErrorCode.otpRateLimited,
            origin: LoginFailureOrigin.otpSend,
            surface: LoginErrorSurface.otpField,
          ),
          (
            code: UserErrorCode.otpProviderFailed,
            origin: LoginFailureOrigin.otpSend,
            surface: LoginErrorSurface.otpField,
          ),
          (
            code: UserErrorCode.loginLocked,
            origin: LoginFailureOrigin.otpLogin,
            surface: LoginErrorSurface.accountBlocked,
          ),
          (
            code: UserErrorCode.accountSuspended,
            origin: LoginFailureOrigin.oneTap,
            surface: LoginErrorSurface.accountBlocked,
          ),
          (
            code: UserErrorCode.accountDeleted,
            origin: LoginFailureOrigin.social,
            surface: LoginErrorSurface.accountBlocked,
          ),
          (
            code: UserErrorCode.carrierUnavailable,
            origin: LoginFailureOrigin.oneTap,
            surface: LoginErrorSurface.topLevel,
          ),
          (
            code: UserErrorCode.carrierTokenInvalid,
            origin: LoginFailureOrigin.oneTap,
            surface: LoginErrorSurface.topLevel,
          ),
          (
            code: UserErrorCode.carrierProviderTimeout,
            origin: LoginFailureOrigin.oneTap,
            surface: LoginErrorSurface.topLevel,
          ),
          (
            code: UserErrorCode.carrierPhoneMismatch,
            origin: LoginFailureOrigin.oneTap,
            surface: LoginErrorSurface.topLevel,
          ),
          (
            code: UserErrorCode.consentRequired,
            origin: LoginFailureOrigin.social,
            surface: LoginErrorSurface.agreement,
          ),
          (
            code: UserErrorCode.wechatAuthFailed,
            origin: LoginFailureOrigin.social,
            surface: LoginErrorSurface.socialMethod,
          ),
          (
            code: UserErrorCode.alipayAuthFailed,
            origin: LoginFailureOrigin.social,
            surface: LoginErrorSurface.socialMethod,
          ),
          (
            code: UserErrorCode.qqAuthFailed,
            origin: LoginFailureOrigin.social,
            surface: LoginErrorSurface.socialMethod,
          ),
          (
            code: UserErrorCode.socialProviderUnavailable,
            origin: LoginFailureOrigin.social,
            surface: LoginErrorSurface.socialMethod,
          ),
          (
            code: UserErrorCode.socialProviderCancelled,
            origin: LoginFailureOrigin.social,
            surface: LoginErrorSurface.silent,
          ),
        ];
    for (final testCase in cases) {
      final feedback = loginFeedbackForError(
        CloudException(
          type: CloudErrorType.server,
          message: 'debug',
          code: testCase.code.code,
          runtimeFailure: testRuntimeFailure(code: testCase.code.code),
        ),
        origin: testCase.origin,
        locale: 'zh',
        entryId: 'contract-test',
        surfaceId: 'LoginPage',
      );
      final presentation = feedback.presentation;
      expect(
        presentation.phase,
        isNot(LoginPhoneOtpPhase.success),
        reason: testCase.code.code,
      );
      expect(feedback.surface, testCase.surface, reason: testCase.code.code);
      expect(feedback.message.trim(), isNotEmpty, reason: testCase.code.code);
      expect(
        feedback.isSilent,
        testCase.surface == LoginErrorSurface.silent,
        reason: testCase.code.code,
      );

      // 云端下发 userMessage 时优先采用（可经 control-plane 热配置 override）。
      final online = loginFeedbackForError(
        CloudException(
          type: CloudErrorType.server,
          message: 'debug',
          code: testCase.code.code,
          userMessage: '运营态_${testCase.code.name}',
          runtimeFailure: testRuntimeFailure(code: testCase.code.code),
        ),
        origin: testCase.origin,
        locale: 'zh',
        entryId: 'contract-test',
        surfaceId: 'LoginPage',
      );
      expect(
        online.message,
        '运营态_${testCase.code.name}',
        reason: testCase.code.code,
      );
    }
  });

  test('登录失败埋点只记录结构化恢复字段，不记录用户可见文案', () {
    const visibleMessage = '验证码错误，请重新输入';
    final feedback = loginFeedbackForError(
      CloudException(
        type: CloudErrorType.server,
        message: 'provider raw error',
        code: UserErrorCode.otpMismatch.code,
        userMessage: visibleMessage,
        requestId: 'request-123',
        traceId: 'trace-456',
        runtimeFailure: testRuntimeFailure(
          code: UserErrorCode.otpMismatch.code,
        ),
      ),
      origin: LoginFailureOrigin.otpLogin,
      locale: 'zh',
      entryId: 'contract-test',
      surfaceId: 'LoginPage',
    );

    expect(feedback.telemetry['code'], UserErrorCode.otpMismatch.code);
    expect(feedback.telemetry['recovery'], isNotEmpty);
    expect(feedback.telemetry['surface'], LoginErrorSurface.otpField.name);
    expect(feedback.telemetry['operation'], LoginFailureOrigin.otpLogin.name);
    expect(feedback.telemetry['requestId'], 'request-123');
    expect(feedback.telemetry['traceId'], 'trace-456');
    expect(feedback.telemetry.containsKey('message'), isFalse);
    expect(feedback.telemetry.values, isNot(contains(visibleMessage)));
    expect(feedback.telemetry.values, isNot(contains('provider raw error')));
  });

  test('非 CloudException 失败记录异常类型但不泄露原始消息', () {
    final feedback = loginFeedbackForError(
      StateError('missing local fixture with sensitive path'),
      origin: LoginFailureOrigin.otpLogin,
      locale: 'zh',
      entryId: 'contract-test',
      surfaceId: 'LoginPage',
    );

    expect(feedback.telemetry['code'], feedback.cloudError.runtimeFailure.code);
    expect(feedback.telemetry['failureKind'], 'contract');
    expect(feedback.telemetry['errorType'], 'StateError');
    expect(feedback.telemetry.containsKey('message'), isFalse);
    expect(
      feedback.telemetry.values,
      isNot(contains('missing local fixture with sensitive path')),
    );
  });

  testWidgets('最近账号摘要存在时展示 returningAccount，同构主按钮不本地直进', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _RememberedLoginStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );

    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.text(UITextConstants.loginReturningDefaultName),
      findsOneWidget,
    );
    expect(find.text(_defaultNicknameSample), findsNothing);
    expect(find.text('138****3909'), findsOneWidget);
    expect(find.text(UITextConstants.loginReturningHeroTitle), findsOneWidget);
    expect(
      find.text(UITextConstants.loginReturningHeroSubtitle),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.loginContinue), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTap), findsNothing);

    await tester.ensureVisible(find.text(UITextConstants.loginContinue));
    await tester.tap(find.text(UITextConstants.loginContinue));
    await tester.pump();
    expect(repo.loginOneTapCalls, 0, reason: '未勾选协议不得请求服务端');
    expect(find.text(UITextConstants.loginAgreementRequired), findsWidgets);
    await tester.pump(const Duration(seconds: 3));

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginContinue));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(repo.refreshTokenCalls, 1, reason: '最近账号态必须通过服务端 refresh 二次登录');
    expect(repo.loginOneTapCalls, 0);
  });

  testWidgets('软退出后凭证有效期内：returning 主按钮为继续登录、refresh 成功无红字', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _SoftLoggedOutStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 软退出保留熟悉感与继续登录入口（凭证仍在有效期内）。
    expect(find.text('趣友A'), findsOneWidget);
    expect(find.text(UITextConstants.loginContinue), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTap), findsNothing);
    expect(find.text(UITextConstants.loginReturningSmsPrimary), findsNothing);

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginContinue));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(repo.refreshTokenCalls, 1, reason: '有效期内一键登录应走 refresh 直接恢复');
    expect(find.text(UITextConstants.loginFailed), findsNothing);
  });

  testWidgets('过期摘要无可执行恢复动作：不展示返回账号，直接回退手机号', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _ExpiredQuickLoginStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('趣友B'), findsNothing);
    expect(find.text(UITextConstants.loginReturningSmsPrimary), findsNothing);
    expect(find.text(UITextConstants.loginOneTap), findsNothing);
    expect(
      find.text(UITextConstants.loginReturningDefaultAccount),
      findsNothing,
    );
    expect(repo.refreshTokenCalls, 0);
    expect(find.byType(PhoneNumberField), findsOneWidget);
    expect(find.text(UITextConstants.loginFailed), findsNothing);
  });

  testWidgets('彻底退出后无凭证和摘要：直接进入手机号验证码登录', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _HardLoggedOutStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.loginReturningSmsPrimary), findsNothing);
    expect(find.text(UITextConstants.loginOneTap), findsNothing);
    expect(find.text('趣友C'), findsNothing);
    expect(repo.refreshTokenCalls, 0);
    expect(find.byType(PhoneNumberField), findsOneWidget);
  });

  testWidgets('过期 returning 记住手机号 + 已勾协议：只预填，用户显式点击后发码', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _ExpiredPhoneOtpStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 先勾选协议；进入短信流程仍只能预填，不能未经确认自动发送短信。
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();

    await tester.tap(find.text(UITextConstants.loginReturningSmsPrimary));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));

    // 先只预填完整手机号，等待用户显式点击「获取验证码」。
    expect(repo.refreshTokenCalls, 0);
    expect(repo.sendOtpCalls, 0);
    expect(find.byType(OtpCodeBoxes), findsNothing);
    final phoneField = tester.widget<CupertinoTextField>(
      find.byType(CupertinoTextField).first,
    );
    expect(phoneField.controller?.text, '18013813909');
    expect(find.text(UITextConstants.loginFailed), findsNothing);
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));
    expect(repo.sendOtpCalls, 1);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);
    final otpFieldFinder = find.byType(CupertinoTextField).last;
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).focusNode?.hasFocus,
      isTrue,
      reason: '发码进入验证码态后应自动聚焦到验证码输入框',
    );
  });

  testWidgets('过期 returning 记住手机号 + 未勾协议：点主按钮预填但不自动发码并提示勾选', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _ExpiredPhoneOtpStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.text(UITextConstants.loginReturningSmsPrimary));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));

    // 未勾协议不得自动发码，但仍预填手机号并停在可发码态，给出明确下一步。
    expect(repo.sendOtpCalls, 0);
    expect(find.byType(OtpCodeBoxes), findsNothing);
    final phoneField = tester.widget<CupertinoTextField>(
      find.byType(CupertinoTextField).first,
    );
    expect(phoneField.controller?.text, '18013813909');
  });

  testWidgets('其他手机号入口仍为空号手动输入：不预填、不自动发码', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _ExpiredPhoneOtpStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 主动选择「其他手机号」走空号手动输入流程（与记住号自动续登区分）。
    final phoneEntry = find.text(UITextConstants.loginMethodPhone);
    await tester.ensureVisible(phoneEntry);
    await tester.tap(phoneEntry);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(repo.sendOtpCalls, 0);
    expect(find.byType(OtpCodeBoxes), findsNothing);
    final phoneField = tester.widget<CupertinoTextField>(
      find.byType(CupertinoTextField).first,
    );
    expect(phoneField.controller?.text, isEmpty);
  });

  testWidgets('手机号验证码输入包裹 AutofillGroup，支持系统自动填充', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(AutofillGroup), findsOneWidget);
  });

  testWidgets('无最近账号摘要但 carrier hint 为新号码时展示 carrierPhone 状态', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(
        hint: decodeOneTapLoginHint(<String, dynamic>{
          'state': 'new_phone',
          'maskedPhone': '180****3901',
          'registered': false,
          'expiresInSeconds': 60,
        }),
      ),
      oneTapClient: const _ProbeOneTapLoginClient(),
      telemetryRecorder: ops,
    );

    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('180****3901'), findsOneWidget);
    expect(find.text(UITextConstants.loginCarrierHeroTitle), findsOneWidget);
    expect(find.text(UITextConstants.loginCarrierHeroSubtitle), findsOneWidget);
    expect(find.textContaining('将创建趣我圈账号'), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTapPrimary), findsOneWidget);
    expect(
      ops.recorded.map((event) => event.action),
      containsAll(<String>['login_page_exposed', 'login_state_resolved']),
    );
  });

  testWidgets('carrier hint 命中已注册账号仍保持运营商主动作，不混用返回会话', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(
        hint: decodeOneTapLoginHint(<String, dynamic>{
          'state': 'registered',
          'maskedPhone': '180****3902',
          'registered': true,
          'accountHint': <String, dynamic>{
            'displayName': '老用户',
            'nicknameCustomized': true,
            'maskedPhone': '180****3902',
            'identityOrigin': 'phone',
          },
          'expiresInSeconds': 60,
        }),
      ),
      oneTapClient: const _ProbeOneTapLoginClient(
        token: 'carrier_token_registered',
      ),
    );

    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('老用户'), findsNothing);
    expect(find.text('180****3902'), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTapPrimary), findsOneWidget);
    expect(find.text(UITextConstants.loginContinue), findsNothing);
  });

  testWidgets('one-tap 不可用时 1.2s 内降级到手机号输入，不长时间 loading', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _HangingOneTapLoginClient(),
    );

    await tester.pump();
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 1300));
    expect(
      find.text(UITextConstants.loginPhoneNumberPlaceholder),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.loginSendOtp), findsOneWidget);
  });

  testWidgets('运营商 hint 返回受限账号时进入阻断面，不降级为手机号创建', (tester) async {
    final repo = _SuspendedHintAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: repo,
      oneTapClient: const _ProbeOneTapLoginClient(),
    );

    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.byKey(const ValueKey<String>('loginAccountBlocked')),
      findsOneWidget,
    );
    expect(find.byType(PhoneNumberField), findsNothing);
    expect(repo.loginOneTapCalls, 0);
    final blocking = tester.widget<AppFormErrorCard>(
      find.byKey(const ValueKey<String>('loginAccountBlocked')),
    );
    expect(
      blocking.semantic.message,
      UserErrorCode.accountSuspended.messageForLocale('en'),
    );
  });

  testWidgets('用户已切换手机号后迟到的运营商探测不得覆盖当前步骤', (tester) async {
    final client = _ControlledOneTapLoginClient();
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(
        hint: decodeOneTapLoginHint(<String, dynamic>{
          'state': 'new_phone',
          'maskedPhone': '180****3901',
          'registered': false,
          'expiresInSeconds': 60,
        }),
      ),
      oneTapClient: client,
    );

    await tester.ensureVisible(find.byIcon(Icons.phone_iphone));
    await tester.tap(find.byIcon(Icons.phone_iphone));
    await tester.pump();
    expect(find.byType(PhoneNumberField), findsOneWidget);

    client.completeProbe();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(PhoneNumberField), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTapPrimary), findsNothing);
  });

  testWidgets('两状态布局同构：主按钮、协议、其他登录方式纵向位置一致', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _RememberedLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));
    final returningPrimaryDy = tester
        .getTopLeft(find.text(UITextConstants.loginContinue))
        .dy;
    final returningAgreementDy = tester
        .getTopLeft(find.textContaining(UITextConstants.userAgreement))
        .dy;
    final returningOtherDy = tester
        .getTopLeft(find.text(UITextConstants.loginOtherMethods))
        .dy;

    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(
        hint: decodeOneTapLoginHint(<String, dynamic>{
          'state': 'new_phone',
          'maskedPhone': '180****3901',
          'registered': false,
          'expiresInSeconds': 60,
        }),
      ),
      oneTapClient: const _ProbeOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(
      tester.getTopLeft(find.text(UITextConstants.loginOneTapPrimary)).dy,
      returningPrimaryDy,
    );
    expect(
      tester.getTopLeft(find.textContaining(UITextConstants.userAgreement)).dy,
      returningAgreementDy,
    );
    expect(
      tester.getTopLeft(find.text(UITextConstants.loginOtherMethods)).dy,
      returningOtherDy,
    );
  });

  testWidgets('iPhone17 / iPad / Web 响应式 frame 居中且宽度受限', (tester) async {
    for (final size in const <Size>[
      Size(430, 932),
      Size(834, 1194),
      Size(1280, 800),
    ]) {
      await tester.binding.setSurfaceSize(size);
      await _pumpLogin(
        tester,
        authStore: _GuestLoginStore(),
        authRepository: _RecordingAuthFacets(
          hint: decodeOneTapLoginHint(<String, dynamic>{
            'state': 'new_phone',
            'maskedPhone': '180****3901',
            'registered': false,
            'expiresInSeconds': 60,
          }),
        ),
        oneTapClient: const _ProbeOneTapLoginClient(),
      );
      await tester.pump(const Duration(milliseconds: 50));

      final buttonRect = tester.getRect(
        find.text(UITextConstants.loginOneTapPrimary),
      );
      final accountRect = tester.getRect(find.text('180****3901'));
      expect(buttonRect.width, lessThanOrEqualTo(430));
      expect(buttonRect.center.dx, closeTo(size.width / 2, 1.0));
      expect(accountRect.center.dx, closeTo(size.width / 2, 1.0));
    }
    addTearDown(() => tester.binding.setSurfaceSize(null));
  });

  testWidgets('手机号初始态社交登录方式在 iPhone17 首屏完整可见且不重复手机号', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _TestNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    final alipayRect = tester.getRect(find.byIcon(SimpleIcons.alipay));
    final wechatRect = tester.getRect(find.byIcon(SimpleIcons.wechat));
    final otherTitleRect = tester.getRect(
      find.text(UITextConstants.loginOtherMethods),
    );
    expect(otherTitleRect.top, greaterThan(700));
    expect(alipayRect.bottom, lessThan(900));
    expect(wechatRect.height, closeTo(alipayRect.height, 0.5));
    expect(find.byIcon(Icons.phone_iphone), findsNothing);
    expect(find.text(UITextConstants.loginMethodPhone), findsNothing);
    expect(find.text(UITextConstants.loginOtherMethods), findsOneWidget);
  });

  testWidgets('勾选协议后提交 one-tap，保存 remembered summary', (tester) async {
    final store = _MutableAuthStore();
    final repo = _RecordingAuthFacets(
      hint: decodeOneTapLoginHint(<String, dynamic>{
        'state': 'new_phone',
        'maskedPhone': '180****3901',
        'registered': false,
        'expiresInSeconds': 60,
      }),
    );
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLogin(
      tester,
      authStore: store,
      authRepository: repo,
      oneTapClient: const _ProbeOneTapLoginClient(),
      telemetryRecorder: ops,
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginOneTapPrimary));
    await tester.pump(const Duration(milliseconds: 50));

    expect(repo.loginOneTapCalls, 1);
    expect(store.lastRememberedMethod, AuthRememberedLoginMethod.oneTap);
    expect(store.lastRememberedMaskedIdentifier, '180****3901');
    expect(
      ops.recorded.map((event) => event.action),
      containsAll(<String>['login_primary_clicked', 'login_success']),
    );
  });

  testWidgets('手机号 OTP 支持发码、粘贴六位验证码后显式登录', (tester) async {
    final store = _MutableAuthStore();
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: store,
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '18013813909',
    );
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump();
    expect(repo.sendOtpCalls, 0, reason: '未勾选协议不得发码');
    expect(find.text(UITextConstants.loginAgreementRequired), findsWidgets);
    await tester.pump(const Duration(seconds: 3));

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));
    expect(repo.sendOtpCalls, 1);
    expect(find.textContaining('180****3909'), findsWidgets);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);

    final otpFieldFinder = find.byType(CupertinoTextField).last;
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).focusNode?.hasFocus,
      isTrue,
      reason: '点击获取验证码后应自动聚焦到验证码输入框',
    );

    await tester.enterText(find.byType(CupertinoTextField).last, '12 34 56');
    await tester.pump();
    expect(find.text('1'), findsOneWidget);
    expect(find.text('6'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 350));
    expect(repo.phoneLoginCalls, 0, reason: '六位验证码只完成输入，不得自动提交');
    await tester.tap(find.text(UITextConstants.loginPhoneSubmit));
    await tester.pump(const Duration(milliseconds: 350));
    expect(repo.phoneLoginCalls, 1);
    expect(store.lastRememberedMethod, AuthRememberedLoginMethod.phoneOtp);
    expect(store.lastRememberedMaskedIdentifier, '180****3909');
  });

  testWidgets('发码后折叠手机号输入，点击更换手机号本地清空 challenge 展示', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _MutableAuthStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));
    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '18013813909',
    );
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));

    expect(find.byType(PhoneNumberField), findsNothing);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);
    expect(find.text(UITextConstants.loginPhoneChange), findsOneWidget);

    await tester.tap(find.text(UITextConstants.loginPhoneChange));
    await tester.pump();
    expect(find.byType(PhoneNumberField), findsOneWidget);
    expect(find.byType(OtpCodeBoxes), findsNothing);
    expect(find.text('180****3909'), findsNothing);
  });

  testWidgets('手机号输入期间不抢先显示格式错误', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _MutableAuthStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    final phoneField = find.byType(CupertinoTextField).first;
    await tester.showKeyboard(phoneField);
    await tester.pump();
    await tester.enterText(phoneField, '12345678901');
    await tester.pump();

    expect(find.text(UITextConstants.loginPhoneInvalid), findsNothing);

    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(find.text(UITextConstants.loginPhoneInvalid), findsOneWidget);
  });

  testWidgets('验证码已送达后重发失败仍保留验证码步骤与用户输入', (tester) async {
    final repo = _FailSecondOtpSendFacets();
    await _pumpLogin(
      tester,
      authStore: _MutableAuthStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
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
    await tester.enterText(find.byType(CupertinoTextField).last, '123');
    await tester.pump(const Duration(seconds: 2));

    await tester.tap(
      find.byKey(const ValueKey<String>('loginOtpResendAction')),
    );
    await tester.pump(const Duration(milliseconds: 250));

    expect(repo.sendOtpCalls, 2);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);
    expect(
      tester
          .widget<CupertinoTextField>(find.byType(CupertinoTextField).last)
          .controller
          ?.text,
      '123',
    );
    expect(find.text(UITextConstants.loginOtpSendFailed), findsOneWidget);
  });

  testWidgets('手机号 OTP 输入首位后保持焦点，可连续输入而不需重新点按', (tester) async {
    final repo = _RecordingAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _MutableAuthStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '18013813909',
    );
    await tester.pump();
    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));

    final otpFieldFinder = find.byType(CupertinoTextField).last;
    await tester.showKeyboard(otpFieldFinder);
    await tester.pump();
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).focusNode?.hasFocus,
      isTrue,
    );

    tester.testTextInput.updateEditingValue(
      const TextEditingValue(
        text: '1',
        selection: TextSelection.collapsed(offset: 1),
      ),
    );
    await tester.pump();
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).controller?.text,
      '1',
    );
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).focusNode?.hasFocus,
      isTrue,
      reason: '首位输入后不应因 phase 切换重建而丢焦点',
    );

    tester.testTextInput.updateEditingValue(
      const TextEditingValue(
        text: '12',
        selection: TextSelection.collapsed(offset: 2),
      ),
    );
    await tester.pump();
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).controller?.text,
      '12',
    );
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).focusNode?.hasFocus,
      isTrue,
      reason: '第二位输入前不应要求用户重新点击验证码框',
    );

    tester.testTextInput.updateEditingValue(
      const TextEditingValue(
        text: '123456',
        selection: TextSelection.collapsed(offset: 6),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(repo.phoneLoginCalls, 0, reason: '完成六位输入后仍等待用户点击确认');
    expect(
      tester.widget<CupertinoTextField>(otpFieldFinder).focusNode?.hasFocus,
      isTrue,
      reason: '完成输入后不应因自动提交而抢走焦点',
    );
  });

  testWidgets('验证码格在 337px 可用宽度下自适应不溢出', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _MutableAuthStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));
    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '18013813909',
    );
    await tester.pump();
    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));

    final otpRect = tester.getRect(find.byType(OtpCodeBoxes));
    final boxFinder = find.descendant(
      of: find.byType(OtpCodeBoxes),
      matching: find.byWidgetPredicate(
        (widget) =>
            widget is Container &&
            widget.decoration is BoxDecoration &&
            (widget.decoration! as BoxDecoration).borderRadius != null &&
            widget.constraints != null,
      ),
    );
    expect(boxFinder, findsNWidgets(6));
    final rightMost = tester.getRect(boxFinder.at(5));
    expect(rightMost.right, lessThanOrEqualTo(otpRect.right));
  });

  testWidgets('验证码格在 306.3px 可用宽度下会压缩间距且不溢出', (tester) async {
    final controller = TextEditingController(text: '123456');
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: SizedBox(
            width: 306.3,
            child: OtpCodeBoxes(
              controller: controller,
              enabled: true,
              hasError: false,
              onChanged: (_) {},
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);

    final otpRect = tester.getRect(find.byType(OtpCodeBoxes));
    final boxFinder = find.descendant(
      of: find.byType(OtpCodeBoxes),
      matching: find.byWidgetPredicate(
        (widget) =>
            widget is Container &&
            widget.decoration is BoxDecoration &&
            (widget.decoration! as BoxDecoration).borderRadius != null &&
            widget.constraints != null,
      ),
    );
    expect(boxFinder, findsNWidgets(6));

    final firstRect = tester.getRect(boxFinder.at(0));
    final secondRect = tester.getRect(boxFinder.at(1));
    final rightMost = tester.getRect(boxFinder.at(5));

    expect(firstRect.left, greaterThanOrEqualTo(otpRect.left));
    expect(rightMost.right, lessThanOrEqualTo(otpRect.right));
    expect(
      secondRect.left - firstRect.right,
      lessThan(AppSpacing.loginOtpBoxGap),
      reason: '窄宽度下应先压缩格间距，避免 44x44 最小输入格被撑出溢出',
    );
  });

  testWidgets('手机号 OTP 12 状态都有就近 UI 表达', (tester) async {
    final cases = <({LoginPhoneOtpState state, String expected})>[
      (
        state: const LoginPhoneOtpState.idle(),
        expected: UITextConstants.loginPhoneNumberPlaceholder,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.editing,
          phone: '180',
        ),
        expected: UITextConstants.loginPhoneNumberPlaceholder,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.invalid,
          phone: '12345678901',
          message: UITextConstants.loginPhoneInvalid,
        ),
        expected: UITextConstants.loginPhoneInvalid,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.valid,
          phone: '18013813909',
        ),
        expected: UITextConstants.loginPhoneNumberPlaceholder,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.sendingCode,
          phone: '18013813909',
        ),
        expected: UITextConstants.loginSendOtpSubmitting,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.codeSent,
          phone: '18013813909',
          maskedPhone: '180****3909',
          resendSeconds: 60,
          otpWasDelivered: true,
        ),
        expected: '重新获取(60s)',
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.codeEditing,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123',
          otpWasDelivered: true,
        ),
        expected: '3',
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.codeComplete,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
          otpWasDelivered: true,
        ),
        expected: '6',
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.loggingIn,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
          otpWasDelivered: true,
        ),
        expected: UITextConstants.loginOtpSentTo.replaceFirst(
          '%s',
          '180****3909',
        ),
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.codeError,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
          message: UITextConstants.loginOtpMismatch,
          otpWasDelivered: true,
        ),
        expected: UITextConstants.loginOtpMismatch,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.codeExpired,
          phone: '18013813909',
          maskedPhone: '180****3909',
          message: UITextConstants.loginOtpExpired,
        ),
        expected: UITextConstants.loginOtpExpired,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.rateLimited,
          phone: '18013813909',
          message: '发送过于频繁，请 60 秒后再试',
          resendSeconds: 60,
        ),
        expected: '发送过于频繁，请 60 秒后再试',
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.sendFailed,
          phone: '18013813909',
          message: UITextConstants.loginOtpSendFailed,
        ),
        expected: UITextConstants.loginOtpSendFailed,
      ),
      (
        state: LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.loginLocked,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
          message: UserErrorCode.loginLocked.defaultMessage,
        ),
        expected: UserErrorCode.loginLocked.defaultMessage,
      ),
      (
        state: LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.accountSuspended,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
          message: UserErrorCode.accountSuspended.defaultMessage,
        ),
        expected: UserErrorCode.accountSuspended.defaultMessage,
      ),
      (
        state: LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.accountDeleted,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
          message: UserErrorCode.accountDeleted.defaultMessage,
        ),
        expected: UserErrorCode.accountDeleted.defaultMessage,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.success,
          phone: '18013813909',
          maskedPhone: '180****3909',
          message: UITextConstants.loginRedirecting,
        ),
        expected: UITextConstants.loginRedirecting,
      ),
    ];

    for (final item in cases) {
      await tester.pumpWidget(
        CupertinoApp(
          home: SizedBox(
            width: 430,
            height: 260,
            child: PhoneOtpPanel(
              state: item.state,
              phoneController: TextEditingController(text: item.state.phone),
              otpController: TextEditingController(text: item.state.code),
              onPhoneChanged: (_) {},
              onOtpChanged: (_) {},
              onResend: () {},
              onChangePhone: () {},
            ),
          ),
        ),
      );
      await tester.pump();
      expect(
        find.text(item.expected),
        findsWidgets,
        reason: item.state.phase.name,
      );
    }
  });

  test('每个 OTP 子态主按钮语义都给出明确、非死路的下一步动作', () {
    String labelFor(LoginPhoneOtpPhase phase, {String code = '123456'}) {
      return LoginPhoneOtpState(
        phase: phase,
        phone: '18013813909',
        maskedPhone: '180****3909',
        code: code,
      ).primaryLabel;
    }

    // 阻断态：不诱导无效重试，统一给"换个手机号"出口。
    for (final phase in const <LoginPhoneOtpPhase>[
      LoginPhoneOtpPhase.loginLocked,
      LoginPhoneOtpPhase.accountSuspended,
      LoginPhoneOtpPhase.accountDeleted,
    ]) {
      expect(
        labelFor(phase),
        UITextConstants.loginSwitchPhone,
        reason: phase.name,
      );
      final state = LoginPhoneOtpState(
        phase: phase,
        phone: '18013813909',
        code: '123456',
      );
      expect(state.isBlocked, isTrue, reason: phase.name);
      expect(state.canLogin, isFalse, reason: phase.name);
      expect(state.canSendCode, isFalse, reason: phase.name);
    }

    // 验证码已过期：主按钮语义=重新获取验证码（文案与行为一致）。
    expect(
      labelFor(LoginPhoneOtpPhase.codeExpired, code: ''),
      UITextConstants.loginOtpResend,
    );
    expect(
      const LoginPhoneOtpState(
        phase: LoginPhoneOtpPhase.codeExpired,
        phone: '18013813909',
      ).canSendCode,
      isTrue,
    );

    // 已收到验证码且 6 位：主按钮可提交登录。
    final complete = LoginPhoneOtpState(
      phase: LoginPhoneOtpPhase.codeComplete,
      phone: '18013813909',
      code: '123456',
      otpWasDelivered: true,
    );
    expect(complete.primaryLabel, UITextConstants.loginPhoneSubmit);
    expect(complete.canLogin, isTrue);
  });

  testWidgets('OTP 输入错误与发送失败分别锚定字段提示和表单错误卡', (tester) async {
    Future<void> pumpPanel(LoginPhoneOtpState state) async {
      await tester.pumpWidget(
        CupertinoApp(
          home: PhoneOtpPanel(
            state: state,
            phoneController: TextEditingController(text: state.phone),
            otpController: TextEditingController(text: state.code),
            onPhoneChanged: (_) {},
            onOtpChanged: (_) {},
            onResend: () {},
            onChangePhone: () {},
          ),
        ),
      );
      await tester.pump();
    }

    await pumpPanel(
      const LoginPhoneOtpState(
        phase: LoginPhoneOtpPhase.invalid,
        phone: '123',
        message: UITextConstants.loginPhoneInvalid,
      ),
    );
    expect(find.byType(AppInlineFieldError), findsOneWidget);
    expect(find.byType(AppFormErrorCard), findsNothing);

    await pumpPanel(
      const LoginPhoneOtpState(
        phase: LoginPhoneOtpPhase.sendFailed,
        phone: '18013813909',
        message: UITextConstants.loginOtpSendFailed,
      ),
    );
    expect(find.byType(AppInlineFieldError), findsNothing);
    expect(find.byType(AppFormErrorCard), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('login-phone-form-error')),
      findsOneWidget,
    );
  });

  testWidgets('倒计时结束后"重新获取"可点触发重发，倒计时中禁用', (tester) async {
    var resendCalls = 0;
    Future<void> pumpPanel(LoginPhoneOtpState state) async {
      await tester.pumpWidget(
        CupertinoApp(
          home: SizedBox(
            width: 430,
            height: 260,
            child: PhoneOtpPanel(
              state: state,
              phoneController: TextEditingController(text: state.phone),
              otpController: TextEditingController(text: state.code),
              onPhoneChanged: (_) {},
              onOtpChanged: (_) {},
              onResend: () => resendCalls += 1,
              onChangePhone: () {},
            ),
          ),
        ),
      );
      await tester.pump();
    }

    await pumpPanel(
      const LoginPhoneOtpState(
        phase: LoginPhoneOtpPhase.codeSent,
        phone: '18013813909',
        maskedPhone: '180****3909',
        resendSeconds: 60,
        otpWasDelivered: true,
      ),
    );
    final countingAction = tester.widget<GestureDetector>(
      find.ancestor(
        of: find.byKey(const ValueKey<String>('loginOtpResendAction')),
        matching: find.byType(GestureDetector),
      ),
    );
    expect(countingAction.onTap, isNull, reason: '倒计时中不可点');

    await pumpPanel(
      const LoginPhoneOtpState(
        phase: LoginPhoneOtpPhase.codeError,
        phone: '18013813909',
        maskedPhone: '180****3909',
        code: '123456',
        otpWasDelivered: true,
      ),
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('loginOtpResendAction')),
    );
    await tester.pump();
    expect(resendCalls, 1, reason: '倒计时结束后可重发');
  });

  testWidgets('继续登录 refresh 失败不进死路：无红字降级短信、保留可操作出口', (tester) async {
    final repo = _FailingRefreshAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _RememberedLoginStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginContinue));
    await tester.pump(const Duration(milliseconds: 50));

    // refresh 失败后不停在空面板、也不回到注定失败的一键登录：统一降级到短信验证码流程，
    // 保留可操作短信出口；若宿主平台没有真实可发现方式，不渲染空分隔区。
    expect(find.byType(PhoneNumberField), findsOneWidget);
    expect(find.text(UITextConstants.loginOtherMethods), findsNothing);
    expect(find.text(UITextConstants.loginFailed), findsNothing);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('运营商一键登录失败降级到手机号输入并解释原因', (tester) async {
    final repo = _CarrierMismatchAuthFacets();
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: repo,
      oneTapClient: const _ProbeOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginOneTapPrimary));
    await tester.pump(const Duration(milliseconds: 50));

    // 降级到手机号输入，给出可继续的短信路径。
    expect(
      find.text(UITextConstants.loginPhoneNumberPlaceholder),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.loginSendOtp), findsOneWidget);
    final feedbackCard = tester.widget<AppFormErrorCard>(
      find.byKey(const ValueKey<String>('login-process-feedback')),
    );
    expect(feedbackCard.density, AppFormErrorCardDensity.compact);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey<String>('login-process-feedback')),
        matching: find.byType(CupertinoButton),
      ),
      findsNothing,
    );
    expect(find.text(UITextConstants.loginReturningSmsPrimary), findsNothing);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('运营商 token 失效时在同一次显式提交内刷新一次并完成登录', (tester) async {
    final store = _MutableAuthStore();
    final repo = _ExpiredThenFreshOneTapFacets();
    final client = _RefreshingOneTapLoginClient();
    await _pumpLogin(
      tester,
      authStore: store,
      authRepository: repo,
      oneTapClient: client,
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginOneTapPrimary));
    await tester.pump(const Duration(milliseconds: 100));

    expect(repo.loginOneTapCalls, 2);
    expect(client.requestLoginTokenCalls, 1, reason: '失效 token 只允许刷新一次');
    expect(store.lastRememberedMethod, AuthRememberedLoginMethod.oneTap);
  });

  testWidgets('社交授权取消静默恢复原登录态且只记录取消事件', (tester) async {
    final ops = RecordingAppTelemetryRecorder();
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _CancellingWechatNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
      telemetryRecorder: ops,
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.ensureVisible(find.byIcon(SimpleIcons.wechat));
    await tester.tap(find.byIcon(SimpleIcons.wechat));
    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.byKey(const ValueKey<String>('login-process-feedback')),
      findsNothing,
    );
    expect(find.byType(PhoneOtpPanel), findsOneWidget);
    expect(
      ops.recorded.map((event) => event.action),
      contains('login_social_cancelled'),
    );
  });

  testWidgets('社交登录失败只在唯一流程反馈槽展示，不污染 OTP 小字', (tester) async {
    const message = '微信授权暂时失败，请重试或选择其他方式';
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _SocialFailingAuthFacets(message),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _TestNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.ensureVisible(find.byIcon(SimpleIcons.wechat));
    await tester.tap(find.byIcon(SimpleIcons.wechat));
    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.byKey(const ValueKey<String>('login-social-method-feedback')),
      findsOneWidget,
    );
    expect(find.text(message), findsOneWidget);
    final liveRegions = tester.widgetList<Semantics>(
      find.descendant(
        of: find.byKey(const ValueKey<String>('login-social-method-feedback')),
        matching: find.byType(Semantics),
      ),
    );
    expect(
      liveRegions.any((node) => node.properties.liveRegion == true),
      isTrue,
    );
    expect(
      tester
          .getRect(
            find.byKey(const ValueKey<String>('login-social-method-feedback')),
          )
          .bottom,
      lessThan(tester.getRect(find.byType(OtherLoginMethodGrid)).top),
    );
    expect(find.byType(PhoneOtpPanel), findsOneWidget);
    expect(
      find.descendant(
        of: find.byType(PhoneOtpPanel),
        matching: find.text(message),
      ),
      findsNothing,
    );
  });

  testWidgets('支持平台社交方式不可用时仍可发现，点击后就近说明并提供短信恢复', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      nativeAuthBridge: const _WechatOnlyNativeAuthBridge(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byIcon(SimpleIcons.wechat), findsOneWidget);
    expect(find.byIcon(SimpleIcons.qq), findsOneWidget);
    expect(find.byIcon(SimpleIcons.alipay), findsOneWidget);
    expect(find.byIcon(Icons.phone_iphone), findsNothing);

    await tester.ensureVisible(find.byIcon(SimpleIcons.qq));
    await tester.tap(find.byIcon(SimpleIcons.qq));
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('login-social-method-feedback')),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.loginSocialClientNotInstalled),
      findsOneWidget,
    );
  });

  testWidgets('顶部为全局返回按钮（统一语义组件）且不含帮助问号图标', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.question_circle), findsNothing);
    // 返回按钮使用统一导航语义组件（尺寸/配色来自全局 token）。
    expect(
      find.ancestor(
        of: find.byIcon(CupertinoIcons.back),
        matching: find.byType(AppNavigationBarIconButton),
      ),
      findsOneWidget,
    );
  });

  testWidgets('常见 iPhone 尺寸下登录页一屏完整展示、无回弹、不可滚动', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _RememberedLoginStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 去掉 iOS 回弹/阻尼。
    final scrollView = tester.widget<SingleChildScrollView>(
      find.byType(SingleChildScrollView),
    );
    expect(scrollView.physics, isA<ClampingScrollPhysics>());

    // 内容已收紧到一屏：底部"其他登录方式"完整可见，且无可滚动余量。
    final otherRect = tester.getRect(
      find.text(UITextConstants.loginOtherMethods),
    );
    expect(otherRect.bottom, lessThanOrEqualTo(852));
    final position = Scrollable.of(
      tester.element(find.text(UITextConstants.loginContinue)),
    ).position;
    expect(position.maxScrollExtent, 0.0, reason: '一屏可容纳则不可滚动');
  });

  testWidgets('320px、200% 动态字体与键盘占位下仍可滚动到恢复出口', (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 568));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _MutableAuthStore(),
      authRepository: _RecordingAuthFacets(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
      textScaler: const TextScaler.linear(2),
      viewInsets: const EdgeInsets.only(bottom: 260),
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(tester.takeException(), isNull);
    expect(find.byType(SingleChildScrollView), findsOneWidget);
    await tester.ensureVisible(find.text(UITextConstants.loginSendOtp));
    await tester.pump();
    expect(find.text(UITextConstants.loginSendOtp), findsOneWidget);
  });
}

Future<void> _pumpLogin(
  WidgetTester tester, {
  required AuthSessionStore authStore,
  required _LoginAuthTestFacets authRepository,
  required OneTapLoginClient oneTapClient,
  RecordingAppTelemetryRecorder? telemetryRecorder,
  PlatformCapabilities? capabilities,
  NativeAuthBridge? nativeAuthBridge,
  TextScaler? textScaler,
  EdgeInsets? viewInsets,
  Brightness? brightness,
  String? fontFamily,
}) async {
  final ops = telemetryRecorder ?? RecordingAppTelemetryRecorder();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authSessionStoreProvider.overrideWithValue(authStore),
        accountSessionLoginCommandWriterProvider.overrideWithValue(
          authRepository,
        ),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          authRepository,
        ),
        authenticationChallengeCommandWriterProvider.overrideWithValue(
          authRepository,
        ),
        oneTapLoginClientProvider.overrideWithValue(oneTapClient),
        loginJourneyEventTrackerProvider.overrideWithValue(
          JourneyEventTracker(telemetryReporter: ops),
        ),
        if (capabilities != null)
          platformCapabilitiesProvider.overrideWithValue(capabilities),
        if (nativeAuthBridge != null)
          nativeAuthBridgeProvider.overrideWithValue(nativeAuthBridge),
      ],
      child: CupertinoApp(
        theme: CupertinoThemeData(
          brightness: brightness,
          textTheme: fontFamily == null
              ? null
              : _goldenCupertinoTextTheme(fontFamily),
        ),
        builder: (context, child) {
          final media = MediaQuery.of(context);
          final mediaChild = MediaQuery(
            data: media.copyWith(
              textScaler: textScaler,
              viewInsets: viewInsets,
            ),
            child: child!,
          );
          if (fontFamily == null) {
            return mediaChild;
          }
          return Theme(
            data: ThemeData(
              brightness: brightness ?? Brightness.light,
              fontFamily: fontFamily,
            ),
            child: mediaChild,
          );
        },
        home: RepaintBoundary(
          key: const ValueKey<String>('login-page-test-boundary'),
          child: LoginPage(key: UniqueKey()),
        ),
      ),
    ),
  );
  await tester.pump();
}

CupertinoTextThemeData _goldenCupertinoTextTheme(String fontFamily) {
  const base = CupertinoTextThemeData();
  TextStyle withFamily(TextStyle style) => style.copyWith(
    fontFamily: fontFamily,
    fontFamilyFallback: const <String>[],
  );
  return CupertinoTextThemeData(
    textStyle: withFamily(base.textStyle),
    actionTextStyle: withFamily(base.actionTextStyle),
    actionSmallTextStyle: withFamily(base.actionSmallTextStyle),
    tabLabelTextStyle: withFamily(base.tabLabelTextStyle),
    navTitleTextStyle: withFamily(base.navTitleTextStyle),
    navLargeTitleTextStyle: withFamily(base.navLargeTitleTextStyle),
    navActionTextStyle: withFamily(base.navActionTextStyle),
    pickerTextStyle: withFamily(base.pickerTextStyle),
    dateTimePickerTextStyle: withFamily(base.dateTimePickerTextStyle),
  );
}

class _ProbeOneTapLoginClient implements OneTapLoginClient {
  const _ProbeOneTapLoginClient({this.token = 'carrier_token_new'});

  final String token;

  @override
  Future<bool> isAvailable() async => true;

  @override
  Future<OneTapLoginProbe> probe() async => OneTapLoginProbe(
    availability: OneTapAvailability.available,
    vendor: 'test',
    carrierToken: token,
    maskedPhone: '180****3901',
  );

  @override
  Future<OneTapLoginResult> requestLoginToken() async => OneTapLoginResult(
    vendor: 'test',
    carrierToken: token,
    maskedPhone: '180****3901',
  );
}

class _RefreshingOneTapLoginClient implements OneTapLoginClient {
  int requestLoginTokenCalls = 0;

  @override
  Future<bool> isAvailable() async => true;

  @override
  Future<OneTapLoginProbe> probe() async => const OneTapLoginProbe(
    availability: OneTapAvailability.available,
    vendor: 'test',
    carrierToken: 'expired_token',
    maskedPhone: '180****3901',
  );

  @override
  Future<OneTapLoginResult> requestLoginToken() async {
    requestLoginTokenCalls += 1;
    return const OneTapLoginResult(
      vendor: 'test',
      carrierToken: 'fresh_token',
      maskedPhone: '180****3901',
    );
  }
}

class _UnavailableOneTapLoginClient implements OneTapLoginClient {
  const _UnavailableOneTapLoginClient();

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

class _IncompleteProbeOneTapLoginClient implements OneTapLoginClient {
  const _IncompleteProbeOneTapLoginClient();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<OneTapLoginProbe> probe() async => const OneTapLoginProbe(
    availability: OneTapAvailability.available,
    vendor: 'aliyun',
    reason: 'prelogin_token_not_resolved',
  );

  @override
  Future<OneTapLoginResult> requestLoginToken() {
    throw StateError('incomplete probe must not expose a login entry');
  }
}

class _HangingOneTapLoginClient implements OneTapLoginClient {
  const _HangingOneTapLoginClient();

  @override
  Future<bool> isAvailable() => Completer<bool>().future;

  @override
  Future<OneTapLoginProbe> probe() => Completer<OneTapLoginProbe>().future;

  @override
  Future<OneTapLoginResult> requestLoginToken() =>
      Completer<OneTapLoginResult>().future;
}

class _ControlledOneTapLoginClient implements OneTapLoginClient {
  final Completer<OneTapLoginProbe> _probeCompleter =
      Completer<OneTapLoginProbe>();

  void completeProbe() {
    _probeCompleter.complete(
      const OneTapLoginProbe(
        availability: OneTapAvailability.available,
        vendor: 'test',
        carrierToken: 'late_carrier_token',
        maskedPhone: '180****3901',
      ),
    );
  }

  @override
  Future<bool> isAvailable() async => true;

  @override
  Future<OneTapLoginProbe> probe() => _probeCompleter.future;

  @override
  Future<OneTapLoginResult> requestLoginToken() {
    throw UnimplementedError();
  }
}

class _TestNativeAuthBridge implements NativeAuthBridge {
  const _TestNativeAuthBridge();

  static const _providers = <NativeAuthProvider>{
    NativeAuthProvider.wechat,
    NativeAuthProvider.alipay,
    NativeAuthProvider.qq,
  };

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async {
    final available = _providers.contains(provider);
    return NativeAuthCapability(
      provider: provider,
      availability: available
          ? NativeAuthAvailability.available
          : NativeAuthAvailability.clientNotInstalled,
      reason: available ? 'test_fixture' : 'unsupported_in_test',
    );
  }

  @override
  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  }) async {
    if (!_providers.contains(provider)) {
      throw StateError('${provider.name} test auth is unavailable');
    }
    return NativeAuthResult(
      provider: provider,
      ticket: 'test-${provider.name}-ticket',
    );
  }

  @override
  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  }) async {
    throw StateError('passkey test auth is unavailable');
  }
}

class _WechatOnlyNativeAuthBridge implements NativeAuthBridge {
  const _WechatOnlyNativeAuthBridge();

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async {
    final available = provider == NativeAuthProvider.wechat;
    return NativeAuthCapability(
      provider: provider,
      availability: available
          ? NativeAuthAvailability.available
          : NativeAuthAvailability.clientNotInstalled,
      reason: available ? 'available' : 'not_installed',
    );
  }

  @override
  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  }) async {
    return NativeAuthResult(provider: provider, ticket: 'wechat-code');
  }

  @override
  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  }) {
    throw UnimplementedError();
  }
}

class _CancellingWechatNativeAuthBridge extends _WechatOnlyNativeAuthBridge {
  const _CancellingWechatNativeAuthBridge();

  @override
  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  }) {
    throw PlatformException(code: 'authorization_cancelled');
  }
}

abstract interface class _LoginAuthTestFacets
    implements
        AccountSessionCommandWriter,
        AuthenticationChallengeCommandWriter {}

class _RecordingAuthFacets implements _LoginAuthTestFacets {
  _RecordingAuthFacets({OneTapLoginHint? hint})
    : hint =
          hint ??
          const OneTapLoginHint(
            state: 'unavailable',
            maskedPhone: '',
            registered: false,
            expiresInSeconds: 0,
          );

  final OneTapLoginHint hint;
  int loginOneTapCalls = 0;
  int refreshTokenCalls = 0;
  int sendOtpCalls = 0;
  int phoneLoginCalls = 0;

  @override
  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  ) async => hint;

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) async {
    loginOneTapCalls += 1;
    return decodeAuthSessionGrant(<String, dynamic>{
      'accessToken': 'access',
      'refreshToken': 'refresh',
      'ownerId': 'owner',
      'activeSub': <String, dynamic>{'subAccountId': 'sub'},
      'accountState': 'active',
      'identityOrigin': 'phone',
      'subAccountCount': 1,
      'accountHint': <String, dynamic>{
        'displayName': '趣友3901',
        'maskedPhone': '180****3901',
      },
    });
  }

  @override
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command) async {
    sendOtpCalls += 1;
    return const OtpChallengeIssueResult(
      maskedPhone: '180****3909',
      expiresInSeconds: 300,
      deliveryStatus: 'queued',
      retryAfterSeconds: 0,
      requestId: 'request-1',
      challengeId: 'challenge-1',
    );
  }

  @override
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command) async {
    phoneLoginCalls += 1;
    return decodeAuthSessionGrant(<String, dynamic>{
      'accessToken': 'phone_access',
      'refreshToken': 'phone_refresh',
      'ownerId': 'phone_owner',
      'activeSub': <String, dynamic>{'subAccountId': 'phone_sub'},
      'accountState': 'active',
      'identityOrigin': 'phone',
      'subAccountCount': 1,
      'accountHint': <String, dynamic>{
        'displayName': _defaultNicknameSample,
        'maskedPhone': '180****3909',
      },
    });
  }

  @override
  Future<AuthSessionGrant> loginWithWechat(LoginWithWechatCommand command) =>
      throw UnimplementedError();

  @override
  Future<AuthSessionGrant> loginWithAlipay(LoginWithAlipayCommand command) =>
      throw UnimplementedError();

  @override
  Future<AuthSessionGrant> loginWithQq(LoginWithQqCommand command) =>
      throw UnimplementedError();

  @override
  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command) =>
      throw UnimplementedError();

  @override
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command) async {
    refreshTokenCalls += 1;
    return const TokenRefreshGrant(
      accessToken: 'refreshed_access',
      refreshToken: 'refreshed_refresh',
      sessionRememberTtlSeconds: 0,
    );
  }

  @override
  Future<LogoutAck> logout(LogoutCommand command) async =>
      const LogoutAck(revoked: true);

  @override
  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  ) async {
    return const AlipayAuthorizationGrant(
      authorizationPayload: 'test-alipay-authorization',
      expiresAt: '2099-01-01T00:00:00Z',
    );
  }
}

class _SuspendedHintAuthFacets extends _RecordingAuthFacets {
  @override
  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  ) {
    throw CloudException(
      type: CloudErrorType.forbidden,
      message: 'account is suspended',
      code: UserErrorCode.accountSuspended.code,
      runtimeFailure: testRuntimeFailure(
        code: UserErrorCode.accountSuspended.code,
      ),
    );
  }
}

class _SocialFailingAuthFacets extends _RecordingAuthFacets {
  _SocialFailingAuthFacets(this.userMessage);

  final String userMessage;

  @override
  Future<AuthSessionGrant> loginWithWechat(LoginWithWechatCommand command) {
    throw CloudException(
      type: CloudErrorType.server,
      message: 'provider rejected authorization',
      code: UserErrorCode.wechatAuthFailed.code,
      userMessage: userMessage,
      runtimeFailure: testRuntimeFailure(
        code: UserErrorCode.wechatAuthFailed.code,
      ),
    );
  }
}

class _ExpiredThenFreshOneTapFacets extends _RecordingAuthFacets {
  _ExpiredThenFreshOneTapFacets()
    : super(
        hint: decodeOneTapLoginHint(<String, dynamic>{
          'state': 'new_phone',
          'maskedPhone': '180****3901',
          'registered': false,
          'expiresInSeconds': 60,
        }),
      );

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) {
    if (command.carrierToken == 'expired_token') {
      loginOneTapCalls += 1;
      throw CloudException(
        type: CloudErrorType.server,
        message: 'carrier token expired',
        code: UserErrorCode.carrierTokenInvalid.code,
        runtimeFailure: testRuntimeFailure(
          code: UserErrorCode.carrierTokenInvalid.code,
        ),
      );
    }
    return super.loginOneTap(command);
  }
}

class _FailSecondOtpSendFacets extends _RecordingAuthFacets {
  @override
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command) async {
    if (sendOtpCalls == 0) {
      sendOtpCalls += 1;
      return const OtpChallengeIssueResult(
        maskedPhone: '180****3909',
        expiresInSeconds: 300,
        retryAfterSeconds: 1,
        deliveryStatus: 'queued',
        requestId: 'request-1',
        challengeId: 'challenge-1',
      );
    }
    sendOtpCalls += 1;
    throw CloudException(
      type: CloudErrorType.server,
      message: 'sms provider unavailable',
      code: UserErrorCode.otpProviderFailed.code,
      userMessage: UITextConstants.loginOtpSendFailed,
      runtimeFailure: testRuntimeFailure(
        code: UserErrorCode.otpProviderFailed.code,
      ),
    );
  }
}

/// 最近账号二次登录（服务端 refresh）失败：用于验证不进死路。
class _FailingRefreshAuthFacets extends _RecordingAuthFacets {
  @override
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command) async {
    throw CloudException(
      type: CloudErrorType.server,
      message: 'refresh failed',
      userMessage: '会话已过期，请重新登录或换其它方式',
      runtimeFailure: testRuntimeFailure(code: 'USER.AUTH.refresh_failed'),
    );
  }
}

/// 运营商一键登录返回号码不一致（surface），用于验证降级到手机号输入。
class _CarrierMismatchAuthFacets extends _RecordingAuthFacets {
  _CarrierMismatchAuthFacets()
    : super(
        hint: decodeOneTapLoginHint(<String, dynamic>{
          'state': 'new_phone',
          'maskedPhone': '180****3901',
          'registered': false,
          'expiresInSeconds': 60,
        }),
      );

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) async {
    throw CloudException(
      type: CloudErrorType.server,
      message: 'carrier phone mismatch',
      code: UserErrorCode.carrierPhoneMismatch.code,
      userMessage: '运营商号码校验未通过，请改用短信验证码登录',
      runtimeFailure: testRuntimeFailure(
        code: UserErrorCode.carrierPhoneMismatch.code,
      ),
    );
  }
}

class _GuestLoginStore extends _MutableAuthStore {
  _GuestLoginStore();
}

class _GhostSummaryStore extends _MutableAuthStore {
  _GhostSummaryStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: 'still-valid-but-unidentifiable',
    ownerId: '',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: 'phone',
    installId: 'install-id',
    rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
    rememberedLoginMaskedIdentifier: '',
    rememberedDisplayName: '欢迎回来',
    rememberedAvatarUrl: 'https://cdn.example/avatar.png',
    rememberedNicknameCustomized: false,
    manualLoggedOut: true,
    launchPromptDismissed: false,
  );
}

class _RememberedLoginStore extends _MutableAuthStore {
  _RememberedLoginStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: 'remembered_refresh',
    ownerId: '',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
    rememberedLoginMaskedIdentifier: '138****3909',
    rememberedDisplayName: _defaultNicknameSample,
    rememberedAvatarUrl: '',
    manualLoggedOut: false,
    launchPromptDismissed: false,
  );
}

/// 软退出后：保留 refreshToken 与账号摘要，快速登录凭证仍在有效期内。
class _SoftLoggedOutStore extends _MutableAuthStore {
  _SoftLoggedOutStore();

  @override
  Future<StoredAuthSession> read() async => StoredAuthSession(
    accessToken: '',
    refreshToken: 'soft_refresh',
    ownerId: 'owner-soft',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    lastForegroundAuthCheckAtEpochMs: 0,
    rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
    rememberedLoginMaskedIdentifier: '138****0001',
    rememberedDisplayName: '趣友A',
    rememberedAvatarUrl: '',
    rememberedNicknameCustomized: true,
    quickLoginExpiresAtEpochMs:
        DateTime.now().millisecondsSinceEpoch + 7 * 86400 * 1000,
    manualLoggedOut: true,
    launchPromptDismissed: false,
  );
}

/// 软退出后凭证已过期：保留摘要，但快速登录凭证不可用。
class _ExpiredQuickLoginStore extends _MutableAuthStore {
  _ExpiredQuickLoginStore();

  @override
  Future<StoredAuthSession> read() async => StoredAuthSession(
    accessToken: '',
    refreshToken: 'expired_refresh',
    ownerId: 'owner-exp',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs:
        DateTime.now().millisecondsSinceEpoch - 40 * 86400 * 1000,
    lastForegroundAuthCheckAtEpochMs: 0,
    rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
    rememberedLoginMaskedIdentifier: '138****0002',
    rememberedDisplayName: '趣友B',
    rememberedAvatarUrl: '',
    rememberedNicknameCustomized: true,
    quickLoginExpiresAtEpochMs: DateTime.now().millisecondsSinceEpoch - 1000,
    manualLoggedOut: true,
    launchPromptDismissed: false,
  );
}

/// 软退出后凭证已过期，但本机以手机号方式登录并记住完整手机号：
/// 用于验证过期 returning 点主按钮可自动预填手机号 + 自动发码。
class _ExpiredPhoneOtpStore extends _MutableAuthStore {
  _ExpiredPhoneOtpStore();

  @override
  Future<StoredAuthSession> read() async => StoredAuthSession(
    accessToken: '',
    refreshToken: 'expired_refresh',
    ownerId: 'owner-exp-phone',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs:
        DateTime.now().millisecondsSinceEpoch - 40 * 86400 * 1000,
    lastForegroundAuthCheckAtEpochMs: 0,
    rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
    rememberedLoginMaskedIdentifier: '180****3909',
    rememberedLoginIdentifier: '18013813909',
    rememberedDisplayName: '欢迎回来',
    rememberedAvatarUrl: '',
    quickLoginExpiresAtEpochMs: DateTime.now().millisecondsSinceEpoch - 1000,
    manualLoggedOut: true,
    launchPromptDismissed: false,
  );
}

/// 彻底退出后：凭证与展示摘要均已清除。
class _HardLoggedOutStore extends _MutableAuthStore {
  _HardLoggedOutStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: '',
    ownerId: '',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: '',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    manualLoggedOut: true,
    launchPromptDismissed: false,
  );
}

class _MutableAuthStore implements AuthSessionStore {
  _MutableAuthStore();

  AuthRememberedLoginMethod? _lastRememberedMethod;
  String? _lastRememberedMaskedIdentifier;
  String? _lastRememberedIdentifier;

  AuthRememberedLoginMethod? get lastRememberedMethod => _lastRememberedMethod;
  String? get lastRememberedMaskedIdentifier => _lastRememberedMaskedIdentifier;
  String? get lastRememberedIdentifier => _lastRememberedIdentifier;

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: '',
    ownerId: '',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: '',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    manualLoggedOut: false,
    launchPromptDismissed: false,
  );

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    _lastRememberedMethod = rememberedLoginMethod;
    _lastRememberedMaskedIdentifier = rememberedLoginMaskedIdentifier;
    _lastRememberedIdentifier = rememberedLoginIdentifier;
  }

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}
