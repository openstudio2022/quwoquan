import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/one_tap_login_hint_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';
import 'package:simple_icons/simple_icons.dart';

const String _defaultNicknameSample = '新同学_260622_6698692';
final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

void main() {
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

  test('消息语气分级：仅锁定/封禁/注销为阻断红，频繁为告警，其余中性', () {
    const blockingPhases = <LoginPhoneOtpPhase>{
      LoginPhoneOtpPhase.loginLocked,
      LoginPhoneOtpPhase.accountSuspended,
      LoginPhoneOtpPhase.accountDeleted,
    };
    for (final phase in LoginPhoneOtpPhase.values) {
      final tone = loginMessageToneForPhase(phase);
      if (blockingPhases.contains(phase)) {
        expect(tone, LoginMessageTone.blocking, reason: phase.name);
      } else if (phase == LoginPhoneOtpPhase.rateLimited) {
        expect(tone, LoginMessageTone.warning, reason: phase.name);
      } else {
        expect(tone, LoginMessageTone.neutral, reason: phase.name);
      }
    }
    // 验证码错误/过期/发送失败等可恢复态绝不用阻断红。
    expect(
      loginMessageToneForPhase(LoginPhoneOtpPhase.codeError),
      LoginMessageTone.neutral,
    );
    expect(
      loginMessageToneForPhase(LoginPhoneOtpPhase.codeExpired),
      LoginMessageTone.neutral,
    );
    expect(
      loginMessageToneForPhase(LoginPhoneOtpPhase.sendFailed),
      LoginMessageTone.neutral,
    );
  });

  testWidgets('消息语气取色：阻断红与可恢复非红区分明确', (tester) async {
    late BuildContext capturedContext;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) {
            capturedContext = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    final blocking = loginMessageToneColor(
      capturedContext,
      LoginMessageTone.blocking,
    );
    final warning = loginMessageToneColor(
      capturedContext,
      LoginMessageTone.warning,
    );
    final neutral = loginMessageToneColor(
      capturedContext,
      LoginMessageTone.neutral,
    );

    expect(blocking, AppColors.iosDestructive(capturedContext));
    expect(warning, AppColors.warning);
    expect(neutral, AppColors.iosSecondaryLabel(capturedContext));
    expect(blocking, isNot(neutral));
    expect(blocking, isNot(warning));
  });

  testWidgets('登录页 hero 使用真实趣我圈花瓣品牌标识与品牌库第三方图标', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
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
    expect(find.byIcon(Icons.phone_iphone), findsOneWidget);
  });

  testWidgets('登录页输入框、验证码格和其他方式图标使用同一高保 token', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(),
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

    expect(
      tester.getSize(find.byType(PhoneNumberField)),
      const Size(374, AppSpacing.loginPhoneFieldHeight),
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

    final phoneIcon = tester.widget<Icon>(find.byIcon(Icons.phone_iphone).last);
    final wechatIcon = tester.widget<Icon>(find.byIcon(SimpleIcons.wechat));
    final qqIcon = tester.widget<Icon>(find.byIcon(SimpleIcons.qq));
    // 手机图标与品牌图标统一尺寸、统一白色字形（实心彩圆 + 白字形），风格一致。
    expect(phoneIcon.size, AppSpacing.loginOtherMethodIconSize);
    expect(wechatIcon.size, AppSpacing.loginOtherMethodIconSize);
    expect(qqIcon.size, AppSpacing.loginOtherMethodIconSize);
    expect(phoneIcon.color, AppColors.white);

    // 手机方式应有可见的实心圆底（非近背景的隐形浅灰），与微信圆底一致。
    final phoneCircle = tester.widget<Container>(
      find
          .ancestor(
            of: find.byIcon(Icons.phone_iphone).last,
            matching: find.byType(Container),
          )
          .first,
    );
    final phoneDecoration = phoneCircle.decoration as BoxDecoration;
    expect(phoneDecoration.shape, BoxShape.circle);
    expect(phoneDecoration.color, AppColors.loginMethodPhoneCircle);
  });

  test('OTP debugCode 仅 alpha mock 与 beta 联调态展示', () {
    const debugResult = OtpSendResultData(
      maskedPhone: '180****3909',
      expiresInSeconds: 300,
      deliveryStatus: 'debug',
      debugCode: '123456',
    );
    const passThroughResult = OtpSendResultData(
      maskedPhone: '180****3909',
      expiresInSeconds: 300,
      deliveryStatus: 'pass_through',
      debugCode: '123456',
    );
    const realResult = OtpSendResultData(
      maskedPhone: '180****3909',
      expiresInSeconds: 300,
      deliveryStatus: 'delivered',
      debugCode: '123456',
    );

    expect(
      shouldRevealOtpDebugCode(
        runtimeEnv: 'alpha',
        mockDataSourceActive: true,
        result: debugResult,
      ),
      isTrue,
    );
    expect(
      shouldRevealOtpDebugCode(
        runtimeEnv: 'alpha',
        mockDataSourceActive: false,
        result: debugResult,
      ),
      isFalse,
    );
    expect(
      shouldRevealOtpDebugCode(
        runtimeEnv: 'beta',
        mockDataSourceActive: false,
        result: passThroughResult,
      ),
      isTrue,
    );
    for (final env in const <String>['gamma', 'prod']) {
      expect(
        shouldRevealOtpDebugCode(
          runtimeEnv: env,
          mockDataSourceActive: false,
          result: passThroughResult,
        ),
        isFalse,
      );
    }
    // gamma 受控放通：仅命中沙箱白名单（deliveryStatus == 'sandbox'）才回填验证码。
    const sandboxResult = OtpSendResultData(
      maskedPhone: '180****3909',
      expiresInSeconds: 300,
      deliveryStatus: 'sandbox',
      debugCode: '123456',
    );
    expect(
      shouldRevealOtpDebugCode(
        runtimeEnv: 'gamma',
        mockDataSourceActive: false,
        result: sandboxResult,
      ),
      isTrue,
    );
    // 生产即使收到 sandbox 状态也绝不回填（生产严格）。
    expect(
      shouldRevealOtpDebugCode(
        runtimeEnv: 'prod',
        mockDataSourceActive: false,
        result: sandboxResult,
      ),
      isFalse,
    );
    expect(
      shouldRevealOtpDebugCode(
        runtimeEnv: 'beta',
        mockDataSourceActive: false,
        result: realResult,
      ),
      isFalse,
    );
  });

  testWidgets('手机号输入框可输入，按钮只随手机号合法性启用', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
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

  test('登录错误码映射有明确下一步状态，文案云端 userMessage 优先、离线回退 baseline', () {
    const covered = <UserErrorCode>[
      UserErrorCode.otpMismatch,
      UserErrorCode.otpExpired,
      UserErrorCode.otpRateLimited,
      UserErrorCode.otpProviderFailed,
      UserErrorCode.loginLocked,
      UserErrorCode.accountSuspended,
      UserErrorCode.accountDeleted,
      UserErrorCode.carrierUnavailable,
      UserErrorCode.carrierTokenInvalid,
      UserErrorCode.carrierProviderTimeout,
      UserErrorCode.carrierPhoneMismatch,
      UserErrorCode.consentRequired,
    ];
    for (final code in covered) {
      final sending =
          code.name.startsWith('carrier') ||
          code == UserErrorCode.otpProviderFailed;

      // 每个错误码都有明确、非成功的就近 UI 状态。
      final presentation = loginErrorPresentationForCode(
        code,
        sending: sending,
      );
      expect(
        presentation.phase,
        isNot(LoginPhoneOtpPhase.success),
        reason: code.code,
      );

      // 离线/缺失 userMessage 时回退 codegen baseline（同源 errors.yaml），文案非空。
      final offline = resolveLoginErrorMessage(null, code, sending: sending);
      expect(offline.trim(), isNotEmpty, reason: code.code);

      // 云端下发 userMessage 时优先采用（可经 control-plane 热配置 override）。
      final online = resolveLoginErrorMessage(
        CloudException(
          type: CloudErrorType.server,
          message: 'debug',
          code: code.code,
          userMessage: '运营态_${code.name}',
        ),
        code,
        sending: sending,
      );
      expect(online, '运营态_${code.name}', reason: code.code);
    }
  });

  testWidgets('最近账号摘要存在时展示 returningAccount，同构主按钮不本地直进', (tester) async {
    final repo = _RecordingAuthRepository();
    await _pumpLogin(
      tester,
      authStore: _RememberedLoginStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );

    await tester.pump(const Duration(milliseconds: 50));

    expect(find.textContaining(_defaultNicknamePattern), findsOneWidget);
    expect(find.text('138****3909'), findsOneWidget);
    expect(find.text(UITextConstants.loginReturningHeroTitle), findsOneWidget);
    expect(
      find.text(UITextConstants.loginReturningHeroSubtitle),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.loginOneTap), findsOneWidget);

    await tester.ensureVisible(find.text(UITextConstants.loginOneTap));
    await tester.tap(find.text(UITextConstants.loginOneTap));
    await tester.pump();
    expect(repo.loginOneTapCalls, 0, reason: '未勾选协议不得请求服务端');
    expect(find.text(UITextConstants.loginAgreementRequired), findsWidgets);
    await tester.pump(const Duration(seconds: 3));

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginOneTap));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(repo.refreshTokenCalls, 1, reason: '最近账号态必须通过服务端 refresh 二次登录');
    expect(repo.loginOneTapCalls, 0);
  });

  testWidgets('软退出后凭证有效期内：returning 主按钮为一键登录、refresh 成功无红字', (tester) async {
    final repo = _RecordingAuthRepository();
    await _pumpLogin(
      tester,
      authStore: _SoftLoggedOutStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 软退出保留熟悉感与一键登录入口（凭证仍在有效期内）。
    expect(find.text('趣友A'), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTap), findsOneWidget);
    expect(find.text(UITextConstants.loginReturningSmsPrimary), findsNothing);

    await tester.ensureVisible(find.byIcon(CupertinoIcons.circle).first);
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();
    await tester.tap(find.text(UITextConstants.loginOneTap));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(repo.refreshTokenCalls, 1, reason: '有效期内一键登录应走 refresh 直接恢复');
    expect(find.text(UITextConstants.loginFailed), findsNothing);
  });

  testWidgets('快速登录凭证过期：returning 主按钮落短信、点击进验证码、无红字', (tester) async {
    final repo = _RecordingAuthRepository();
    await _pumpLogin(
      tester,
      authStore: _ExpiredQuickLoginStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 过期：保留头部，但主按钮变为"用短信验证码登录"，副标题中性提示已过期。
    expect(find.text('趣友B'), findsOneWidget);
    expect(find.text(UITextConstants.loginReturningSmsPrimary), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTap), findsNothing);
    expect(find.text(UITextConstants.loginSessionExpiredHint), findsWidgets);

    await tester.tap(find.text(UITextConstants.loginReturningSmsPrimary));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // 进入手机号验证码流程，绝不发起注定失败的一键登录，且无红字兜底。
    expect(repo.refreshTokenCalls, 0);
    expect(find.byType(PhoneNumberField), findsOneWidget);
    expect(find.text(UITextConstants.loginFailed), findsNothing);
  });

  testWidgets('彻底退出后无凭证：returning 主按钮落短信，不发起一键登录', (tester) async {
    final repo = _RecordingAuthRepository();
    await _pumpLogin(
      tester,
      authStore: _HardLoggedOutStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.loginReturningSmsPrimary), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTap), findsNothing);

    await tester.tap(find.text(UITextConstants.loginReturningSmsPrimary));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(repo.refreshTokenCalls, 0);
    expect(find.byType(PhoneNumberField), findsOneWidget);
  });

  testWidgets('过期 returning 记住手机号 + 已勾协议：点主按钮自动预填并自动发码进验证码', (tester) async {
    final repo = _RecordingAuthRepository();
    await _pumpLogin(
      tester,
      authStore: _ExpiredPhoneOtpStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 先勾选协议（图一返回头部的协议勾选），满足自动发码前置。
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pump();

    await tester.tap(find.text(UITextConstants.loginReturningSmsPrimary));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));

    // 自动预填完整手机号、自动发码（无需用户单独点击获取验证码）→ 直接进验证码态。
    expect(repo.refreshTokenCalls, 0);
    expect(repo.sendOtpCalls, 1);
    expect(find.byType(OtpCodeBoxes), findsOneWidget);
    final phoneField = tester.widget<CupertinoTextField>(
      find.byType(CupertinoTextField).first,
    );
    expect(phoneField.controller?.text, '18013813909');
    expect(find.text(UITextConstants.loginFailed), findsNothing);
  });

  testWidgets('过期 returning 记住手机号 + 未勾协议：点主按钮预填但不自动发码并提示勾选', (tester) async {
    final repo = _RecordingAuthRepository();
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
    final repo = _RecordingAuthRepository();
    await _pumpLogin(
      tester,
      authStore: _ExpiredPhoneOtpStore(),
      authRepository: repo,
      oneTapClient: const _UnavailableOneTapLoginClient(),
      capabilities: CapabilityProfile.mobile,
    );
    await tester.pump(const Duration(milliseconds: 50));

    // 主动选择「其他手机号」走空号手动输入流程（与记住号自动续登区分）。
    final phoneEntry = find.text(UITextConstants.loginMethodPhoneFull);
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
      authRepository: _RecordingAuthRepository(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(AutofillGroup), findsOneWidget);
  });

  testWidgets('无最近账号摘要但 carrier hint 为新号码时展示 carrierPhone 状态', (tester) async {
    final ops = MockOpsEventRepository();
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(
        hint: OneTapLoginHintDto.fromMap(<String, dynamic>{
          'state': 'new_phone',
          'maskedPhone': '180****3901',
          'registered': false,
          'expiresInSeconds': 60,
        }),
      ),
      oneTapClient: const _ProbeOneTapLoginClient(),
      opsEventRepository: ops,
    );

    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('180****3901'), findsOneWidget);
    expect(find.text(UITextConstants.loginCarrierHeroTitle), findsOneWidget);
    expect(find.text(UITextConstants.loginCarrierHeroSubtitle), findsOneWidget);
    expect(find.textContaining('将创建趣我圈账号'), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTapPrimary), findsOneWidget);
    expect(
      ops.recorded.map((event) => event.eventName),
      containsAll(<String>[
        'two_state_login.login_page_exposed',
        'two_state_login.login_state_resolved',
      ]),
    );
  });

  testWidgets('carrier hint 命中已注册账号时升级 returningAccount 状态', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(
        hint: OneTapLoginHintDto.fromMap(<String, dynamic>{
          'state': 'registered',
          'maskedPhone': '180****3902',
          'registered': true,
          'accountHint': <String, dynamic>{
            'displayName': '老用户',
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

    expect(find.text('老用户'), findsOneWidget);
    expect(find.text('180****3902'), findsOneWidget);
    expect(find.text(UITextConstants.loginOneTap), findsOneWidget);
  });

  testWidgets('one-tap 不可用时 1.2s 内降级到手机号输入，不长时间 loading', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(),
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

  testWidgets('两状态布局同构：主按钮、协议、其他登录方式纵向位置一致', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _RememberedLoginStore(),
      authRepository: _RecordingAuthRepository(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));
    final returningPrimaryDy = tester
        .getTopLeft(find.text(UITextConstants.loginOneTap))
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
      authRepository: _RecordingAuthRepository(
        hint: OneTapLoginHintDto.fromMap(<String, dynamic>{
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
        authRepository: _RecordingAuthRepository(
          hint: OneTapLoginHintDto.fromMap(<String, dynamic>{
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

  testWidgets('手机号初始态其他登录方式在 iPhone17 首屏完整可见', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(),
      oneTapClient: const _UnavailableOneTapLoginClient(),
    );
    await tester.pump(const Duration(milliseconds: 50));

    final alipayRect = tester.getRect(find.byIcon(SimpleIcons.alipay));
    final phoneRect = tester.getRect(find.byIcon(Icons.phone_iphone).last);
    final otherTitleRect = tester.getRect(
      find.text(UITextConstants.loginOtherMethods),
    );
    expect(otherTitleRect.top, greaterThan(700));
    expect(alipayRect.bottom, lessThan(900));
    // 手机图标与品牌图标统一尺寸，风格一致。
    expect(phoneRect.height, closeTo(alipayRect.height, 0.5));
    expect(find.text(UITextConstants.loginOtherMethods), findsOneWidget);
  });

  testWidgets('勾选协议后提交 one-tap，保存 remembered summary', (tester) async {
    final store = _MutableAuthStore();
    final repo = _RecordingAuthRepository(
      hint: OneTapLoginHintDto.fromMap(<String, dynamic>{
        'state': 'new_phone',
        'maskedPhone': '180****3901',
        'registered': false,
        'expiresInSeconds': 60,
      }),
    );
    final ops = MockOpsEventRepository();
    await _pumpLogin(
      tester,
      authStore: store,
      authRepository: repo,
      oneTapClient: const _ProbeOneTapLoginClient(),
      opsEventRepository: ops,
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
      ops.recorded.map((event) => event.eventName),
      containsAll(<String>[
        'two_state_login.login_primary_clicked',
        'two_state_login.login_success',
      ]),
    );
  });

  testWidgets('手机号 OTP 支持发码、粘贴六位验证码后自动登录', (tester) async {
    final store = _MutableAuthStore();
    final repo = _RecordingAuthRepository();
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

    await tester.enterText(find.byType(CupertinoTextField).last, '12 34 56');
    await tester.pump();
    expect(find.text('1'), findsOneWidget);
    expect(find.text('6'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 350));
    expect(repo.phoneLoginCalls, 1);
    expect(store.lastRememberedMethod, AuthRememberedLoginMethod.phoneOtp);
    expect(store.lastRememberedMaskedIdentifier, '180****3909');
  });

  testWidgets('手机号 OTP 输入首位后保持焦点，可连续输入而不需重新点按', (tester) async {
    final repo = _RecordingAuthRepository();
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

    expect(repo.phoneLoginCalls, 1);
  });

  testWidgets('验证码格在 337px 可用宽度下自适应不溢出', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await _pumpLogin(
      tester,
      authStore: _MutableAuthStore(),
      authRepository: _RecordingAuthRepository(),
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
        expected: UITextConstants.loginPhoneRequired,
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
        ),
        expected: '重新获取(60s)',
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.codeEditing,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123',
        ),
        expected: '3',
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.codeComplete,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
        ),
        expected: '6',
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.loggingIn,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
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
      // 阻断态（无 message）必须由 _messageForState 兜底出明确提示，杜绝空白。
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.loginLocked,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
        ),
        expected: UITextConstants.loginPhoneLoginLocked,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.accountSuspended,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
        ),
        expected: UITextConstants.loginAccountSuspended,
      ),
      (
        state: const LoginPhoneOtpState(
          phase: LoginPhoneOtpPhase.accountDeleted,
          phone: '18013813909',
          maskedPhone: '180****3909',
          code: '123456',
        ),
        expected: UITextConstants.loginAccountDeleted,
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
      UITextConstants.loginSendOtp,
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
    );
    expect(complete.primaryLabel, UITextConstants.loginPhoneSubmit);
    expect(complete.canLogin, isTrue);
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
      ),
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('loginOtpResendAction')),
    );
    await tester.pump();
    expect(resendCalls, 1, reason: '倒计时结束后可重发');
  });

  testWidgets('一键登录 refresh 失败不进死路：无红字降级短信、保留可操作出口', (tester) async {
    final repo = _FailingRefreshAuthRepository();
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
    await tester.tap(find.text(UITextConstants.loginOneTap));
    await tester.pump(const Duration(milliseconds: 50));

    // refresh 失败后不停在空面板、也不回到注定失败的一键登录：统一降级到短信验证码流程，
    // 保留可操作出口（手机号输入 + 其他方式），且不出现无意义红字兜底。
    expect(find.byType(UnavailablePanel), findsNothing);
    expect(find.byType(PhoneNumberField), findsOneWidget);
    expect(find.text(UITextConstants.loginOtherMethods), findsOneWidget);
    expect(find.text(UITextConstants.loginFailed), findsNothing);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('运营商一键登录失败降级到手机号输入并解释原因', (tester) async {
    final repo = _CarrierMismatchAuthRepository();
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
    expect(find.byType(UnavailablePanel), findsNothing);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('顶部为全局返回按钮（统一语义组件）且不含帮助问号图标', (tester) async {
    await _pumpLogin(
      tester,
      authStore: _GuestLoginStore(),
      authRepository: _RecordingAuthRepository(),
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
      authRepository: _RecordingAuthRepository(),
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
      tester.element(find.text(UITextConstants.loginOneTap)),
    ).position;
    expect(position.maxScrollExtent, 0.0, reason: '一屏可容纳则不可滚动');
  });
}

Future<void> _pumpLogin(
  WidgetTester tester, {
  required AuthSessionStore authStore,
  required AuthRepository authRepository,
  required OneTapLoginClient oneTapClient,
  MockOpsEventRepository? opsEventRepository,
  PlatformCapabilities? capabilities,
}) async {
  final ops = opsEventRepository ?? MockOpsEventRepository();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authSessionStoreProvider.overrideWithValue(authStore),
        authRepositoryProvider.overrideWithValue(authRepository),
        oneTapLoginClientProvider.overrideWithValue(oneTapClient),
        opsEventRepositoryProvider.overrideWithValue(ops),
        if (capabilities != null)
          platformCapabilitiesProvider.overrideWithValue(capabilities),
      ],
      child: CupertinoApp(home: LoginPage(key: UniqueKey())),
    ),
  );
  await tester.pump();
}

class _ProbeOneTapLoginClient implements OneTapLoginClient {
  const _ProbeOneTapLoginClient({this.token = 'carrier_token_new'});

  final String token;

  @override
  Future<bool> isAvailable() async => true;

  @override
  Future<OneTapLoginProbe> probe() async => OneTapLoginProbe(
    isAvailable: true,
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

class _UnavailableOneTapLoginClient implements OneTapLoginClient {
  const _UnavailableOneTapLoginClient();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<OneTapLoginProbe> probe() async =>
      const OneTapLoginProbe(isAvailable: false);

  @override
  Future<OneTapLoginResult> requestLoginToken() {
    throw UnimplementedError();
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

class _RecordingAuthRepository implements AuthRepository {
  _RecordingAuthRepository({OneTapLoginHintDto? hint})
    : hint =
          hint ?? OneTapLoginHintDto(state: 'unavailable', expiresInSeconds: 0);

  final OneTapLoginHintDto hint;
  int loginOneTapCalls = 0;
  int refreshTokenCalls = 0;
  int sendOtpCalls = 0;
  int phoneLoginCalls = 0;

  @override
  Future<OneTapLoginHintDto> resolveOneTapLoginHint({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
  }) async => hint;

  @override
  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) async {
    loginOneTapCalls += 1;
    return AuthLoginResultDto.fromMap(<String, dynamic>{
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
  Future<OtpSendResultData> sendOtp({
    required String phone,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? sourceOperation,
  }) async {
    sendOtpCalls += 1;
    return OtpSendResultData(
      maskedPhone: '180****3909',
      expiresInSeconds: 300,
      deliveryStatus: 'debug',
      requestId: 'request-1',
      challengeId: 'challenge-1',
      debugCode: '123456',
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
    if (credentialType == 'phone') {
      phoneLoginCalls += 1;
    }
    return AuthLoginResultDto.fromMap(<String, dynamic>{
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
  Future<AuthLoginResultDto> loginWechat({
    required String wechatCode,
    required String deviceId,
    required String platform,
  }) => throw UnimplementedError();

  @override
  Future<AuthLoginResultDto> loginAlipay({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
  }) => throw UnimplementedError();

  @override
  Future<AuthLoginResultDto> loginQq({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
  }) => throw UnimplementedError();

  @override
  Future<AuthLoginResultDto> loginApple({
    required String appleIdToken,
    required String deviceId,
    required String platform,
  }) => throw UnimplementedError();

  @override
  Future<AuthLoginResultDto> loginPasskey({
    required String passkeyAssertion,
    required String deviceId,
    required String platform,
    String? displayLabel,
  }) => throw UnimplementedError();

  @override
  Future<AuthLoginResultDto> loginAnonymous({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) => throw UnimplementedError();

  @override
  Future<AuthLoginResultDto> refreshToken(String refreshToken) async {
    refreshTokenCalls += 1;
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'refreshed_access',
      'refreshToken': 'refreshed_refresh',
      'ownerId': 'owner',
      'activeSub': <String, dynamic>{'subAccountId': 'sub'},
      'accountState': 'active',
      'identityOrigin': 'phone',
      'subAccountCount': 1,
      'accountHint': <String, dynamic>{
        'displayName': _defaultNicknameSample,
        'maskedPhone': '138****3909',
      },
    });
  }

  @override
  Future<void> logout({String? refreshToken, String? deviceId}) async {}

  @override
  Future<void> bindCredential({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  }) async {}

  @override
  Future<void> bindPhoneWithOtp({
    required String phone,
    required String otpCode,
    String? displayLabel,
  }) async {}

  @override
  Future<void> bindCarrierPhone({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? displayLabel,
  }) async {}

  @override
  Future<void> unbindCredential(String credentialType) async {}

  @override
  Future<List<OwnerCredentialRowDto>> listCredentials() async =>
      <OwnerCredentialRowDto>[];

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async =>
      <PersonaManagementItemViewData>[];

  @override
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String isolationLevel = 'open',
  }) => throw UnimplementedError();

  @override
  Future<void> activatePersona(String subAccountId) async {}

  @override
  Future<void> deletePersona(String subAccountId) async {}
}

/// 最近账号二次登录（服务端 refresh）失败：用于验证不进死路。
class _FailingRefreshAuthRepository extends _RecordingAuthRepository {
  @override
  Future<AuthLoginResultDto> refreshToken(String refreshToken) async {
    throw CloudException(
      type: CloudErrorType.server,
      message: 'refresh failed',
      userMessage: '会话已过期，请重新登录或换其它方式',
    );
  }
}

/// 运营商一键登录返回号码不一致（surface），用于验证降级到手机号输入。
class _CarrierMismatchAuthRepository extends _RecordingAuthRepository {
  _CarrierMismatchAuthRepository()
    : super(
        hint: OneTapLoginHintDto.fromMap(<String, dynamic>{
          'state': 'new_phone',
          'maskedPhone': '180****3901',
          'registered': false,
          'expiresInSeconds': 60,
        }),
      );

  @override
  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) async {
    throw CloudException(
      type: CloudErrorType.server,
      message: 'carrier phone mismatch',
      code: UserErrorCode.carrierPhoneMismatch.code,
      userMessage: '运营商号码校验未通过，请改用短信验证码登录',
    );
  }
}

class _GuestLoginStore extends _MutableAuthStore {
  _GuestLoginStore();
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

/// 彻底退出后：保留展示摘要但无 refreshToken（凭证已清除）。
class _HardLoggedOutStore extends _MutableAuthStore {
  _HardLoggedOutStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: '',
    ownerId: '',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    rememberedLoginMethod: AuthRememberedLoginMethod.oneTap,
    rememberedLoginMaskedIdentifier: '138****0003',
    rememberedDisplayName: '趣友C',
    rememberedAvatarUrl: '',
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
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
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
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

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
