import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/cloud/rtc/generated/rtc_errors.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_permission_guard.dart';

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
      CallType.fromWire(intent.mediaType.wireValue, 'RtcCallEntryIntent.mediaType'),
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
    final message = switch (reason) {
      RtcCallEntryUnavailableReason.blocked =>
        RtcErrorCode.blocked.defaultMessage,
      RtcCallEntryUnavailableReason.notMutual ||
      RtcCallEntryUnavailableReason.capabilityDenied ||
      RtcCallEntryUnavailableReason.missingTarget =>
        RtcErrorCode.notMutual.defaultMessage,
      RtcCallEntryUnavailableReason.missingConversationContext ||
      RtcCallEntryUnavailableReason.missingCircleContext =>
        CallText.callContextUnavailable,
      RtcCallEntryUnavailableReason.noParticipants => CallText.callNoContacts,
      RtcCallEntryUnavailableReason.participantLimitExceeded =>
        RtcErrorCode.callFull.defaultMessage,
    };
    return AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        title: CallText.callEntryUnavailableTitle,
        message: message,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: FoundationText.confirm,
        ),
        dismissible: true,
        presentation: UiErrorPresentation.actionDialog,
        tone: UiErrorTone.caution,
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
    return AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        title: CallText.callEntryUnavailableTitle,
        message: RtcErrorCode.internalError.defaultMessage,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: FoundationText.confirm,
        ),
        dismissible: true,
        presentation: UiErrorPresentation.actionDialog,
        tone: UiErrorTone.caution,
      ),
    );
  }
}

final rtcCallEntryPresenterProvider = Provider<RtcCallEntryPresenter>(
  (ref) => const RtcCallEntryPresenter(),
);
