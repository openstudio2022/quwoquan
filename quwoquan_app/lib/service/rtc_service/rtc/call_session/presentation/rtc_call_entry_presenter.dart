import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/runtime/errors/generated/rtc/rtc_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_permission_guard.dart';

typedef RtcCallEntryPermissionRequest =
    Future<CallPermissionOutcome> Function(
      BuildContext context,
      CallType callType,
    );
typedef RtcCallEntryParticipantPicker =
    Future<List<String>?> Function(
      BuildContext context,
      RtcCallEntryIntent intent,
    );
typedef RtcCallEntryStarter =
    Future<String?> Function(
      WidgetRef ref,
      RtcCallEntryIntent intent,
      List<String> selectedInviteeIds,
      AppUiSurface sourceSurface,
    );
typedef RtcOutgoingCallNavigator =
    void Function(BuildContext context, String callId);

enum RtcCallEntryPresentationResult {
  started,
  cancelled,
  unavailable,
  permissionBlocked,
  failed,
}

/// Widget 层薄 presenter：统一权限预检、选人、CallSession 发起与 generated route 导航。
///
/// 对象授权与 command 构造仍由 application [RtcCallEntryCoordinator] 负责；
/// presenter 不持有关系、Conversation 或 Circle 的第二套规则。
final class RtcCallEntryPresenter {
  const RtcCallEntryPresenter({
    this.permissionRequest,
    this.participantPicker,
    this.callStarter,
    this.outgoingNavigator,
  });

  final RtcCallEntryPermissionRequest? permissionRequest;
  final RtcCallEntryParticipantPicker? participantPicker;
  final RtcCallEntryStarter? callStarter;
  final RtcOutgoingCallNavigator? outgoingNavigator;

  Future<RtcCallEntryPresentationResult> start({
    required BuildContext context,
    required WidgetRef ref,
    required RtcCallEntryIntent intent,
    required AppUiSurface sourceSurface,
  }) async {
    if (!intent.availability.isAvailable) {
      await _showUnavailable(context, intent.availability.reason!);
      return RtcCallEntryPresentationResult.unavailable;
    }

    final requestPermission = permissionRequest ?? _requestPermission;
    final permissionOutcome = await requestPermission(
      context,
      CallType.fromWire(
        intent.mediaType.wireValue,
        'RtcCallEntryIntent.mediaType',
      ),
    );
    if (!context.mounted ||
        permissionOutcome == CallPermissionOutcome.blocked) {
      return RtcCallEntryPresentationResult.permissionBlocked;
    }

    final effectiveIntent =
        permissionOutcome == CallPermissionOutcome.fallbackVoiceOnly
        ? intent.withMediaType(RtcCallEntryMediaType.audio)
        : intent;
    if (!effectiveIntent.availability.isAvailable) {
      await _showUnavailable(context, effectiveIntent.availability.reason!);
      return RtcCallEntryPresentationResult.unavailable;
    }

    var selectedInviteeIds = const <String>[];
    if (effectiveIntent.requiresParticipantPicker) {
      final pickParticipants = participantPicker ?? _pickParticipants;
      final selected = await pickParticipants(context, effectiveIntent);
      if (!context.mounted || selected == null || selected.isEmpty) {
        return RtcCallEntryPresentationResult.cancelled;
      }
      selectedInviteeIds = selected;
    }

    final startCall = callStarter ?? _startCall;
    final callId = await startCall(
      ref,
      effectiveIntent,
      selectedInviteeIds,
      sourceSurface,
    );
    if (!context.mounted) {
      return callId == null
          ? RtcCallEntryPresentationResult.failed
          : RtcCallEntryPresentationResult.started;
    }
    if (callId == null || callId.trim().isEmpty) {
      await _showStartFailure(context, ref);
      return RtcCallEntryPresentationResult.failed;
    }

    final navigate = outgoingNavigator ?? _navigateOutgoing;
    navigate(context, callId);
    return RtcCallEntryPresentationResult.started;
  }

  static Future<CallPermissionOutcome> _requestPermission(
    BuildContext context,
    CallType callType,
  ) {
    return CallPermissionGuard.ensure(context, callType: callType);
  }

  static Future<List<String>?> _pickParticipants(
    BuildContext context,
    RtcCallEntryIntent intent,
  ) {
    return context.push<List<String>>(
      AppRoutePaths.rtcPickParticipants,
      extra: CallParticipantPickerRouteExtra.initialCall(
        maxParticipants: intent.maxParticipants,
        conversationId: intent.conversationId,
        defaultSelectAll: intent.defaultSelectAll,
      ),
    );
  }

  static Future<String?> _startCall(
    WidgetRef ref,
    RtcCallEntryIntent intent,
    List<String> selectedInviteeIds,
    AppUiSurface sourceSurface,
  ) {
    return ref
        .read(callSessionProvider.notifier)
        .initiateCall(
          intent: intent,
          selectedInviteeIds: selectedInviteeIds,
          sourceSurface: sourceSurface,
        );
  }

  static void _navigateOutgoing(BuildContext context, String callId) {
    context.push(AppRoutePaths.rtcOutgoing(callId: callId));
  }

  static Future<void> _showUnavailable(
    BuildContext context,
    RtcCallEntryUnavailableReason reason,
  ) {
    // 端侧本地判定的入口不可用原因同样对应已声明的 stable code，因此走
    // localDomainCloudException 接回统一映射链：与云端返回同一个码时，文案、
    // 恢复动作与埋点 sourceCode 完全一致，不再是只剩字符串的旁路。
    final localCode = switch (reason) {
      RtcCallEntryUnavailableReason.blocked => RtcErrorCode.blocked,
      RtcCallEntryUnavailableReason.notMutual ||
      RtcCallEntryUnavailableReason.capabilityDenied ||
      RtcCallEntryUnavailableReason.missingTarget => RtcErrorCode.notMutual,
      RtcCallEntryUnavailableReason.missingConversationContext ||
      RtcCallEntryUnavailableReason.missingCircleContext =>
        RtcErrorCode.invalidCallAction,
      RtcCallEntryUnavailableReason.noParticipants =>
        RtcErrorCode.invalidArgument,
      RtcCallEntryUnavailableReason.participantLimitExceeded =>
        RtcErrorCode.callFull,
    };
    return AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: localDomainCloudException(localCode.code),
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        allowRetry: false,
      ),
    );
  }

  static Future<void> _showStartFailure(BuildContext context, WidgetRef ref) {
    final failure = ref.read(callSessionProvider).failure;
    if (failure != null) {
      return AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: failure,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
      );
    }
    // 没有具体 failure 时也不再手写语义：以 canonical internal_error 走同一条
    // 映射链，保证这类"兜底失败"在埋点里仍然带着可聚合的 sourceCode。
    return AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: localDomainCloudException(RtcErrorCode.internalError.code),
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      ),
    );
  }
}

final rtcCallEntryPresenterProvider = Provider<RtcCallEntryPresenter>(
  (ref) => const RtcCallEntryPresenter(),
);
