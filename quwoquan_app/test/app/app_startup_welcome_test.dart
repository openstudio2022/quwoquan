import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

void main() {
  testWidgets('启动首帧直接展示欢迎页，不等待认证恢复完成', (tester) async {
    final blockingStore = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appDataSourceModeProvider.overrideWith(_StartupMockDataSource.new),
          authSessionStoreProvider.overrideWithValue(blockingStore),
        ],
        child: const QuWoQuanAppRoot(),
      ),
    );

    expect(blockingStore.readStarted, isTrue);
    expect(blockingStore.readCompleted, isFalse);
    expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);
    expect(find.text(UITextConstants.welcomeMainSlogan), findsOneWidget);
    expect(find.byType(WelcomeFlowerMark), findsOneWidget);

    await tester.pump();

    expect(blockingStore.readStarted, isTrue);
    expect(blockingStore.readCompleted, isFalse);
    expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);
    expect(find.byType(WelcomeFlowerMark), findsOneWidget);

    await tester.pump(const Duration(seconds: 16));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('Web 启动先出内容壳，再叠欢迎层且不显示登录 prompt', (
    tester,
  ) async {
    final blockingStore = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appDataSourceModeProvider.overrideWith(_StartupMockDataSource.new),
          authSessionStoreProvider.overrideWithValue(blockingStore),
          platformTargetProvider.overrideWithValue(AppPlatform.web),
          platformCapabilitiesProvider.overrideWithValue(CapabilityProfile.web),
        ],
        child: const QuWoQuanAppRoot(),
      ),
    );

    expect(blockingStore.readStarted, isTrue);
    expect(find.byType(MainAppShell), findsOneWidget);
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.text(UITextConstants.welcomeLoginPromptTitle), findsNothing);
    expect(find.byType(LoginPage), findsNothing);

    await tester.pump();
    await tester.pump(const Duration(seconds: 3));

    expect(find.byType(MainAppShell), findsOneWidget);
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.byType(LoginPage), findsNothing);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}

final class _StartupMockDataSource extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;
}

final class _BlockingAuthSessionStore implements AuthSessionStore {
  final Completer<StoredAuthSession> _readCompleter =
      Completer<StoredAuthSession>();

  bool readStarted = false;
  bool readCompleted = false;

  @override
  Future<StoredAuthSession> read() async {
    readStarted = true;
    final stored = await _readCompleter.future;
    readCompleted = true;
    return stored;
  }

  @override
  Future<void> saveLoginResult(AuthLoginResultDto result) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}
}
