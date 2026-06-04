import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';

void main() {
  testWidgets('one-tap 可用时展示一键登录按钮，不停留在 spinner', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          oneTapLoginClientProvider.overrideWithValue(
            const _FakeOneTapLoginClient(available: true),
          ),
        ],
        child: const CupertinoApp(home: LoginPage()),
      ),
    );
    await tester.pump();

    expect(find.text(UITextConstants.loginOneTapPrimary), findsOneWidget);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(find.text(UITextConstants.loginLater), findsOneWidget);

    await tester.tap(find.text(UITextConstants.loginOneTapPrimary));
    await tester.pump();

    // 未勾选协议：统一约束提示，不跳页。
    expect(find.text(UITextConstants.authConsentRequired), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('one-tap 不可用时回退到手机号验证码', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          oneTapLoginClientProvider.overrideWithValue(
            const _FakeOneTapLoginClient(available: false),
          ),
        ],
        child: const CupertinoApp(home: LoginPage()),
      ),
    );
    await tester.pump();

    expect(
      find.text(UITextConstants.loginPhoneNumberPlaceholder),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.loginPhoneSubmit), findsOneWidget);
    expect(find.text(UITextConstants.loginLater), findsOneWidget);

    await tester.tap(find.text(UITextConstants.loginPhoneSubmit));
    await tester.pump();

    expect(find.text(UITextConstants.authConsentRequired), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('one-tap 探测超时/卡住时切到手机号兜底，主区域不再转圈', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          oneTapLoginClientProvider.overrideWithValue(
            const _HangingOneTapLoginClient(),
          ),
        ],
        child: const CupertinoApp(home: LoginPage()),
      ),
    );
    // 探测期间：spinner 占位。
    await tester.pump();
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    expect(find.text(UITextConstants.loginPhoneSubmit), findsNothing);

    // 超过 1.2s 探测超时：自动展示手机号表单，不再转圈。
    await tester.pump(const Duration(milliseconds: 1300));
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(find.text(UITextConstants.loginPhoneSubmit), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('协议区位于「稍后登录」之后、其他登录方式之前', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          oneTapLoginClientProvider.overrideWithValue(
            const _FakeOneTapLoginClient(available: true),
          ),
        ],
        child: const CupertinoApp(home: LoginPage()),
      ),
    );
    await tester.pump();

    final laterDy = tester.getTopLeft(find.text(UITextConstants.loginLater)).dy;
    final agreementDy = tester
        .getTopLeft(find.textContaining(UITextConstants.userAgreement))
        .dy;
    final otherMethodsDy = tester
        .getTopLeft(find.text(UITextConstants.loginOtherMethods))
        .dy;

    expect(laterDy < agreementDy, isTrue, reason: '协议区应在「稍后登录」之后');
    expect(agreementDy < otherMethodsDy, isTrue, reason: '协议区应在其他登录方式之前');
  });

  testWidgets('非生产 debugCode 明确提示但不自动填入验证码输入框', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          oneTapLoginClientProvider.overrideWithValue(
            const _FakeOneTapLoginClient(available: false),
          ),
          authRepositoryProvider.overrideWithValue(MockAuthRepository()),
        ],
        child: const CupertinoApp(home: LoginPage()),
      ),
    );
    await tester.pump();

    await tester.enterText(
      find.widgetWithText(
        CupertinoTextField,
        UITextConstants.loginPhoneNumberPlaceholder,
      ),
      '+8618013813909',
    );
    await tester.tap(find.text(UITextConstants.loginSendOtp));
    await tester.pump(const Duration(milliseconds: 250));

    expect(
      find.textContaining(UITextConstants.loginOtpDebugCodePrefix),
      findsOneWidget,
    );
    final otpField = tester.widget<CupertinoTextField>(
      find.widgetWithText(
        CupertinoTextField,
        UITextConstants.loginOtpPlaceholder,
      ),
    );
    expect(otpField.controller?.text ?? '', isEmpty);
    await tester.pump(const Duration(seconds: 3));
  });
}

class _FakeOneTapLoginClient implements OneTapLoginClient {
  const _FakeOneTapLoginClient({required this.available});

  final bool available;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<OneTapLoginResult> requestLoginToken() async {
    return const OneTapLoginResult(
      vendor: 'test',
      carrierToken: 'carrier_token_new',
      maskedPhone: '138****0000',
    );
  }
}

/// isAvailable 永不返回，模拟一键登录探测卡住，触发登录页超时兜底。
class _HangingOneTapLoginClient implements OneTapLoginClient {
  const _HangingOneTapLoginClient();

  @override
  Future<bool> isAvailable() => Completer<bool>().future;

  @override
  Future<OneTapLoginResult> requestLoginToken() =>
      Completer<OneTapLoginResult>().future;
}
