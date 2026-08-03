// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/core/auth/account_restriction_support.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/di/login_dependencies.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show
        accountSessionLifecycleCommandWriterProvider,
        accountSessionLoginCommandWriterProvider,
        appCredentialBindingCommandWriterProvider,
        authenticationChallengeCommandWriterProvider;
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../support/recording_app_telemetry_recorder.dart';
import '../../../support/runtime_failure_fixtures.dart';

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
    ];
    await Future.wait(
      fonts.map((font) {
        final loader = FontLoader(font.$1)..addFont(rootBundle.load(font.$2));
        return loader.load();
      }),
    );
  });

  group('状态与错误合同', () {
    test('terminal latch 只允许一个完成方取得终态', () {
      final controller = LoginFlowController(flowId: 'flow-1');
      addTearDown(controller.dispose);

      expect(controller.tryClaimTerminal(), isTrue);
      expect(controller.tryClaimTerminal(), isFalse);
      final before = controller.state;
      controller.replace(
        LoginFlowState(step: LoginStep.phoneEntry, flowId: 'flow-1'),
      );
      expect(controller.state, same(before));
    });

    test('用户错误文案、恢复动作和可观测字段同源', () {
      final mismatch = loginFeedbackForError(
        _cloudError(
          UserErrorCode.otpMismatch,
          requestId: 'request-1',
          traceId: 'trace-1',
        ),
        origin: LoginFailureOrigin.otpVerify,
        locale: 'zh',
      );
      expect(mismatch.message, '验证码不正确');
      expect(mismatch.copyKey, 'loginOtpMismatch');
      expect(mismatch.recoveryAction, 'reenterOtp');
      expect(mismatch.clearOtp, isTrue);
      expect(mismatch.shakeOtp, isTrue);
      expect(mismatch.sourceCode, UserErrorCode.otpMismatch.code);
      expect(mismatch.requestId, 'request-1');
      expect(mismatch.traceId, 'trace-1');

      final cases = <UserErrorCode, (String, String)>{
        UserErrorCode.otpExpired: ('验证码已失效', 'resendOtp'),
        UserErrorCode.challengeConsumed: ('验证码已失效', 'resendOtp'),
        UserErrorCode.otpAttemptsExceeded: ('尝试次数较多', 'waitThenResendOtp'),
        UserErrorCode.otpProviderFailed: ('验证码发送失败', 'resendOtp'),
        UserErrorCode.wechatAuthFailed: ('授权未完成', 'retryAuthorization'),
        UserErrorCode.credentialConflict: ('这个手机号已绑定其他账号', 'changePhone'),
      };
      for (final entry in cases.entries) {
        final origin = entry.key == UserErrorCode.otpProviderFailed
            ? LoginFailureOrigin.otpSend
            : entry.key == UserErrorCode.wechatAuthFailed
            ? LoginFailureOrigin.social
            : LoginFailureOrigin.otpVerify;
        final feedback = loginFeedbackForError(
          _cloudError(entry.key),
          origin: origin,
          locale: 'zh',
        );
        expect(feedback.message, entry.value.$1, reason: entry.key.code);
        expect(feedback.recoveryAction, entry.value.$2, reason: entry.key.code);
      }
    });

    test('网络校验失败保留验证码且不伪造服务端错误码', () {
      final feedback = loginFeedbackForError(
        _cloudErrorWithoutCode(kind: RuntimeFailureKind.network),
        origin: LoginFailureOrigin.otpVerify,
        locale: 'zh',
      );
      expect(feedback.message, '暂时无法验证验证码');
      expect(feedback.preserveOtp, isTrue);
      expect(feedback.sourceCode, isNull);
      expect(feedback.failureKind, RuntimeFailureKind.network.name);
      expect(feedback.recoveryAction, 'retryVerifyOtp');
    });

    test('OTP 发送的网络、超时、服务不可用与 Provider 失败保持分轨', () {
      final cases = <RuntimeFailureKind, (String, String)>{
        RuntimeFailureKind.network: (
          '网络连接异常，请检查后重试',
          'loginNetworkUnavailable',
        ),
        RuntimeFailureKind.timeout: ('请求超时，请重试', 'loginRequestTimeout'),
        RuntimeFailureKind.unavailable: (
          '登录服务暂不可用，请重试',
          'loginOtpServiceUnavailable',
        ),
      };
      for (final entry in cases.entries) {
        final feedback = loginFeedbackForError(
          _cloudErrorWithoutCode(kind: entry.key),
          origin: LoginFailureOrigin.otpSend,
          locale: 'zh',
        );
        expect(feedback.message, entry.value.$1, reason: entry.key.name);
        expect(feedback.copyKey, entry.value.$2, reason: entry.key.name);
        expect(feedback.recoveryAction, 'resendOtp');
        expect(feedback.sourceCode, isNull);
        expect(feedback.failureKind, entry.key.name);
      }

      final provider = loginFeedbackForError(
        _cloudError(UserErrorCode.otpProviderFailed),
        origin: LoginFailureOrigin.otpSend,
        locale: 'zh',
      );
      expect(provider.message, '验证码发送失败');
      expect(provider.copyKey, 'loginOtpSendFailed');
      expect(provider.sourceCode, UserErrorCode.otpProviderFailed.code);
    });

    test('account_suspended 固定使用 generated 安全文案且与注销、临时锁定分轨', () {
      final suspended = loginFeedbackForError(
        CloudException(
          type: CloudErrorType.forbidden,
          message: 'raw exception detail',
          code: UserErrorCode.accountSuspended.code,
          userMessage:
              'reason=secret evidence=secret case=case-123 raw_exception=secret',
          runtimeFailure: testRuntimeFailure(
            code: UserErrorCode.accountSuspended.code,
            kind: RuntimeFailureKind.auth,
          ),
        ),
        origin: LoginFailureOrigin.otpVerify,
        locale: 'zh',
      );
      final deleted = loginFeedbackForError(
        _cloudError(UserErrorCode.accountDeleted),
        origin: LoginFailureOrigin.otpVerify,
        locale: 'zh',
      );
      final locked = loginFeedbackForError(
        _cloudError(UserErrorCode.loginLocked),
        origin: LoginFailureOrigin.otpVerify,
        locale: 'zh',
      );

      expect(suspended.message, UserErrorCode.accountSuspended.defaultMessage);
      expect(suspended.message, isNot(contains('secret')));
      expect(suspended.copyKey, 'loginAccountSuspended');
      expect(suspended.recoveryAction, 'openSupport');
      expect(deleted.copyKey, 'loginAccountDeleted');
      expect(deleted.recoveryAction, 'changeMethod');
      expect(locked.copyKey, 'loginAccountTemporarilyLocked');
      expect(locked.recoveryAction, 'waitThenChangeMethod');
    });

    test('产品漏斗与运维失败事件分轨且不记录敏感输入', () async {
      final recorder = RecordingAppTelemetryRecorder();
      final tracker = JourneyEventTracker(telemetryReporter: recorder);
      await tracker.trackLoginFunnel(
        action: 'login_otp_verify',
        flowId: 'flow-safe',
        step: 'otp',
        result: 'failure',
        provider: 'phone',
        otpPurpose: 'login',
        pageName: 'LoginPage',
      );
      await tracker.trackLoginOperation(
        operationId: 'verify_login_otp',
        surfaceId: 'login',
        result: 'failure',
        flowId: 'flow-safe',
        step: 'otp',
        failReasonCode: UserErrorCode.otpMismatch.code,
        failureKind: 'invalidInput',
        recoveryAction: 'reenterOtp',
        copyKey: 'loginOtpMismatch',
        feedbackSurface: 'otp',
        requestId: 'request-safe',
        traceId: 'trace-safe',
        pageName: 'LoginPage',
      );

      expect(recorder.recorded, hasLength(2));
      final funnel = recorder.recorded.first;
      final operation = recorder.recorded.last;
      expect(funnel.eventType, 'login_funnel');
      expect(funnel.extensions, isNot(contains('requestId')));
      expect(funnel.extensions, isNot(contains('traceId')));
      expect(operation.eventType, 'login_operation');
      expect(operation.extensions['requestId'], 'request-safe');
      expect(operation.extensions['traceId'], 'trace-safe');
      expect(operation.extensions['copyKey'], 'loginOtpMismatch');
      expect(operation.extensions['feedbackSurface'], 'otp');
      for (final payload in recorder.recorded.map(
        (event) => event.extensions,
      )) {
        expect(payload.values, isNot(contains('18013813909')));
        expect(payload.values, isNot(contains('123456')));
        expect(payload.keys, isNot(contains('otpCode')));
        expect(payload.keys, isNot(contains('bindingTicket')));
        expect(payload.keys, isNot(contains('token')));
      }
    });

    testWidgets('登录步骤停留九十秒会产生一次可告警的 stalled 事实', (tester) async {
      final recorder = RecordingAppTelemetryRecorder();
      await _pumpHost(tester, auth: _RecordingAuthFacets(), recorder: recorder);

      await tester.pump(const Duration(seconds: 90));

      final stalled = recorder.recorded.where(
        (event) =>
            event.eventType == 'login_funnel' &&
            event.extensions['action'] == 'login_state_changed' &&
            event.extensions['result'] == 'stalled',
      );
      expect(stalled, hasLength(1));
      expect(
        stalled.single.extensions['durationMs'],
        greaterThanOrEqualTo(90000),
      );
      expect(stalled.single.extensions, isNot(contains('requestId')));
      expect(stalled.single.extensions, isNot(contains('traceId')));
    });
  });

  group('统一布局与高保基线', () {
    testWidgets('一键登录层级、居中文案与三入口 footer 固定', (tester) async {
      final state = LoginFlowState(
        step: LoginStep.oneTap,
        flowId: 'layout',
        entryMode: LoginEntryMode.carrier,
        maskedPhone: '180****9016',
      );
      await _pumpFrame(tester, state: state);

      final primary = find.byKey(const ValueKey<String>('loginOneTapPrimary'));
      final secondary = find.byKey(
        const ValueKey<String>('loginOtherPhoneButton'),
      );
      final agreement = find.byType(LoginAgreementRow);
      final footer = find.byKey(const ValueKey<String>('loginMethodFooter'));
      expect(primary, findsOneWidget);
      expect(secondary, findsOneWidget);
      expect(agreement, findsOneWidget);
      expect(footer, findsOneWidget);
      expect(
        tester.getTopLeft(primary).dy,
        lessThan(tester.getTopLeft(secondary).dy),
      );
      expect(
        tester.getTopLeft(secondary).dy,
        lessThan(tester.getTopLeft(agreement).dy),
      );
      expect(
        tester.getTopLeft(agreement).dy,
        lessThan(tester.getTopLeft(footer).dy),
      );

      final footerDescendants = find.descendant(
        of: footer,
        matching: find.byType(Text),
      );
      final footerLabels = footerDescendants
          .evaluate()
          .map((element) => element.widget)
          .whereType<Text>()
          .map((widget) => widget.data)
          .whereType<String>()
          .toList();
      expect(footerLabels, containsAll(<String>['其他登录方式', '微信', 'QQ', '支付宝']));
      expect(footerLabels, isNot(contains('其他手机号登录')));

      for (final text in <String>['欢迎回来', '本机号码 180****9016', '其他登录方式']) {
        expect(
          tester.widget<Text>(find.text(text)).textAlign,
          TextAlign.center,
        );
      }
    });

    testWidgets('footer 在手机号、验证码和异常状态保持同一底部基线', (tester) async {
      await tester.binding.setSurfaceSize(const Size(393, 852));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final states = <LoginFlowState>[
        LoginFlowState(step: LoginStep.phoneEntry, flowId: 'phone'),
        LoginFlowState(
          step: LoginStep.otp,
          flowId: 'otp',
          phone: '18013819016',
          maskedPhone: '180****9016',
          challengeId: 'challenge',
          otpChallengeState: OtpChallengeState.active,
          resendDeadline: DateTime.now().add(const Duration(seconds: 60)),
        ),
        LoginFlowState(
          step: LoginStep.socialFailed,
          flowId: 'social-failed',
          provider: 'wechat',
          feedback: _feedback('授权未完成', 'loginSocialAuthorizationFailed'),
        ),
      ];
      final footerTops = <double>[];
      for (final state in states) {
        await _pumpFrame(tester, state: state, setSurfaceSize: false);
        footerTops.add(
          tester
              .getTopLeft(
                find.byKey(const ValueKey<String>('loginMethodFooter')),
              )
              .dy,
        );
        final scroll = find.byKey(const ValueKey<String>('loginMainScroll'));
        final footer = find.byKey(const ValueKey<String>('loginMethodFooter'));
        expect(find.descendant(of: scroll, matching: footer), findsNothing);
      }
      expect(footerTops.toSet(), hasLength(1));
    });

    testWidgets('不支持的平台仍保留三个槽位并提供具象无障碍说明', (tester) async {
      await _pumpFrame(
        tester,
        state: LoginFlowState(
          step: LoginStep.phoneEntry,
          flowId: 'unavailable',
        ),
        availability: _unavailableSocialCapabilities,
      );
      expect(find.text('微信'), findsOneWidget);
      expect(find.text('QQ'), findsOneWidget);
      expect(find.text('支付宝'), findsOneWidget);
      expect(find.bySemanticsLabel('当前设备暂不支持微信登录'), findsOneWidget);
      expect(find.bySemanticsLabel('当前设备暂不支持QQ登录'), findsOneWidget);
      expect(find.bySemanticsLabel('当前设备暂不支持支付宝登录'), findsOneWidget);
    });

    testWidgets('320px、200% 字体、键盘与 reduced motion 均保留操作出口', (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 568));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await _pumpFrame(
        tester,
        setSurfaceSize: false,
        textScaler: const TextScaler.linear(2),
        viewInsets: const EdgeInsets.only(bottom: 220),
        disableAnimations: true,
        state: LoginFlowState(
          step: LoginStep.otp,
          flowId: 'a11y',
          phone: '18013819016',
          maskedPhone: '180****9016',
          challengeId: 'challenge',
          code: '',
          otpChallengeState: OtpChallengeState.resendAvailable,
        ),
      );
      expect(tester.takeException(), isNull);
      expect(
        find.byKey(const ValueKey<String>('loginOtpResendSlot')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('loginMethodFooter')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('loginMainScroll')),
        findsOneWidget,
      );
    });

    testWidgets('五组新高保共 20 个明暗状态冻结为开发基线', (tester) async {
      await tester.binding.setSurfaceSize(const Size(393, 852));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      for (final scenario in _goldenScenarios()) {
        await _pumpFrame(
          tester,
          state: scenario.state(),
          brightness: scenario.brightness,
          setSurfaceSize: false,
          boundaryKey: ValueKey<String>('golden-${scenario.name}'),
        );
        await expectLater(
          find.byKey(ValueKey<String>('golden-${scenario.name}')),
          matchesGoldenFile('goldens/login_${scenario.name}.png'),
        );
      }
    });
  });

  group('手机号、协议与验证码交互', () {
    testWidgets('协议未勾选时弹 sheet，取消不执行，确认只恢复一次发码', (tester) async {
      final auth = _RecordingAuthFacets();
      await _pumpHost(tester, auth: auth);
      await _enterPhone(tester, '18013819016');

      await tester.tap(find.byKey(const ValueKey<String>('loginPhonePrimary')));
      await tester.pumpAndSettle();
      expect(find.text('请先阅读并同意相关协议'), findsOneWidget);
      expect(find.text('同意后即可继续登录'), findsOneWidget);
      expect(find.text('同意并继续'), findsOneWidget);
      expect(find.text('暂不'), findsOneWidget);
      expect(auth.sendOtpCalls, 0);

      await tester.tap(
        find.byKey(const ValueKey<String>('loginConsentCancel')),
      );
      await tester.pumpAndSettle();
      expect(auth.sendOtpCalls, 0);
      expect(find.byType(LoginAgreementRow), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey<String>('loginPhonePrimary')));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey<String>('loginConsentConfirm')),
      );
      await tester.pumpAndSettle();
      expect(auth.sendOtpCalls, 1);
      expect(auth.lastSendOtp?.phone, '+8618013819016');
      expect(find.text('输入验证码'), findsOneWidget);
      expect(find.text('60秒后可重新获取'), findsOneWidget);
      expect(find.text('重新获取验证码'), findsNothing);
    });

    testWidgets('输入第六位后自动验证，不出现多余登录按钮', (tester) async {
      final auth = _RecordingAuthFacets();
      var loggedIn = 0;
      await _pumpHost(tester, auth: auth, onLoggedIn: () => loggedIn += 1);
      await _reachOtp(tester);
      expect(find.text(FoundationText.loginPhoneSubmit), findsNothing);

      await tester.enterText(
        find.byKey(const ValueKey<String>('loginOtpHiddenField')),
        '286419',
      );
      await tester.pump();
      await tester.pump();
      expect(auth.phoneLoginCalls, 1);
      expect(auth.lastPhoneLogin?.phone, '+8618013819016');
      expect(auth.lastPhoneLogin?.otpCode, '286419');
      expect(loggedIn, 1);
    });

    testWidgets('验证码不正确时抖动一次、清空、首格聚焦且倒计时继续', (tester) async {
      final auth = _RecordingAuthFacets(
        phoneLoginError: _cloudError(UserErrorCode.otpMismatch),
      );
      await _pumpHost(tester, auth: auth, disableAnimations: false);
      await _reachOtp(tester);
      final countdownBefore = _resendCountdownText(tester);

      await tester.enterText(
        find.byKey(const ValueKey<String>('loginOtpHiddenField')),
        '111111',
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('验证码不正确'), findsOneWidget);
      expect(
        tester
            .widget<CupertinoTextField>(
              find.byKey(const ValueKey<String>('loginOtpHiddenField')),
            )
            .controller
            ?.text,
        isEmpty,
      );
      expect(_resendCountdownText(tester), countdownBefore);
      expect(find.text('重新获取验证码'), findsNothing);
      final context = tester.element(
        find.byKey(const ValueKey<String>('loginOtpBox0')),
      );
      for (var index = 0; index < 6; index += 1) {
        final container = tester.widget<Container>(
          find.byKey(ValueKey<String>('loginOtpBox$index')),
        );
        final decoration = container.decoration! as BoxDecoration;
        final border = decoration.border! as Border;
        expect(border.top.color, isNot(AppColors.errorForeground(context)));
      }
      final first = tester.widget<Container>(
        find.byKey(const ValueKey<String>('loginOtpBox0')),
      );
      final firstBorder =
          (first.decoration! as BoxDecoration).border! as Border;
      expect(firstBorder.top.color, AppColors.loginInputFocusedBorder(context));
    });

    testWidgets('网络校验失败保留数字并给出明确重新验证动作', (tester) async {
      final auth = _RecordingAuthFacets(
        phoneLoginError: _cloudErrorWithoutCode(
          kind: RuntimeFailureKind.network,
        ),
      );
      await _pumpHost(tester, auth: auth);
      await _reachOtp(tester);
      await tester.enterText(
        find.byKey(const ValueKey<String>('loginOtpHiddenField')),
        '123456',
      );
      await tester.pump();
      await tester.pump();

      expect(find.text('暂时无法验证验证码'), findsOneWidget);
      expect(find.text('重新验证'), findsOneWidget);
      expect(
        tester
            .widget<CupertinoTextField>(
              find.byKey(const ValueKey<String>('loginOtpHiddenField')),
            )
            .controller
            ?.text,
        '123456',
      );
      await tester.tap(
        find.byKey(const ValueKey<String>('loginOtpRetryVerify')),
      );
      await tester.pump();
      expect(auth.phoneLoginCalls, 2);
    });

    testWidgets('验证码失效后同一位置直接切为重新获取', (tester) async {
      final auth = _RecordingAuthFacets(
        phoneLoginError: _cloudError(UserErrorCode.otpExpired),
      );
      await _pumpHost(tester, auth: auth);
      await _reachOtp(tester);
      await tester.enterText(
        find.byKey(const ValueKey<String>('loginOtpHiddenField')),
        '654321',
      );
      await tester.pump();
      await tester.pump();

      expect(find.text('验证码已失效'), findsOneWidget);
      expect(find.text('重新获取验证码'), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(const ValueKey<String>('loginOtpResendSlot')),
          matching: find.text('重新获取验证码'),
        ),
        findsOneWidget,
      );
    });
  });

  group('第三方授权、绑定与退出', () {
    testWidgets('用户取消授权静默回到原入口且不进入失败死路', (tester) async {
      final auth = _RecordingAuthFacets();
      final bridge = _TestNativeAuthBridge(
        signInError: PlatformException(code: 'authorization_cancelled'),
      );
      await _pumpHost(tester, auth: auth, nativeAuthBridge: bridge);
      await _startSocial(tester, '微信');

      expect(find.text('手机号登录'), findsOneWidget);
      expect(find.text('授权未完成'), findsNothing);
      expect(find.text('重新授权'), findsNothing);
      expect(auth.socialLoginCalls, 0);
    });

    testWidgets('授权失败显示具象错误与重新授权出口', (tester) async {
      final auth = _RecordingAuthFacets(
        socialError: _cloudError(UserErrorCode.wechatAuthFailed),
      );
      await _pumpHost(tester, auth: auth);
      await _startSocial(tester, '微信');

      expect(find.text('授权未完成'), findsOneWidget);
      expect(find.text('重新授权'), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('loginMethodFooter')),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel('当前正在使用微信登录'), findsOneWidget);
    });

    testWidgets('首次社交登录必须完成手机号绑定后才签发并应用 session', (tester) async {
      final auth = _RecordingAuthFacets(
        socialOutcome: const FederatedLoginOutcome(
          status: FederatedLoginStatus.phonebindingrequired,
          bindingTicket: 'binding-ticket-1',
          provider: 'wechat',
          expiresInSeconds: 180,
        ),
      );
      final credential = _RecordingCredentialWriter();
      final store = _MutableAuthStore();
      var loggedIn = 0;
      await _pumpHost(
        tester,
        auth: auth,
        credentialWriter: credential,
        store: store,
        onLoggedIn: () => loggedIn += 1,
      );
      await _startSocial(tester, '微信');

      expect(find.text('绑定手机号'), findsOneWidget);
      expect(find.text('验证手机号后即可完成登录'), findsOneWidget);
      expect(find.byType(LoginAgreementRow), findsNothing);
      expect(store.saveLoginGrantCalls, 0);
      expect(loggedIn, 0);
      expect(find.bySemanticsLabel('当前正在使用微信登录'), findsOneWidget);

      await _enterPhone(tester, '18013819016');
      await tester.tap(find.byKey(const ValueKey<String>('loginPhonePrimary')));
      await tester.pump();
      await tester.pump();
      expect(auth.lastSendOtp?.sourceOperation, 'bind_phone');
      expect(auth.lastSendOtp?.bindingTicket, 'binding-ticket-1');
      expect(auth.lastSendOtp?.phone, '+8618013819016');

      await tester.enterText(
        find.byKey(const ValueKey<String>('loginOtpHiddenField')),
        '286419',
      );
      await tester.pump();
      await tester.pump();
      expect(credential.completeCalls, 1);
      expect(credential.lastComplete?.bindingTicket, 'binding-ticket-1');
      expect(credential.lastComplete?.challengeId, 'challenge-1');
      expect(credential.lastComplete?.phone, '+8618013819016');
      expect(store.saveLoginGrantCalls, 1);
      expect(loggedIn, 1);
    });

    testWidgets('绑定流程返回会取消 ticket 并回入口，绝不触发登录完成', (tester) async {
      final auth = _RecordingAuthFacets(
        socialOutcome: const FederatedLoginOutcome(
          status: FederatedLoginStatus.phonebindingrequired,
          bindingTicket: 'binding-ticket-return',
          provider: 'wechat',
          expiresInSeconds: 180,
        ),
      );
      var loggedIn = 0;
      await _pumpHost(tester, auth: auth, onLoggedIn: () => loggedIn += 1);
      await _startSocial(tester, '微信');
      expect(find.text('绑定手机号'), findsOneWidget);

      await tester.tap(find.bySemanticsLabel('返回上一页'));
      await tester.pump();
      expect(find.text('手机号登录'), findsOneWidget);
      expect(find.text('绑定手机号'), findsNothing);
      expect(loggedIn, 0);
    });

    testWidgets('根步骤系统返回只调用一次宿主关闭，内部 OTP 返回不关闭', (tester) async {
      var dismissed = 0;
      await _pumpHost(
        tester,
        auth: _RecordingAuthFacets(),
        onDismiss: () => dismissed += 1,
      );
      await _reachOtp(tester);

      await tester.binding.handlePopRoute();
      await tester.pump();
      expect(find.text('手机号登录'), findsOneWidget);
      expect(dismissed, 0);

      await tester.binding.handlePopRoute();
      await tester.pump();
      await tester.binding.handlePopRoute();
      await tester.pump();
      expect(dismissed, 1);
    });

    testWidgets('受限说明不探测旧凭证，提供真实官网支持并可安全关闭', (tester) async {
      final auth = _RecordingAuthFacets();
      final oneTap = _RecordingOneTapLoginClient();
      final support = _RecordingSupportLauncher();
      var dismissed = 0;

      await _pumpHost(
        tester,
        auth: auth,
        oneTapClient: oneTap,
        supportLauncher: support,
        reason: AuthPromptReason.accountSuspended.name,
        onDismiss: () => dismissed += 1,
      );

      expect(
        find.text(FoundationText.loginAccountSuspensionTitle),
        findsOneWidget,
      );
      final restrictionFeedback = find.byKey(
        const ValueKey<String>('loginFeedback-loginAccountSuspended'),
      );
      expect(restrictionFeedback, findsOneWidget);
      expect(<String>{
        UserErrorCode.accountSuspended.defaultMessageZh,
        UserErrorCode.accountSuspended.defaultMessageEn,
      }, contains(tester.widget<Text>(restrictionFeedback).data));
      expect(
        find.byKey(const ValueKey<String>('loginAccountSuspensionSupport')),
        findsOneWidget,
      );
      expect(
        find.byKey(
          const ValueKey<String>('loginAccountSuspensionOtherAccount'),
        ),
        findsOneWidget,
      );
      expect(oneTap.probeCalls, 0);
      expect(auth.refreshTokenCalls, 0);
      expect(find.textContaining('reason='), findsNothing);
      expect(find.textContaining('evidence='), findsNothing);
      expect(find.textContaining('case='), findsNothing);
      expect(find.textContaining('raw_exception'), findsNothing);
      expect(find.textContaining('申诉已提交'), findsNothing);

      await tester.tap(
        find.byKey(const ValueKey<String>('loginAccountSuspensionSupport')),
      );
      await tester.pump();
      expect(support.calls, 1);
      expect(find.textContaining('申诉已提交'), findsNothing);

      await tester.binding.handlePopRoute();
      await tester.pump();
      expect(dismissed, 1);
    });
  });
}

Future<void> _pumpFrame(
  WidgetTester tester, {
  required LoginFlowState state,
  Map<String, NativeAuthCapability> availability = _availableSocialCapabilities,
  Brightness brightness = Brightness.light,
  TextScaler textScaler = TextScaler.noScaling,
  EdgeInsets viewInsets = EdgeInsets.zero,
  bool disableAnimations = false,
  bool setSurfaceSize = true,
  EdgeInsets safePadding = const EdgeInsets.only(top: 47, bottom: 34),
  Key boundaryKey = const ValueKey<String>('login-frame-boundary'),
}) async {
  if (setSurfaceSize) {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));
  }
  final phoneController = TextEditingController(text: state.phone);
  final otpController = TextEditingController(text: state.code);
  addTearDown(phoneController.dispose);
  addTearDown(otpController.dispose);
  await tester.pumpWidget(
    CupertinoApp(
      theme: CupertinoThemeData(
        brightness: brightness,
        textTheme: _goldenCupertinoTextTheme('Noto Sans SC'),
      ),
      builder: (context, child) {
        final media = MediaQuery.of(context);
        return MediaQuery(
          data: media.copyWith(
            textScaler: textScaler,
            viewInsets: viewInsets,
            padding: safePadding,
            viewPadding: safePadding,
            disableAnimations: disableAnimations,
          ),
          child: child!,
        );
      },
      home: RepaintBoundary(
        key: boundaryKey,
        child: LoginFrame(
          state: state,
          phoneEntryHasParent: false,
          socialMethodAvailability: availability,
          phoneController: phoneController,
          otpController: otpController,
          onAgreementToggle: _noop,
          onNavigate: _noop,
          onOneTap: _noop,
          onOtherPhone: _noop,
          onPhonePrimary: _noop,
          onAgreementTap: _noop,
          onPrivacyTap: _noop,
          onSocialMethod: (_) {},
          onPhoneChanged: (_) {},
          onPhoneEditingComplete: _noop,
          onOtpChanged: (_) {},
          onResendOtp: _noop,
          onRetryOtpVerify: _noop,
          onChangePhone: _noop,
          onRetrySocial: _noop,
          onCancelSocial: _noop,
          onAccountRestrictionSupport: _noop,
          accountRestrictionSupportBusy: false,
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

Future<void> _pumpHost(
  WidgetTester tester, {
  required _RecordingAuthFacets auth,
  _RecordingCredentialWriter? credentialWriter,
  _MutableAuthStore? store,
  OneTapLoginClient oneTapClient = const _UnavailableOneTapLoginClient(),
  NativeAuthBridge nativeAuthBridge = const _TestNativeAuthBridge(),
  AccountRestrictionSupportLauncher? supportLauncher,
  RecordingAppTelemetryRecorder? recorder,
  VoidCallback? onLoggedIn,
  VoidCallback? onDismiss,
  String? reason,
  bool disableAnimations = false,
}) async {
  final authStore = store ?? _MutableAuthStore();
  final credential = credentialWriter ?? _RecordingCredentialWriter();
  final telemetry = recorder ?? RecordingAppTelemetryRecorder();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authSessionStoreProvider.overrideWithValue(authStore),
        accountSessionLoginCommandWriterProvider.overrideWithValue(auth),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(auth),
        authenticationChallengeCommandWriterProvider.overrideWithValue(auth),
        appCredentialBindingCommandWriterProvider.overrideWithValue(credential),
        oneTapLoginClientProvider.overrideWithValue(oneTapClient),
        accountRestrictionSupportLauncherProvider.overrideWithValue(
          supportLauncher ?? _RecordingSupportLauncher(),
        ),
        nativeAuthBridgeProvider.overrideWithValue(nativeAuthBridge),
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile,
        ),
        loginJourneyEventTrackerProvider.overrideWithValue(
          JourneyEventTracker(telemetryReporter: telemetry),
        ),
      ],
      child: CupertinoApp(
        builder: (context, child) {
          final media = MediaQuery.of(context);
          return MediaQuery(
            data: media.copyWith(disableAnimations: disableAnimations),
            child: child!,
          );
        },
        home: LoginFrameHost(
          reason: reason,
          dismissPolicy: LoginDismissPolicy.hostControlledClose,
          onLoggedIn: onLoggedIn ?? _noop,
          onDismiss: onDismiss ?? _noop,
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 20));
}

Future<void> _enterPhone(WidgetTester tester, String phone) async {
  await tester.enterText(
    find.byKey(const ValueKey<String>('loginPhoneField')),
    phone,
  );
  await tester.pump();
}

Future<void> _reachOtp(WidgetTester tester) async {
  await _enterPhone(tester, '18013819016');
  await tester.tap(find.byIcon(CupertinoIcons.circle));
  await tester.pump();
  await tester.tap(find.byKey(const ValueKey<String>('loginPhonePrimary')));
  await tester.pump();
  await tester.pump();
  expect(find.text('输入验证码'), findsOneWidget);
}

Future<void> _startSocial(WidgetTester tester, String label) async {
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
  expect(find.text('请先阅读并同意相关协议'), findsOneWidget);
  await tester.tap(find.byKey(const ValueKey<String>('loginConsentConfirm')));
  await tester.pumpAndSettle();
}

String _resendCountdownText(WidgetTester tester) {
  final regexp = RegExp(r'^\d+秒后可重新获取$');
  final finder = find.byWidgetPredicate(
    (widget) => widget is Text && regexp.hasMatch(widget.data ?? ''),
  );
  expect(finder, findsOneWidget);
  return tester.widget<Text>(finder).data!;
}

void _noop() {}

const Map<String, NativeAuthCapability> _availableSocialCapabilities =
    <String, NativeAuthCapability>{
      'wechat': NativeAuthCapability(
        provider: NativeAuthProvider.wechat,
        availability: NativeAuthAvailability.available,
      ),
      'qq': NativeAuthCapability(
        provider: NativeAuthProvider.qq,
        availability: NativeAuthAvailability.available,
      ),
      'alipay': NativeAuthCapability(
        provider: NativeAuthProvider.alipay,
        availability: NativeAuthAvailability.available,
      ),
    };

const Map<String, NativeAuthCapability> _unavailableSocialCapabilities =
    <String, NativeAuthCapability>{
      'wechat': NativeAuthCapability(
        provider: NativeAuthProvider.wechat,
        availability: NativeAuthAvailability.clientNotInstalled,
      ),
      'qq': NativeAuthCapability(
        provider: NativeAuthProvider.qq,
        availability: NativeAuthAvailability.clientNotInstalled,
      ),
      'alipay': NativeAuthCapability(
        provider: NativeAuthProvider.alipay,
        availability: NativeAuthAvailability.clientNotInstalled,
      ),
    };

LoginFeedback _feedback(String message, String copyKey) => LoginFeedback(
  message: message,
  copyKey: copyKey,
  surface: LoginFeedbackSurface.page,
  recoveryAction: 'retry',
);

CloudException _cloudError(
  UserErrorCode code, {
  String? requestId,
  String? traceId,
  RuntimeFailureKind kind = RuntimeFailureKind.validation,
}) {
  return CloudException(
    type: CloudErrorType.server,
    message: code.code,
    code: code.code,
    requestId: requestId,
    traceId: traceId,
    runtimeFailure: testRuntimeFailure(code: code.code, kind: kind),
  );
}

CloudException _cloudErrorWithoutCode({required RuntimeFailureKind kind}) {
  return CloudException(
    type: CloudErrorType.network,
    message: 'network unavailable',
    runtimeFailure: testRuntimeFailure(kind: kind),
  );
}

AuthSessionGrant _grant({String origin = 'phone'}) =>
    decodeAuthSessionGrant(<String, dynamic>{
      'accessToken': 'access-$origin',
      'refreshToken': 'refresh-$origin',
      'ownerId': 'owner-$origin',
      'activePersona': <String, dynamic>{'personaId': 'sub-$origin'},
      'accountState': 'active',
      'identityOrigin': origin,
      'logicalShard': 0,
      'anonymousRetentionPolicy': '',
      'personaCount': 1,
      'sessionRememberTtlSeconds': 2592000,
      'accountHint': <String, dynamic>{
        'displayName': '趣友',
        'nicknameCustomized': false,
        'avatarUrl': '',
        'avatarAssetId': '',
        'maskedPhone': '180****9016',
        'identityOrigin': origin,
      },
    });

class _RecordingAuthFacets
    implements
        AccountSessionCommandWriter,
        AuthenticationChallengeCommandWriter {
  _RecordingAuthFacets({
    this.phoneLoginError,
    this.socialError,
    FederatedLoginOutcome? socialOutcome,
    OtpChallengeIssueResult? otpResult,
  }) : socialOutcome =
           socialOutcome ??
           FederatedLoginOutcome(
             status: FederatedLoginStatus.authenticated,
             session: _grant(origin: 'wechat'),
             expiresInSeconds: 0,
           ),
       otpResult =
           otpResult ??
           const OtpChallengeIssueResult(
             maskedPhone: '180****9016',
             expiresInSeconds: 300,
             deliveryStatus: 'queued',
             retryAfterSeconds: 60,
             requestId: 'request-1',
             challengeId: 'challenge-1',
           );

  final Object? phoneLoginError;
  final Object? socialError;
  final FederatedLoginOutcome socialOutcome;
  final OtpChallengeIssueResult otpResult;
  int sendOtpCalls = 0;
  int phoneLoginCalls = 0;
  int socialLoginCalls = 0;
  int refreshTokenCalls = 0;
  SendOtpCommand? lastSendOtp;
  LoginWithPhoneCommand? lastPhoneLogin;

  @override
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command) async {
    sendOtpCalls += 1;
    lastSendOtp = command;
    return otpResult;
  }

  @override
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command) async {
    phoneLoginCalls += 1;
    lastPhoneLogin = command;
    final error = phoneLoginError;
    if (error != null) throw error;
    return _grant();
  }

  Future<FederatedLoginOutcome> _social() async {
    socialLoginCalls += 1;
    final error = socialError;
    if (error != null) throw error;
    return socialOutcome;
  }

  @override
  Future<FederatedLoginOutcome> loginWithWechat(
    LoginWithWechatCommand command,
  ) => _social();

  @override
  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command) =>
      _social();

  @override
  Future<FederatedLoginOutcome> loginWithAlipay(
    LoginWithAlipayCommand command,
  ) => _social();

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) async =>
      _grant(origin: 'one_tap');

  @override
  Future<AuthSessionGrant> loginAnonymous(
    LoginAnonymousCommand command,
  ) async => _grant(origin: 'anonymous');

  @override
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command) async {
    refreshTokenCalls += 1;
    return const TokenRefreshGrant(
      accessToken: 'access-refreshed',
      refreshToken: 'refresh-refreshed',
      sessionRememberTtlSeconds: 2592000,
    );
  }

  @override
  Future<LogoutAck> logout(LogoutCommand command) async =>
      const LogoutAck(revoked: true);

  @override
  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  ) async => AlipayAuthorizationGrant(
    authorizationPayload: 'alipay-payload',
    expiresAt: DateTime.utc(2099),
  );

  @override
  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  ) async => const OneTapLoginHint(
    state: 'new_phone',
    maskedPhone: '180****9016',
    registered: false,
    expiresInSeconds: 60,
  );
}

class _RecordingCredentialWriter implements AppCredentialBindingCommandWriter {
  int completeCalls = 0;
  CompleteFederatedPhoneBindingCommand? lastComplete;

  @override
  Future<AuthSessionGrant> completeFederatedPhoneBinding(
    CompleteFederatedPhoneBindingCommand command,
  ) async {
    completeCalls += 1;
    lastComplete = command;
    return _grant(origin: 'wechat');
  }

  @override
  Future<CredentialBindingCommandResult> bindPhoneCredential(
    BindPhoneCredentialCommand command,
  ) async => const CredentialBindingCommandResult(
    credentialType: CredentialType.phone,
    isActive: true,
    version: 1,
    idempotentReplay: false,
  );

  @override
  Future<CredentialBindingCommandResult> bindCarrierPhoneCredential(
    BindCarrierPhoneCredentialCommand command,
  ) async => const CredentialBindingCommandResult(
    credentialType: CredentialType.phone,
    isActive: true,
    version: 1,
    idempotentReplay: false,
  );

  @override
  Future<CredentialBindingCommandResult> unbindCredential(
    UnbindCredentialCommand command,
  ) async => CredentialBindingCommandResult(
    credentialType: CredentialType.fromWire(
      command.credentialType,
      'UnbindCredentialCommand.credentialType',
    ),
    isActive: false,
    version: 2,
    idempotentReplay: false,
  );
}

class _MutableAuthStore implements AuthSessionStore {
  _MutableAuthStore()
    : _stored = const StoredAuthSession(
        accessToken: '',
        refreshToken: '',
        ownerId: '',
        activePersonaId: '',
        accountState: '',
        identityOrigin: '',
        installId: 'install-test',
        manualLoggedOut: false,
        launchPromptDismissed: false,
      );

  StoredAuthSession _stored;
  int saveLoginGrantCalls = 0;

  @override
  Future<StoredAuthSession> read() async => _stored;

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    saveLoginGrantCalls += 1;
    _stored = StoredAuthSession(
      accessToken: result.accessToken,
      refreshToken: result.refreshToken,
      ownerId: result.ownerId,
      activePersonaId: result.activePersona?.personaId ?? '',
      accountState: result.accountState,
      identityOrigin: result.identityOrigin,
      installId: _stored.installId,
      rememberedLoginMethod: rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: rememberedLoginMaskedIdentifier ?? '',
      rememberedLoginIdentifier: rememberedLoginIdentifier ?? '',
      rememberedDisplayName: result.accountHint?.displayName ?? '',
      rememberedAvatarUrl: result.accountHint?.avatarUrl ?? '',
      rememberedNicknameCustomized: true,
      rememberedRefreshToken: result.refreshToken,
      quickLoginExpiresAtEpochMs:
          DateTime.now().millisecondsSinceEpoch + 2592000 * 1000,
      manualLoggedOut: false,
      launchPromptDismissed: false,
    );
  }

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> updateActivePersona(String personaId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
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
  Future<OneTapLoginResult> requestLoginToken() =>
      throw StateError('one tap is unavailable');
}

final class _RecordingOneTapLoginClient implements OneTapLoginClient {
  int probeCalls = 0;

  @override
  Future<bool> isAvailable() async => true;

  @override
  Future<OneTapLoginProbe> probe() async {
    probeCalls += 1;
    return const OneTapLoginProbe(
      availability: OneTapAvailability.available,
      vendor: 'carrier',
      carrierToken: 'must-not-be-read',
      maskedPhone: '180****0000',
    );
  }

  @override
  Future<OneTapLoginResult> requestLoginToken() =>
      throw StateError('not expected');
}

final class _RecordingSupportLauncher
    implements AccountRestrictionSupportLauncher {
  int calls = 0;

  @override
  Future<bool> openOfficialSupport() async {
    calls += 1;
    return true;
  }
}

class _TestNativeAuthBridge implements NativeAuthBridge {
  const _TestNativeAuthBridge({this.signInError});

  final Object? signInError;

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async => NativeAuthCapability(
    provider: provider,
    availability: NativeAuthAvailability.available,
  );

  @override
  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  }) async {
    final error = signInError;
    if (error != null) throw error;
    return NativeAuthResult(
      provider: provider,
      ticket: '${provider.name}-ticket',
      maskedAccount: '已授权账号',
    );
  }

  @override
  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  }) => throw StateError('passkey is outside login footer scope');
}

class _GoldenScenario {
  const _GoldenScenario(
    this.name,
    this.state, {
    this.brightness = Brightness.light,
  });

  final String name;
  final LoginFlowState Function() state;
  final Brightness brightness;
}

List<_GoldenScenario> _goldenScenarios() => <_GoldenScenario>[
  _GoldenScenario(
    '01_one_tap_unchecked',
    () => LoginFlowState(
      step: LoginStep.oneTap,
      flowId: 'g01',
      entryMode: LoginEntryMode.carrier,
      maskedPhone: '180****9016',
    ),
  ),
  _GoldenScenario(
    '02_one_tap_checked',
    () => LoginFlowState(
      step: LoginStep.oneTap,
      flowId: 'g02',
      entryMode: LoginEntryMode.carrier,
      maskedPhone: '180****9016',
      consentState: LoginConsentState.accepted,
    ),
  ),
  _GoldenScenario(
    '03_phone_empty',
    () => LoginFlowState(step: LoginStep.phoneEntry, flowId: 'g03'),
  ),
  _GoldenScenario(
    '04_phone_ready',
    () => LoginFlowState(
      step: LoginStep.phoneEntry,
      flowId: 'g04',
      phone: '18013819016',
      maskedPhone: '180****9016',
      consentState: LoginConsentState.accepted,
    ),
  ),
  _GoldenScenario('05_otp_waiting', () => _otpGoldenState(flowId: 'g05')),
  _GoldenScenario(
    '06_otp_verifying',
    () => _otpGoldenState(
      flowId: 'g06',
      code: '286419',
      operation: LoginOperation.verifyingOtp,
    ),
  ),
  _GoldenScenario(
    '07_otp_mismatch',
    () => _otpGoldenState(
      flowId: 'g07',
      feedback: _feedback('验证码不正确', 'loginOtpMismatch'),
    ),
  ),
  _GoldenScenario(
    '08_otp_resend',
    () => _otpGoldenState(
      flowId: 'g08',
      challengeState: OtpChallengeState.resendAvailable,
      deadline: DateTime.now(),
    ),
  ),
  _GoldenScenario(
    '09_otp_expired',
    () => _otpGoldenState(
      flowId: 'g09',
      challengeState: OtpChallengeState.expired,
      deadline: DateTime.now(),
      feedback: _feedback('验证码已失效', 'loginOtpExpired'),
    ),
  ),
  _GoldenScenario(
    '10_send_failed',
    () => LoginFlowState(
      step: LoginStep.phoneEntry,
      flowId: 'g10',
      phone: '18013819016',
      maskedPhone: '180****9016',
      consentState: LoginConsentState.accepted,
      feedback: _feedback('验证码发送失败', 'loginOtpSendFailed'),
    ),
  ),
  _GoldenScenario(
    '11_rate_limited',
    () => _otpGoldenState(
      flowId: 'g11',
      challengeState: OtpChallengeState.rateLimited,
      feedback: _feedback('尝试次数较多', 'loginOtpRateLimited'),
    ),
  ),
  _GoldenScenario(
    '12_blocked',
    () => LoginFlowState(
      step: LoginStep.blocked,
      flowId: 'g12',
      feedback: _feedback('登录服务暂不可用，请使用其他方式登录', 'loginUnavailable'),
    ),
  ),
  _GoldenScenario(
    '13_social_authorizing',
    () => LoginFlowState(
      step: LoginStep.socialAuthorizing,
      flowId: 'g13',
      provider: 'wechat',
      operation: LoginOperation.openingProvider,
      consentState: LoginConsentState.accepted,
    ),
  ),
  _GoldenScenario(
    '14_social_failed',
    () => LoginFlowState(
      step: LoginStep.socialFailed,
      flowId: 'g14',
      provider: 'wechat',
      feedback: _feedback('授权未完成', 'loginSocialAuthorizationFailed'),
    ),
  ),
  _GoldenScenario(
    '15_social_phone',
    () => LoginFlowState(
      step: LoginStep.socialPhoneEntry,
      flowId: 'g15',
      provider: 'wechat',
      bindingTicket: 'binding-ticket',
      bindingDeadline: DateTime.now().add(const Duration(minutes: 3)),
      consentState: LoginConsentState.accepted,
    ),
  ),
  _GoldenScenario(
    '16_social_otp',
    () => _otpGoldenState(
      flowId: 'g16',
      step: LoginStep.socialPhoneOtp,
      provider: 'wechat',
      purpose: LoginOtpPurpose.bindPhone,
      bindingTicket: 'binding-ticket',
    ),
  ),
  _GoldenScenario(
    '17_dark_one_tap',
    () => LoginFlowState(
      step: LoginStep.oneTap,
      flowId: 'g17',
      entryMode: LoginEntryMode.carrier,
      maskedPhone: '180****9016',
    ),
    brightness: Brightness.dark,
  ),
  _GoldenScenario(
    '18_dark_phone',
    () => LoginFlowState(
      step: LoginStep.phoneEntry,
      flowId: 'g18',
      phone: '18013819016',
      maskedPhone: '180****9016',
      consentState: LoginConsentState.accepted,
    ),
    brightness: Brightness.dark,
  ),
  _GoldenScenario(
    '19_dark_otp_mismatch',
    () => _otpGoldenState(
      flowId: 'g19',
      feedback: _feedback('验证码不正确', 'loginOtpMismatch'),
    ),
    brightness: Brightness.dark,
  ),
  _GoldenScenario(
    '20_dark_social_phone',
    () => LoginFlowState(
      step: LoginStep.socialPhoneEntry,
      flowId: 'g20',
      provider: 'wechat',
      bindingTicket: 'binding-ticket',
      bindingDeadline: DateTime.now().add(const Duration(minutes: 3)),
      consentState: LoginConsentState.accepted,
    ),
    brightness: Brightness.dark,
  ),
];

LoginFlowState _otpGoldenState({
  required String flowId,
  LoginStep step = LoginStep.otp,
  LoginOperation operation = LoginOperation.idle,
  OtpChallengeState challengeState = OtpChallengeState.active,
  LoginOtpPurpose purpose = LoginOtpPurpose.login,
  String code = '',
  String provider = '',
  String bindingTicket = '',
  DateTime? deadline,
  LoginFeedback? feedback,
}) {
  return LoginFlowState(
    step: step,
    flowId: flowId,
    operation: operation,
    phone: '18013819016',
    maskedPhone: '180****9016',
    code: code,
    challengeId: 'challenge-1',
    provider: provider,
    bindingTicket: bindingTicket,
    bindingDeadline: bindingTicket.isEmpty
        ? null
        : DateTime.now().add(const Duration(minutes: 3)),
    otpPurpose: purpose,
    otpChallengeState: challengeState,
    resendDeadline: deadline ?? DateTime.now().add(const Duration(seconds: 60)),
    feedback: feedback,
  );
}
