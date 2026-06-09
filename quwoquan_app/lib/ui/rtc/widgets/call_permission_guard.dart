import 'package:flutter/widgets.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';

/// 接听/发起前权限预检结果。
enum CallPermissionOutcome {
  /// 所需权限均已授予，可按原通话类型进行。
  granted,

  /// 摄像头被拒（视频通话），用户选择降级为仅语音继续。
  fallbackVoiceOnly,

  /// 权限不足且用户未选择降级（取消 / 去设置），不进入通话。
  blocked,
}

/// 通话权限统一预检：麦克风为硬门槛，摄像头按通话类型，永久拒绝走统一权限卡片
/// （`UiErrorCategory.permissionRequired` + 去设置），视频缺摄像头可降级仅语音。
///
/// 权限语义与卡片渲染统一复用 [UiErrorSemanticResolver] / [AppActionErrorFeedback]，
/// 不另起一套 RTC 专用错误展示（R31 横向一致 / R18 结构化错误）。
class CallPermissionGuard {
  const CallPermissionGuard._();

  /// 预检并在缺权限时弹统一卡片。返回最终可进行的结果。
  static Future<CallPermissionOutcome> ensure(
    BuildContext context, {
    required CallType callType,
  }) async {
    final micGranted = await _ensureMicrophone(context);
    if (!micGranted) {
      return CallPermissionOutcome.blocked;
    }
    if (callType.isAudio) {
      return CallPermissionOutcome.granted;
    }
    if (!context.mounted) {
      return CallPermissionOutcome.blocked;
    }
    final cameraGranted = await _ensureCamera(context);
    if (cameraGranted) {
      return CallPermissionOutcome.granted;
    }
    // 视频缺摄像头：默认降级为仅语音继续（卡片已提示去设置）。
    return CallPermissionOutcome.fallbackVoiceOnly;
  }

  static Future<bool> _ensureMicrophone(BuildContext context) async {
    final status = await Permission.microphone.status;
    if (status.isGranted) {
      return true;
    }
    final requested = await Permission.microphone.request();
    if (requested.isGranted) {
      return true;
    }
    if (!context.mounted) {
      return false;
    }
    await _presentPermissionCard(
      context,
      title: UITextConstants.callPermissionMicTitle,
      message: requested.isPermanentlyDenied
          ? UITextConstants.callPermissionOpenSettings
          : UITextConstants.callPermissionMicDenied,
    );
    return false;
  }

  static Future<bool> _ensureCamera(BuildContext context) async {
    final status = await Permission.camera.status;
    if (status.isGranted) {
      return true;
    }
    final requested = await Permission.camera.request();
    if (requested.isGranted) {
      return true;
    }
    if (!context.mounted) {
      return false;
    }
    await _presentPermissionCard(
      context,
      title: UITextConstants.callPermissionCameraTitle,
      message: requested.isPermanentlyDenied
          ? UITextConstants.callPermissionOpenSettings
          : UITextConstants.callPermissionCameraDenied,
    );
    return false;
  }

  /// 构造统一权限卡片语义（复用 [UiErrorSemantic]）。提取为静态以便单测，
  /// 杜绝 RTC 自定义权限提示样式。
  static UiErrorSemantic permissionSemantic({
    required String title,
    required String message,
  }) {
    return UiErrorSemantic(
      category: UiErrorCategory.permissionRequired,
      scope: UiErrorScope.dialog,
      title: title,
      message: message,
      primaryAction: const UiErrorAction(
        type: UiErrorActionType.openSettings,
        label: UITextConstants.callPermissionOpenSettings,
      ),
      presentation: UiErrorPresentation.actionDialog,
      tone: UiErrorTone.info,
    );
  }

  static Future<void> _presentPermissionCard(
    BuildContext context, {
    required String title,
    required String message,
  }) async {
    await AppActionErrorFeedback.show(
      context,
      semantic: permissionSemantic(title: title, message: message),
      onAction: (action) async {
        if (action.type == UiErrorActionType.openSettings) {
          await openAppSettings();
        }
      },
    );
  }
}
