import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/runtime/platform/permissions/microphone_permission_guard.dart';

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
    test('永久拒绝 gate 只显示恢复组约定的去设置动作', () {
      final semantic = coordinator.permissionSemantic(
        AppPermissionKind.photos,
        openSettings: true,
      );
      expect(semantic.category, UiErrorCategory.permissionRequired);
      expect(semantic.presentation, UiErrorPresentation.gateCard);
      expect(semantic.primaryAction?.type, UiErrorActionType.openSettings);
      expect(semantic.secondaryAction, isNull);
      expect(semantic.userRecoveryGroup, AppUserRecoveryGroup.enablePermission);
    });

    test('L3 gate 使用 enablePermission 唯一文案', () {
      final semantic = coordinator.permissionSemantic(
        AppPermissionKind.microphone,
        openSettings: true,
      );
      expect(semantic.title, SearchText.recoveryEnablePermissionTitle);
      expect(semantic.message, SearchText.recoveryEnablePermissionMessage);
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

  // spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-006
  group('GWT-006 JIT 麦克风一次手势至多一个 App modal', () {
    setUp(() {
      // ensure() 首次调用会注册默认 platform adapters；先行 attach 让默认注册
      // 发生在 fake 安装之前，避免真实 platform channel 覆盖测试替身后挂起。
      coordinator.ensureLifecycleAttached();
      coordinator.phaseReaders.clear();
      coordinator.requesters.clear();
      coordinator.grantCheckers.clear();
      coordinator.primerCheckers.clear();
      coordinator.primerMarkers.clear();
      coordinator.settingsOpener = () async => false;
    });

    Future<BuildContext> pumpDialogHost(WidgetTester tester) async {
      late BuildContext hostContext;
      await tester.pumpWidget(
        CupertinoApp(
          home: Builder(
            builder: (context) {
              hostContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      return hostContext;
    }

    testWidgets('requestable 软拒：全程零 App modal，仅警示 toast', (tester) async {
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          AppPermissionPhase.requestable;
      coordinator.requesters[AppPermissionKind.microphone] = () async => false;
      final context = await pumpDialogHost(tester);

      final outcome = await coordinator.ensure(
        context,
        AppPermissionKind.microphone,
        surface: AppPermissionSurface.jit,
      );
      await tester.pump();

      expect(outcome, AppPermissionEnsureOutcome.denied);
      expect(find.byType(CupertinoAlertDialog), findsNothing);
      expect(find.text(ChatText.chatVoicePermissionPrimerTitle), findsNothing);
      expect(find.text(ChatText.chatVoicePermissionDenied), findsOneWidget);
      AppToast.dismiss();
      await tester.pump();
    });

    testWidgets('requestable 转永久拒：恰一个去设置 dialog，无 primer 叠加', (tester) async {
      var phaseCalls = 0;
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          ++phaseCalls == 1
          ? AppPermissionPhase.requestable
          : AppPermissionPhase.settingsRequired;
      coordinator.requesters[AppPermissionKind.microphone] = () async => false;
      final context = await pumpDialogHost(tester);

      final outcomeFuture = coordinator.ensure(
        context,
        AppPermissionKind.microphone,
        surface: AppPermissionSurface.jit,
      );
      await tester.pumpAndSettle();

      // 唯一 App modal 是恢复组去设置 dialog；primer 不得叠加出现。
      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.text(SearchText.recoveryEnablePermissionTitle), findsOneWidget);
      expect(find.text(ChatText.chatVoicePermissionPrimerTitle), findsNothing);

      await tester.tap(find.text(SearchText.recoveryEnablePermissionAction));
      await tester.pumpAndSettle();
      expect(await outcomeFuture, AppPermissionEnsureOutcome.settingsRequired);
      expect(find.byType(CupertinoAlertDialog), findsNothing);
    });

    testWidgets('settingsRequired 起步：同样只有一个去设置 dialog', (tester) async {
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          AppPermissionPhase.settingsRequired;
      final context = await pumpDialogHost(tester);

      final outcomeFuture = coordinator.ensure(
        context,
        AppPermissionKind.microphone,
        surface: AppPermissionSurface.jit,
      );
      await tester.pumpAndSettle();

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.text(ChatText.chatVoicePermissionPrimerTitle), findsNothing);

      await tester.tap(find.text(SearchText.recoveryEnablePermissionAction));
      await tester.pumpAndSettle();
      expect(await outcomeFuture, AppPermissionEnsureOutcome.settingsRequired);
    });

    testWidgets('会话 suppress 中再次触发：零 modal，仅软提示不打扰', (tester) async {
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          AppPermissionPhase.settingsRequired;
      coordinator
              .testSession(AppPermissionKind.microphone)
              .suppressSettingsPrompt =
          true;
      final context = await pumpDialogHost(tester);

      final outcome = await coordinator.ensure(
        context,
        AppPermissionKind.microphone,
        surface: AppPermissionSurface.jit,
      );
      await tester.pump();

      expect(outcome, AppPermissionEnsureOutcome.softDenied);
      expect(find.byType(CupertinoAlertDialog), findsNothing);
      expect(
        find.text(ChatText.permissionStillDeniedMessage('麦克风')),
        findsOneWidget,
      );
      AppToast.dismiss();
      await tester.pump();
    });
  });

  // spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-008
  group('GWT-008 权限 primer 文案与继续动作一致', () {
    setUp(() {
      coordinator.ensureLifecycleAttached();
      coordinator.phaseReaders.clear();
      coordinator.requesters.clear();
      coordinator.grantCheckers.clear();
      coordinator.primerCheckers.clear();
      coordinator.primerMarkers.clear();
      coordinator.settingsOpener = () async => false;
    });

    Future<BuildContext> pumpDialogHost(WidgetTester tester) async {
      late BuildContext hostContext;
      await tester.pumpWidget(
        CupertinoApp(
          home: Builder(
            builder: (context) {
              hostContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      return hostContext;
    }

    testWidgets('primer 解释阻断原因，继续按钮统一为「继续」且不与文案矛盾', (tester) async {
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          AppPermissionPhase.requestable;
      coordinator.requesters[AppPermissionKind.microphone] = () async => false;
      coordinator.primerCheckers[AppPermissionKind.microphone] = () async =>
          false;
      final context = await pumpDialogHost(tester);

      final outcomeFuture = coordinator.ensure(
        context,
        AppPermissionKind.microphone,
        surface: AppPermissionSurface.page,
      );
      await tester.pumpAndSettle();

      expect(find.text(ChatText.chatVoicePermissionPrimerTitle), findsOneWidget);
      expect(
        find.text(ChatText.chatVoicePermissionPrimerMessage),
        findsOneWidget,
      );
      expect(find.text(ChatText.permissionPrimerContinue), findsOneWidget);
      // 文案引导「继续 → 系统弹窗」，不得指示用户直接点「允许」造成矛盾。
      expect(ChatText.chatVoicePermissionPrimerMessage, contains('继续'));
      expect(ChatText.chatVoicePermissionPrimerMessage, contains('系统弹窗'));

      await tester.tap(find.text(FoundationText.cancel));
      await tester.pumpAndSettle();
      expect(await outcomeFuture, AppPermissionEnsureOutcome.denied);
    });

    testWidgets('点「继续」只触发系统权限请求这一个声明的下一步', (tester) async {
      var requesterCalls = 0;
      var markerCalls = 0;
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          requesterCalls == 0
          ? AppPermissionPhase.requestable
          : AppPermissionPhase.granted;
      coordinator.requesters[AppPermissionKind.microphone] = () async {
        requesterCalls += 1;
        return true;
      };
      coordinator.primerCheckers[AppPermissionKind.microphone] = () async =>
          false;
      coordinator.primerMarkers[AppPermissionKind.microphone] = () async {
        markerCalls += 1;
      };
      final context = await pumpDialogHost(tester);

      final outcomeFuture = coordinator.ensure(
        context,
        AppPermissionKind.microphone,
        surface: AppPermissionSurface.page,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text(ChatText.permissionPrimerContinue));
      await tester.pumpAndSettle();

      expect(await outcomeFuture, AppPermissionEnsureOutcome.granted);
      expect(requesterCalls, 1);
      expect(markerCalls, 1);
      // 继续后直接进入系统请求，不出现第二个 App dialog。
      expect(find.byType(CupertinoAlertDialog), findsNothing);
    });

    testWidgets('取消 primer 不触发系统权限请求', (tester) async {
      var requesterCalls = 0;
      coordinator.phaseReaders[AppPermissionKind.microphone] = () async =>
          AppPermissionPhase.requestable;
      coordinator.requesters[AppPermissionKind.microphone] = () async {
        requesterCalls += 1;
        return false;
      };
      coordinator.primerCheckers[AppPermissionKind.microphone] = () async =>
          false;
      final context = await pumpDialogHost(tester);

      final outcomeFuture = coordinator.ensure(
        context,
        AppPermissionKind.microphone,
        surface: AppPermissionSurface.page,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text(FoundationText.cancel));
      await tester.pumpAndSettle();

      expect(await outcomeFuture, AppPermissionEnsureOutcome.denied);
      expect(requesterCalls, 0);
    });
  });

  group('MicrophonePermissionGuard 兼容层', () {
    test('permissionSemantic 保留语音输入前置说明', () {
      final semantic = MicrophonePermissionGuard.permissionSemantic(
        title: CallText.callPermissionMicTitle,
        message: CallText.callPermissionMicDenied,
        openSettings: true,
      );
      expect(semantic.title, CallText.callPermissionMicTitle);
      expect(semantic.message, CallText.callPermissionMicDenied);
    });
  });

  group('文案 — UAT 验收口径', () {
    test('分步设置路径包含应用名与权限名', () {
      expect(ChatText.permissionStillDeniedMessage('麦克风'), contains('设置'));
      expect(ChatText.permissionStillDeniedMessage('麦克风'), contains('趣我圈'));
    });
  });
}
