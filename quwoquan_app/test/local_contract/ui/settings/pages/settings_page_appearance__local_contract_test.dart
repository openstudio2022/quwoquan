import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:quwoquan_app/app/models/appearance_settings_models.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/application/user/device_registration/device_push_endpoint_writer.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';
import 'package:quwoquan_app/core/observability/runtime_logger.dart';
import 'package:quwoquan_app/core/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_about_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_calls_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_dark_mode_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_notifications_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_permissions_page.dart';
import '../../../../support/recording_app_telemetry_recorder.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: UITextConstants.loginBrandName,
      packageName: 'com.quwoquan.app',
      version: UITextConstants.settingsAboutDefaultVersion,
      buildNumber: '1',
      buildSignature: '',
    );
  });

  group('SettingsPage 我的主页设置页', () {
    testWidgets('仅展示新设置 IA 指定入口', (tester) async {
      _useTallViewport(tester);
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
      expect(find.text(UITextConstants.profilePersonasLabel), findsOneWidget);
      expect(
        find.text(UITextConstants.settingsPermissionManagement),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.settingsBlockedUsers), findsOneWidget);
      expect(find.text(UITextConstants.settingsDarkMode), findsOneWidget);
      expect(find.text(UITextConstants.settingsAboutQuwoquan), findsOneWidget);
      expect(find.text(UITextConstants.switchAccount), findsOneWidget);
      expect(find.text(UITextConstants.logout), findsOneWidget);

      expect(find.text(AppConceptConstants.assistantLabel), findsNothing);
      expect(find.text(SettingsRemovedText.notification), findsNothing);
      expect(find.text(SettingsRemovedText.cache), findsNothing);
      expect(find.text(SettingsRemovedText.developer), findsNothing);
      expect(find.text(SettingsRemovedText.preferenceSection), findsNothing);
      expect(find.text(SettingsRemovedText.appearanceAndFont), findsNothing);
      expect(
        find.text(SettingsRemovedText.assistantContentAccess),
        findsNothing,
      );
      expect(find.text(SettingsRemovedText.accountSecurity), findsNothing);
      expect(find.text(SettingsRemovedText.loginCredentials), findsNothing);
      expect(find.text(SettingsRemovedText.loginDevices), findsNothing);
      expect(find.text(SettingsRemovedText.accountDeletion), findsNothing);
      expect(find.text(SettingsRemovedText.dataRights), findsNothing);
      expect(find.text(SettingsRemovedText.userAndPersona), findsNothing);
    });

    testWidgets('编辑资料和分身管理进入既有路由', (tester) async {
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.profileEditLabel));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.profileEdit), findsOneWidget);

      final router = GoRouter.of(
        tester.element(find.text(_RouteProbe.profileEdit)),
      );
      router.go(AppRoutePaths.settings);
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.profilePersonasLabel));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.profilePersonas), findsOneWidget);
    });

    testWidgets('权限管理页只承载真实联系人系统权限，不展示对象权限占位', (tester) async {
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.settingsPermissionManagement));
      await tester.pumpAndSettle();

      expect(find.byType(SettingsPermissionsPage), findsOneWidget);
      expect(
        find.text(UITextConstants.settingsContactsPermission),
        findsOneWidget,
      );
      final actionCount =
          find.text(UITextConstants.openSettings).evaluate().length +
          find
              .text(UITextConstants.settingsPermissionUnavailable)
              .evaluate()
              .length;
      expect(actionCount, 1);
      expect(
        find
            .textContaining(UITextConstants.settingsPermissionUnavailable)
            .evaluate()
            .length,
        lessThanOrEqualTo(1),
      );
    });

    testWidgets('深色模式进入详情页并通过系统开关和手动单选更新运行时', (tester) async {
      _useTallViewport(tester);
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.settingsDarkMode));
      await tester.pumpAndSettle();

      expect(find.byType(SettingsDarkModePage), findsOneWidget);
      expect(find.byType(CupertinoActionSheet), findsNothing);
      expect(find.text(UITextConstants.settingsDarkModeSystem), findsWidgets);
      expect(
        find.text(UITextConstants.settingsDarkModeLightOption),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.settingsDarkModeDarkOption),
        findsWidgets,
      );

      await tester.tap(
        find.byKey(
          const ValueKey<AppearanceThemeMode>(AppearanceThemeMode.dark),
        ),
      );
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(SettingsDarkModePage)),
      );
      expect(
        container.read(themeProvider).themeModeSetting,
        AppThemeModeSetting.dark,
      );
      expect(
        container.read(appearanceSettingsControllerProvider).snapshot.themeMode,
        AppearanceThemeMode.dark,
      );

      await tester.tap(find.byType(CupertinoSwitch));
      await tester.pumpAndSettle();

      expect(
        container.read(appearanceSettingsControllerProvider).snapshot.themeMode,
        AppearanceThemeMode.system,
      );
    });

    testWidgets('外观设置加载失败时显示可恢复状态，重试后恢复真实摘要', (tester) async {
      _useTallViewport(tester);
      final appearanceRepository = _RecoveringSettingsQueryReader();
      await tester.pumpWidget(
        _buildSettingsApp(settingsQueryReader: appearanceRepository),
      );
      await tester.pumpAndSettle();

      expect(appearanceRepository.loadCount, 1);
      expect(find.text(UITextConstants.loadFailed), findsOneWidget);
      expect(find.text(UITextConstants.tryAgain), findsOneWidget);

      await tester.tap(find.text(UITextConstants.tryAgain));
      await tester.pumpAndSettle();

      expect(appearanceRepository.loadCount, 2);
      expect(find.text(UITextConstants.loadFailed), findsNothing);
      expect(find.text(UITextConstants.tryAgain), findsNothing);
      expect(find.text(UITextConstants.settingsDarkModeSystem), findsOneWidget);
    });

    testWidgets('深色模式主行值贴右，账号操作为无图标居中按钮', (tester) async {
      _useTallViewport(tester);
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      final modeText = find.text(UITextConstants.settingsDarkModeSystem).first;
      final chevron = find.descendant(
        of: find.ancestor(
          of: find.text(UITextConstants.settingsDarkMode),
          matching: find.byType(SettingsInsetNavigationRow),
        ),
        matching: find.byIcon(CupertinoIcons.chevron_forward),
      );
      expect(modeText, findsOneWidget);
      expect(chevron, findsOneWidget);
      expect(
        tester.getTopRight(modeText).dx,
        lessThan(tester.getTopLeft(chevron).dx),
      );
      expect(
        tester.getTopLeft(chevron).dx - tester.getTopRight(modeText).dx,
        lessThanOrEqualTo(AppSpacing.sm),
      );
      expect(find.byType(SettingsInsetNavigationRow), findsAtLeastNWidgets(6));
      expect(
        find.byType(SettingsInsetFormSectionDivider),
        findsAtLeastNWidgets(3),
      );

      final switchAccountButton = find.ancestor(
        of: find.text(UITextConstants.switchAccount),
        matching: find.byType(CupertinoButton),
      );
      final logoutButton = find.ancestor(
        of: find.text(UITextConstants.logout),
        matching: find.byType(CupertinoButton),
      );
      expect(
        find.descendant(of: switchAccountButton, matching: find.byType(Icon)),
        findsNothing,
      );
      expect(
        find.descendant(of: logoutButton, matching: find.byType(Icon)),
        findsNothing,
      );

      final viewportCenterX =
          tester.getSize(find.byType(MaterialApp)).width / 2;
      expect(
        tester.getCenter(find.text(UITextConstants.switchAccount)).dx,
        moreOrLessEquals(viewportCenterX, epsilon: AppSpacing.md),
      );
      expect(
        tester.getCenter(find.text(UITextConstants.logout)).dx,
        moreOrLessEquals(viewportCenterX, epsilon: AppSpacing.md),
      );
    });

    testWidgets('关于趣我圈页显示版本号', (tester) async {
      _useTallViewport(tester);
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.settingsAboutQuwoquan));
      await tester.pumpAndSettle();

      expect(find.byType(SettingsAboutPage), findsOneWidget);
      expect(find.text(UITextConstants.loginBrandName), findsWidgets);
      expect(find.text(UITextConstants.settingsVersion), findsOneWidget);
      expect(
        find.text(
          UITextConstants.settingsVersionValue(
            UITextConstants.settingsAboutDefaultVersion,
          ),
        ),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.userAgreement), findsOneWidget);
      expect(find.text(UITextConstants.privacyPolicy), findsOneWidget);
      expect(find.text(UITextConstants.permissionsStatement), findsOneWidget);
      expect(find.text(UITextConstants.thirdPartySdkList), findsOneWidget);

      await tester.tap(find.text(UITextConstants.userAgreement));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.userAgreement), findsOneWidget);

      final router = GoRouter.of(
        tester.element(find.text(_RouteProbe.userAgreement)),
      );
      router.go(AppRoutePaths.settingsAbout);
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.privacyPolicy));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.privacyPolicy), findsOneWidget);

      router.go(AppRoutePaths.settingsAbout);
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.permissionsStatement));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.permissions), findsOneWidget);

      router.go(AppRoutePaths.settingsAbout);
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.thirdPartySdkList));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.thirdPartySdkList), findsOneWidget);
    });

    testWidgets('退出登录默认走软退出：不远端吊销、不清本机凭证', (tester) async {
      final store = _SpyAuthSessionStore();
      final repo = _SpyAccountSessionLifecycleWriter();
      final behavior = _SpyBehaviorRepository();
      final ops = _SpyAppTelemetryRecorder();
      await tester.pumpWidget(
        _buildSettingsApp(
          store: store,
          authRepository: repo,
          behaviorRepository: behavior,
          telemetryRecorder: ops,
        ),
      );
      await tester.pumpAndSettle();

      await _openLogoutDialog(tester);

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.text(UITextConstants.logoutDialogTitle), findsWidgets);
      expect(find.byType(CupertinoActionSheet), findsNothing);
      expect(
        find.widgetWithText(
          CupertinoDialogAction,
          UITextConstants.logoutDialogSoftAction,
        ),
        findsOneWidget,
      );
      expect(
        find.widgetWithText(
          CupertinoDialogAction,
          UITextConstants.logoutDialogHardAction,
        ),
        findsOneWidget,
      );

      await tester.tap(
        find.widgetWithText(
          CupertinoDialogAction,
          UITextConstants.logoutDialogSoftAction,
        ),
      );
      await tester.pumpAndSettle();

      expect(store.softLogoutCount, 1);
      expect(store.clearSessionCount, 0);
      expect(repo.logoutCount, 0);
      expect(behavior.clearPendingCount, 1);
      expect(ops.clearPendingCount, 1);
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('退出并清除本机登录信息：远端吊销 + 清本机凭证', (tester) async {
      final store = _SpyAuthSessionStore();
      final repo = _SpyAccountSessionLifecycleWriter();
      final behavior = _SpyBehaviorRepository();
      final ops = _SpyAppTelemetryRecorder();
      await tester.pumpWidget(
        _buildSettingsApp(
          store: store,
          authRepository: repo,
          behaviorRepository: behavior,
          telemetryRecorder: ops,
        ),
      );
      await tester.pumpAndSettle();

      await _openLogoutDialog(tester);

      await tester.tap(
        find.widgetWithText(
          CupertinoDialogAction,
          UITextConstants.logoutDialogHardAction,
        ),
      );
      await tester.pumpAndSettle();

      expect(repo.logoutCount, 1);
      expect(store.clearSessionCount, 1);
      expect(store.softLogoutCount, 0);
      expect(behavior.clearPendingCount, 1);
      expect(ops.clearPendingCount, 1);
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('登录态展示通知与通话设置区并通过 typed 命令提交', (tester) async {
      _useTallViewport(tester);
      final commands = _RecordingUserSettingsCommandWriter();
      await tester.pumpWidget(
        _buildSettingsApp(settingsCommandWriter: commands),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(UITextConstants.settingsNotificationSection),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.settingsCallSection), findsOneWidget);

      await tester.tap(find.text(UITextConstants.settingsNotificationSection));
      await tester.pumpAndSettle();
      expect(find.text(UITextConstants.settingsEnablePush), findsOneWidget);

      await tester.tap(find.text(UITextConstants.settingsEnablePush));
      await tester.pumpAndSettle();
      expect(commands.notificationCommands, hasLength(1));
      expect(commands.notificationCommands.single.enablePush, isFalse);

      await tester.tap(find.byIcon(CupertinoIcons.back));
      await tester.pumpAndSettle();
      await tester.tap(find.text(UITextConstants.settingsCallSection));
      await tester.pumpAndSettle();
      expect(
        find.text(UITextConstants.settingsCallRingtoneDefault),
        findsOneWidget,
      );
      await tester.tap(find.text(UITextConstants.settingsEnableCallVibration));
      await tester.pumpAndSettle();
      expect(commands.callCommands, hasLength(1));
      expect(commands.callCommands.single.enableCallVibration, isFalse);
    });

    testWidgets('设置命令失败时回滚开关状态', (tester) async {
      _useTallViewport(tester);
      final commands = _RecordingUserSettingsCommandWriter()
        ..failNotification = true;
      await tester.pumpWidget(
        _buildSettingsApp(settingsCommandWriter: commands),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.settingsNotificationSection));
      await tester.pumpAndSettle();
      final pushSwitchBefore = tester.widget<CupertinoSwitch>(
        find
            .descendant(
              of: find.ancestor(
                of: find.text(UITextConstants.settingsEnablePush),
                matching: find.byType(SettingsInsetSwitchRow),
              ),
              matching: find.byType(CupertinoSwitch),
            )
            .first,
      );
      expect(pushSwitchBefore.value, isTrue);

      await tester.tap(find.text(UITextConstants.settingsEnablePush));
      await tester.pumpAndSettle();

      final pushSwitchAfter = tester.widget<CupertinoSwitch>(
        find
            .descendant(
              of: find.ancestor(
                of: find.text(UITextConstants.settingsEnablePush),
                matching: find.byType(SettingsInsetSwitchRow),
              ),
              matching: find.byType(CupertinoSwitch),
            )
            .first,
      );
      expect(pushSwitchAfter.value, isTrue);
      expect(
        find.text(UITextConstants.settingsUpdateFailedToast),
        findsOneWidget,
      );
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('远端吊销失败仍清除本机凭证，并写入结构化异常记录', (tester) async {
      final store = _SpyAuthSessionStore();
      final repo = _FailingLogoutAccountSessionLifecycleWriter();
      final behavior = _SpyBehaviorRepository();
      final ops = _SpyAppTelemetryRecorder();
      final buffer = InMemoryRuntimeLogBuffer();
      final logger = RuntimeLogger(
        resource: const RuntimeLogResource(
          sourceType: 'app',
          environment: 'alpha',
          service: 'quwoquan_app',
          appVersion: 'test',
        ),
        buffer: buffer,
      );
      AppExceptionTelemetryService.instance.bind(logger: logger);
      addTearDown(() => AppExceptionTelemetryService.instance.unbind(logger));

      await tester.pumpWidget(
        _buildSettingsApp(
          store: store,
          authRepository: repo,
          behaviorRepository: behavior,
          telemetryRecorder: ops,
        ),
      );
      await tester.pumpAndSettle();
      await _openLogoutDialog(tester);
      await tester.tap(
        find.widgetWithText(
          CupertinoDialogAction,
          UITextConstants.logoutDialogHardAction,
        ),
      );
      await tester.pumpAndSettle();

      expect(repo.logoutCount, 1);
      expect(store.clearSessionCount, 1);
      expect(store.softLogoutCount, 0);
      expect(behavior.clearPendingCount, 1);
      expect(ops.clearPendingCount, 1);
      expect(tester.takeException(), isNull);

      final record = (await buffer.pending()).singleWhere(
        (entry) =>
            entry.attributes.toWire()['source'] ==
            'settings.logout.remote_revoke',
      );
      expect(record.kind, RuntimeLogKind.exception);
      expect(record.correlation.operationId, 'user.account_session.Logout');
      expect(record.correlation.surfaceId, 'settingsHome');
      expect(record.attributes.toWire()['exceptionType'], 'StateError');
      await tester.pump(const Duration(seconds: 4));
    });
  });
}

Future<void> _openLogoutDialog(WidgetTester tester) async {
  _useTallViewport(tester);
  await tester.pumpAndSettle();

  await tester.tap(find.text(UITextConstants.logout));
  await tester.pumpAndSettle();
}

void _useTallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 4000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Widget _buildSettingsApp({
  AuthSessionStore? store,
  contracts.AccountSessionLifecycleCommandWriter? authRepository,
  BehaviorRepository? behaviorRepository,
  AppTelemetryRecorder? telemetryRecorder,
  contracts.UserSettingsQueryReader? settingsQueryReader,
  contracts.UserSettingsCommandWriter? settingsCommandWriter,
}) {
  return ProviderScope(
    overrides: [
      userSettingsQueryReaderProvider.overrideWithValue(
        settingsQueryReader ?? _SettingsQueryReader(),
      ),
      authSessionStoreProvider.overrideWithValue(
        store ?? _SpyAuthSessionStore(),
      ),
      authSessionControllerProvider.overrideWith(
        _SettingsTestAuthSessionController.new,
      ),
      devicePushEndpointCoordinatorProvider.overrideWithValue(
        DevicePushEndpointCoordinator(
          gateway: const _EmptyPushEndpointGateway(),
          writer: const _NoopDevicePushEndpointWriter(),
        ),
      ),
      if (authRepository != null)
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          authRepository,
        ),
      if (behaviorRepository != null)
        behaviorRepositoryProvider.overrideWithValue(behaviorRepository),
      if (telemetryRecorder != null)
        appTelemetryReporterProvider.overrideWithValue(telemetryRecorder),
      if (settingsCommandWriter != null)
        userSettingsCommandWriterProvider.overrideWithValue(
          settingsCommandWriter,
        ),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: AppRoutePaths.settings,
        routes: [
          GoRoute(
            path: AppRoutePaths.settings,
            builder: (context, state) => const SettingsPage(),
            routes: [
              GoRoute(
                path: AppRoutePaths.settingsPermissionsSegment,
                builder: (context, state) => const SettingsPermissionsPage(),
              ),
              GoRoute(
                path: AppRoutePaths.settingsDarkModeSegment,
                builder: (context, state) => const SettingsDarkModePage(),
              ),
              GoRoute(
                path: AppRoutePaths.settingsNotificationsSegment,
                builder: (context, state) => const SettingsNotificationsPage(),
              ),
              GoRoute(
                path: AppRoutePaths.settingsCallsSegment,
                builder: (context, state) => const SettingsCallsPage(),
              ),
              GoRoute(
                path: AppRoutePaths.settingsAboutSegment,
                builder: (context, state) => const SettingsAboutPage(),
              ),
            ],
          ),
          GoRoute(
            path: AppRoutePaths.profileEdit,
            builder: (context, state) => const Text(_RouteProbe.profileEdit),
          ),
          GoRoute(
            path: AppRoutePaths.profilePersonas,
            builder: (context, state) =>
                const Text(_RouteProbe.profilePersonas),
          ),
          GoRoute(
            path: AppRoutePaths.loginPathTemplate,
            builder: (context, state) => const Text(_RouteProbe.login),
          ),
          GoRoute(
            path: AppRoutePaths.legalUserAgreement,
            builder: (context, state) => const Text(_RouteProbe.userAgreement),
          ),
          GoRoute(
            path: AppRoutePaths.legalPrivacyPolicy,
            builder: (context, state) => const Text(_RouteProbe.privacyPolicy),
          ),
          GoRoute(
            path: AppRoutePaths.legalPermissions,
            builder: (context, state) => const Text(_RouteProbe.permissions),
          ),
          GoRoute(
            path: AppRoutePaths.legalThirdPartySdkList,
            builder: (context, state) =>
                const Text(_RouteProbe.thirdPartySdkList),
          ),
        ],
      ),
    ),
  );
}

abstract final class _RouteProbe {
  static const String profileEdit = 'profile-edit-route';
  static const String profilePersonas = 'profile-personas-route';
  static const String login = 'login-route';
  static const String userAgreement = 'user-agreement-route';
  static const String privacyPolicy = 'privacy-policy-route';
  static const String permissions = 'permissions-route';
  static const String thirdPartySdkList = 'third-party-sdk-list-route';
}

abstract final class SettingsRemovedText {
  static const String notification = '通知';
  static const String cache = '存储与缓存';
  static const String developer = '开发者';
  static const String preferenceSection = '偏好';
  static const String appearanceAndFont = '外观与字号';
  static const String assistantContentAccess = '私助读取创作内容';
  static const String accountSecurity = '账号安全与隐私';
  static const String loginCredentials = '登录方式与凭证';
  static const String loginDevices = '登录设备与会话';
  static const String accountDeletion = '账号注销与恢复';
  static const String dataRights = '数据导出与撤回同意';
  static const String userAndPersona = '用户与分身';
}

class _SettingsQueryReader implements contracts.UserSettingsQueryReader {
  @override
  Future<contracts.NotificationSettingsView> getNotificationSettings() async =>
      contracts.NotificationSettingsView(
        userId: 'owner-id',
        enablePush: true,
        enableMarketing: false,
        version: 1,
        updatedAt: DateTime.utc(2026, 7, 19),
      );

  @override
  Future<contracts.PrivacySettingsView> getPrivacySettings() async =>
      contracts.PrivacySettingsView(
        userId: 'owner-id',
        allowStrangerMsg: true,
        profileVisibility: contracts.ProfileVisibility.public,
        assistantEnabled: true,
        version: 1,
        updatedAt: DateTime.utc(2026, 7, 19),
      );

  @override
  Future<contracts.CallSettingsView> getCallSettings() async =>
      contracts.CallSettingsView(
        userId: 'owner-id',
        defaultIncomingCallRingtoneId: contracts.OfficialRingtoneId(
          'official.default',
        ),
        allowCallerRingtoneOverride: true,
        enableCallVibration: true,
        enableGroupCallRing: true,
        version: 1,
        updatedAt: DateTime.utc(2026, 7, 19),
      );

  @override
  Future<contracts.AppearanceSettingsView> getAppearanceSettings() async =>
      contracts.AppearanceSettingsView(
        themeMode: contracts.ThemeModeSetting.system,
        fontSizePreset: contracts.FontSizePreset.md,
        source: contracts.AppearanceSource.ownerDefault,
        ownerDefaultThemeMode: contracts.ThemeModeSetting.system,
        ownerDefaultFontSizePreset: contracts.FontSizePreset.md,
        hasSubAccountOverride: false,
        version: 1,
        updatedAt: DateTime.utc(2026, 7, 19),
      );
}

final class _RecoveringSettingsQueryReader extends _SettingsQueryReader {
  int loadCount = 0;

  @override
  Future<contracts.AppearanceSettingsView> getAppearanceSettings() {
    loadCount += 1;
    if (loadCount == 1) {
      throw StateError('appearance settings unavailable');
    }
    return super.getAppearanceSettings();
  }
}

class _SpyAuthSessionStore implements AuthSessionStore {
  int softLogoutCount = 0;
  int clearSessionCount = 0;

  @override
  Future<StoredAuthSession> read() async => StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'owner-id',
    activeSubAccountId: 'sub-id',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    lastForegroundAuthCheckAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

  @override
  Future<void> saveLoginGrant(
    contracts.AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshGrant(contracts.TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    contracts.AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {
    clearSessionCount += 1;
  }

  @override
  Future<void> softLogout() async {
    softLogoutCount += 1;
  }

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

class _SpyAccountSessionLifecycleWriter
    implements contracts.AccountSessionLifecycleCommandWriter {
  int logoutCount = 0;

  @override
  Future<contracts.LogoutAck> logout(contracts.LogoutCommand command) async {
    logoutCount += 1;
    return const contracts.LogoutAck(revoked: true);
  }

  @override
  Future<contracts.TokenRefreshGrant> refreshToken(
    contracts.RefreshTokenCommand command,
  ) async {
    return const contracts.TokenRefreshGrant(
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      sessionRememberTtlSeconds: 2592000,
    );
  }
}

final class _FailingLogoutAccountSessionLifecycleWriter
    extends _SpyAccountSessionLifecycleWriter {
  @override
  Future<contracts.LogoutAck> logout(contracts.LogoutCommand command) async {
    logoutCount += 1;
    throw StateError('settings remote revoke unavailable');
  }
}

final class _SpyBehaviorRepository extends MockBehaviorRepository {
  int clearPendingCount = 0;

  @override
  Future<void> clearPendingForLogout() async {
    clearPendingCount += 1;
    await super.clearPendingForLogout();
  }
}

final class _SpyAppTelemetryRecorder extends RecordingAppTelemetryRecorder {
  @override
  Future<void> clearPendingForLogout() async {
    clearPendingCount += 1;
  }
}

final class _SettingsTestAuthSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'owner-id',
    activeSubAccountId: 'sub-id',
    accountState: 'active',
    identityOrigin: 'settings-test',
    installId: 'install-id',
  );
}

final class _EmptyPushEndpointGateway implements PushEndpointGateway {
  const _EmptyPushEndpointGateway();

  @override
  Future<void> acknowledgeMutation(String mutationId) async {}

  @override
  Future<void> queueActiveEndpointRemovals() async {}

  @override
  Future<List<PushEndpointMutation>> readPendingMutations() async =>
      const <PushEndpointMutation>[];

  @override
  Future<void> recordUpsert(DevicePushEndpoint endpoint) async {}
}

final class _NoopDevicePushEndpointWriter implements DevicePushEndpointWriter {
  const _NoopDevicePushEndpointWriter();

  @override
  Future<void> remove(DevicePushEndpoint endpoint) async {}

  @override
  Future<void> upsert(DevicePushEndpoint endpoint) async {}
}

/// 记录 UserSettings typed 命令的 stub；receipt 与 Remote 同形。
final class _RecordingUserSettingsCommandWriter
    implements contracts.UserSettingsCommandWriter {
  final List<contracts.UpdateNotificationSettingsCommand> notificationCommands =
      <contracts.UpdateNotificationSettingsCommand>[];
  final List<contracts.UpdateCallSettingsCommand> callCommands =
      <contracts.UpdateCallSettingsCommand>[];
  bool failNotification = false;
  int version = 1;

  @override
  Future<contracts.UserSettingsCommandResult> updateNotificationSettings(
    contracts.UpdateNotificationSettingsCommand command,
  ) async {
    if (failNotification) {
      throw StateError('settings backend unavailable');
    }
    notificationCommands.add(command);
    return contracts.UserSettingsCommandResult(
      userId: 'owner-id',
      version: ++version,
      idempotentReplay: false,
    );
  }

  @override
  Future<contracts.UserSettingsCommandResult> updatePrivacySettings(
    contracts.UpdatePrivacySettingsCommand command,
  ) async {
    return contracts.UserSettingsCommandResult(
      userId: 'owner-id',
      version: ++version,
      idempotentReplay: false,
    );
  }

  @override
  Future<contracts.UserSettingsCommandResult> updateCallSettings(
    contracts.UpdateCallSettingsCommand command,
  ) async {
    callCommands.add(command);
    return contracts.UserSettingsCommandResult(
      userId: 'owner-id',
      version: ++version,
      idempotentReplay: false,
    );
  }

  @override
  Future<contracts.AppearanceSettingsView> updateAppearanceSettings(
    contracts.UpdateAppearanceSettingsCommand command,
  ) async {
    return contracts.AppearanceSettingsView(
      themeMode: command.themeMode,
      fontSizePreset: command.fontSizePreset,
      source: contracts.AppearanceSource.ownerDefault,
      ownerDefaultThemeMode: command.themeMode,
      ownerDefaultFontSizePreset: command.fontSizePreset,
      hasSubAccountOverride: false,
      version: ++version,
      updatedAt: DateTime.utc(2026, 7, 19),
    );
  }
}
