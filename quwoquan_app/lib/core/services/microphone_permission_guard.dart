import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';

/// 麦克风权限预检结果（兼容聊天/RTC 既有 API）。
enum MicrophonePermissionOutcome { granted, denied, permanentlyDenied }

/// 麦克风权限统一预检：委托 [AppPermissionCoordinator]。
class MicrophonePermissionGuard {
  const MicrophonePermissionGuard._();

  static AppPermissionCoordinator get _coordinator =>
      AppPermissionCoordinator.current;

  static Future<bool> isGranted() =>
      _coordinator.isGranted(AppPermissionKind.microphone);

  static Future<MicrophonePermissionOutcome> ensure(
    BuildContext context, {
    AppPermissionSurface surface = AppPermissionSurface.page,
    bool? showPrimer,
    bool showUiOnFailure = true,
    VoidCallback? onOpenedSettings,
  }) async {
    final outcome = await _coordinator.ensure(
      context,
      AppPermissionKind.microphone,
      surface: surface,
      showUiOnFailure: showUiOnFailure,
      showPrimer: showPrimer,
      onSettingsReturn: onOpenedSettings == null
          ? null
          : (_) => onOpenedSettings(),
    );
    return _mapOutcome(outcome);
  }

  static UiErrorSemantic permissionSemantic({
    required String title,
    required String message,
    required bool openSettings,
  }) {
    final base = AppPermissionCoordinator.current.permissionSemantic(
      AppPermissionKind.microphone,
      openSettings: openSettings,
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

  static MicrophonePermissionOutcome _mapOutcome(
    AppPermissionEnsureOutcome outcome,
  ) {
    return switch (outcome) {
      AppPermissionEnsureOutcome.granted => MicrophonePermissionOutcome.granted,
      AppPermissionEnsureOutcome.settingsRequired ||
      AppPermissionEnsureOutcome.softDenied =>
        MicrophonePermissionOutcome.permanentlyDenied,
      AppPermissionEnsureOutcome.restricted ||
      AppPermissionEnsureOutcome.denied => MicrophonePermissionOutcome.denied,
    };
  }
}
