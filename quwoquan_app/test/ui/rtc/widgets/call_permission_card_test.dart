import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_permission_guard.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // S6 统一权限卡片：复用 UiErrorSemantic(permissionRequired) + 去设置，
  // 不另起 RTC 专用权限提示。
  // ──────────────────────────────────────────────────────────────────
  group('CallPermissionGuard.permissionSemantic — 统一语义', () {
    test('麦克风权限卡片：permissionRequired + openSettings', () {
      final semantic = CallPermissionGuard.permissionSemantic(
        title: UITextConstants.callPermissionMicTitle,
        message: UITextConstants.callPermissionMicDenied,
      );
      expect(semantic.category, UiErrorCategory.permissionRequired);
      expect(semantic.scope, UiErrorScope.dialog);
      expect(semantic.presentation, UiErrorPresentation.gateCard);
      expect(semantic.tone, UiErrorTone.info);
      expect(semantic.title, UITextConstants.callPermissionMicTitle);
      expect(
        semantic.primaryAction?.type,
        UiErrorActionType.openSettings,
      );
    });

    test('摄像头权限卡片：去设置文案统一', () {
      final semantic = CallPermissionGuard.permissionSemantic(
        title: UITextConstants.callPermissionCameraTitle,
        message: UITextConstants.callPermissionOpenSettings,
      );
      expect(semantic.title, UITextConstants.callPermissionCameraTitle);
      expect(
        semantic.primaryAction?.label,
        UITextConstants.openSettings,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 预检结果语义：视频缺摄像头降级仅语音；麦克风缺则阻断。
  // ──────────────────────────────────────────────────────────────────
  group('CallPermissionOutcome — 降级语义', () {
    test('三态枚举齐备', () {
      expect(CallPermissionOutcome.values, hasLength(3));
      expect(
        CallPermissionOutcome.values,
        containsAll(<CallPermissionOutcome>[
          CallPermissionOutcome.granted,
          CallPermissionOutcome.fallbackVoiceOnly,
          CallPermissionOutcome.blocked,
        ]),
      );
    });
  });
}
