import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';

/// 接听/发起前权限预检结果。
enum CallPermissionOutcome { granted, fallbackVoiceOnly, blocked }

/// 通话权限统一预检：麦克风为硬门槛，摄像头按通话类型，永久拒绝走 [AppPermissionCoordinator]。
class CallPermissionGuard {
  const CallPermissionGuard._();

  static AppPermissionCoordinator get _coordinator =>
      AppPermissionCoordinator.current;

  static Future<CallPermissionOutcome> ensure(
    BuildContext context, {
    required CallType callType,
  }) async {
    final micOutcome = await _coordinator.ensure(
      context,
      AppPermissionKind.microphone,
      surface: AppPermissionSurface.jit,
    );
    if (micOutcome != AppPermissionEnsureOutcome.granted) {
      return CallPermissionOutcome.blocked;
    }
    if (callType.isAudio) {
      return CallPermissionOutcome.granted;
    }
    if (!context.mounted) {
      return CallPermissionOutcome.blocked;
    }
    final cameraOutcome = await _coordinator.ensure(
      context,
      AppPermissionKind.camera,
      surface: AppPermissionSurface.jit,
    );
    if (cameraOutcome == AppPermissionEnsureOutcome.granted) {
      return CallPermissionOutcome.granted;
    }
    return CallPermissionOutcome.fallbackVoiceOnly;
  }

  static UiErrorSemantic permissionSemantic({
    required String title,
    required String message,
  }) {
    final base = AppPermissionCoordinator.current.permissionSemantic(
      AppPermissionKind.microphone,
      openSettings: true,
    );
    return UiErrorSemantic(
      category: base.category,
      scope: base.scope,
      title: title,
      message: message,
      primaryAction: base.primaryAction,
      secondaryAction: base.secondaryAction,
      dismissible: base.dismissible,
      presentation: base.presentation,
      tone: base.tone,
    );
  }
}
