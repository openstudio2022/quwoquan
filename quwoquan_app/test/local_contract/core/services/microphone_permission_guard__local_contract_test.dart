import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/services/microphone_permission_guard.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('MicrophonePermissionGuard.permissionSemantic — 统一语义', () {
    test('永久拒绝：permissionRequired + gateCard + openSettings', () {
      final semantic = MicrophonePermissionGuard.permissionSemantic(
        title: UITextConstants.chatVoicePermissionPrimerTitle,
        message: UITextConstants.chatVoicePermissionOpenSettings,
        openSettings: true,
      );

      expect(semantic.category, UiErrorCategory.permissionRequired);
      expect(semantic.presentation, UiErrorPresentation.gateCard);
      expect(semantic.primaryAction?.type, UiErrorActionType.openSettings);
      expect(semantic.primaryAction?.label, UITextConstants.openSettings);
    });
  });

  group('MicrophonePermissionGuard.isGranted — 委托 Coordinator', () {
    late AppPermissionCoordinator coordinator;

    setUp(() {
      coordinator = AppPermissionCoordinator.createForTest();
      AppPermissionCoordinator.debugInstance = coordinator;
      coordinator.grantCheckers[AppPermissionKind.microphone] = () async => true;
    });

    tearDown(() {
      AppPermissionCoordinator.debugInstance = null;
    });

    test('Coordinator 报告已授权', () async {
      expect(await MicrophonePermissionGuard.isGranted(), isTrue);
    });
  });

  group('MicrophonePermissionOutcome — 枚举齐备', () {
    test('三态枚举与聊天/RTC 预检语义对齐', () {
      expect(MicrophonePermissionOutcome.values, hasLength(3));
    });
  });
}
