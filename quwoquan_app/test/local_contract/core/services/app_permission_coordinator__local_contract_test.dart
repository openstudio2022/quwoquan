import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/services/microphone_permission_guard.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AppPermissionCoordinator coordinator;

  setUp(() {
    coordinator = AppPermissionCoordinator.createForTest();
    AppPermissionCoordinator.debugInstance = coordinator;
    coordinator.phaseReaders.clear();
    coordinator.requesters.clear();
    coordinator.grantCheckers.clear();
    coordinator.clearSession();
  });

  tearDown(() {
    AppPermissionCoordinator.debugInstance = null;
  });

  group('AppPermissionCoordinator.phase / isGranted', () {
    test('granted 短路', () async {
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          AppPermissionPhase.granted;

      expect(
        await coordinator.phase(AppPermissionKind.microphone),
        AppPermissionPhase.granted,
      );
      expect(await coordinator.isGranted(AppPermissionKind.microphone), isTrue);
    });

    test('settingsRequired 映射正确', () async {
      coordinator.phaseReaders[AppPermissionKind.camera] = () async =>
          AppPermissionPhase.settingsRequired;
      coordinator.grantCheckers[AppPermissionKind.camera] = () async => false;

      expect(
        await coordinator.phase(AppPermissionKind.camera),
        AppPermissionPhase.settingsRequired,
      );
      expect(await coordinator.isGranted(AppPermissionKind.camera), isFalse);
    });
  });

  group('AppPermissionCoordinator session suppress', () {
    test('设置页未打开时清除待返回状态与 callback', () async {
      coordinator.settingsOpener = () async => false;
      var callbackInvoked = false;

      final opened = await coordinator.openSettings(
        AppPermissionKind.contacts,
        onReturn: (_) => callbackInvoked = true,
      );

      final session = coordinator.testSession(AppPermissionKind.contacts);
      expect(opened, isFalse);
      expect(session.settingsVisitPending, isFalse);
      await coordinator.handleSettingsReturnForTest();
      expect(callbackInvoked, isFalse);
    });

    test('settingsRequired + suppress 后 isGranted 仍为 false', () async {
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          AppPermissionPhase.settingsRequired;
      coordinator.grantCheckers[AppPermissionKind.microphone] = () async =>
          false;
      final session = coordinator.testSession(AppPermissionKind.microphone);
      session.suppressSettingsPrompt = true;

      expect(
        await coordinator.isGranted(AppPermissionKind.microphone),
        isFalse,
      );
      expect(session.suppressSettingsPrompt, isTrue);
    });

    test('设置返回未授权：置 suppress 并触发 callback', () async {
      coordinator.grantCheckers[AppPermissionKind.location] = () async => false;
      var callbackGranted = true;
      coordinator.markSettingsVisitPending(
        AppPermissionKind.location,
        onReturn: (granted) => callbackGranted = granted,
      );

      await coordinator.handleSettingsReturnForTest();

      final session = coordinator.testSession(AppPermissionKind.location);
      expect(session.settingsVisitPending, isFalse);
      expect(session.suppressSettingsPrompt, isTrue);
      expect(callbackGranted, isFalse);
    });

    test('设置返回已授权：清除 suppress 并触发 callback', () async {
      coordinator.grantCheckers[AppPermissionKind.photos] = () async => true;
      var callbackGranted = false;
      final session = coordinator.testSession(AppPermissionKind.photos);
      session.suppressSettingsPrompt = true;
      session.settingsVisitPending = true;
      coordinator.markSettingsVisitPending(
        AppPermissionKind.photos,
        onReturn: (granted) => callbackGranted = granted,
      );

      await coordinator.handleSettingsReturnForTest();

      expect(session.suppressSettingsPrompt, isFalse);
      expect(callbackGranted, isTrue);
    });
  });

  group('AppPermissionCoordinator.permissionSemantic', () {
    test('永久拒绝 gate 含去设置与重试授权', () {
      final semantic = coordinator.permissionSemantic(
        AppPermissionKind.photos,
        openSettings: true,
        includeRetry: true,
      );
      expect(semantic.category, UiErrorCategory.permissionRequired);
      expect(semantic.presentation, UiErrorPresentation.gateCard);
      expect(semantic.primaryAction?.type, UiErrorActionType.openSettings);
      expect(semantic.secondaryAction?.type, UiErrorActionType.retry);
    });

    test('L3 gate 标题使用 permissionSettingsGateTitle', () {
      final semantic = coordinator.permissionSemantic(
        AppPermissionKind.microphone,
        openSettings: true,
      );
      expect(
        semantic.title,
        ChatText.permissionSettingsGateTitle(
          ChatText.permissionMicrophoneLabel,
        ),
      );
    });
  });

  group('AppPermissionCoordinator surface jit', () {
    test('JIT 默认不展示 L2 primer 文案矛盾', () {
      expect(ChatText.chatVoicePermissionPrimerMessage, contains('系统弹窗'));
      expect(
        ChatText.chatVoicePermissionPrimerMessage,
        isNot(contains('请点「允许」')),
      );
    });
  });

  group('MicrophonePermissionGuard 兼容层', () {
    test('permissionSemantic 保留自定义 title/message', () {
      final semantic = MicrophonePermissionGuard.permissionSemantic(
        title: UITextConstants.callPermissionMicTitle,
        message: UITextConstants.callPermissionMicDenied,
        openSettings: true,
      );
      expect(semantic.title, UITextConstants.callPermissionMicTitle);
      expect(semantic.message, UITextConstants.callPermissionMicDenied);
    });
  });

  group('文案 — UAT 验收口径', () {
    test('分步设置路径包含应用名与权限名', () {
      expect(ChatText.permissionStillDeniedMessage('麦克风'), contains('设置'));
      expect(ChatText.permissionStillDeniedMessage('麦克风'), contains('趣我圈'));
    });
  });
}
