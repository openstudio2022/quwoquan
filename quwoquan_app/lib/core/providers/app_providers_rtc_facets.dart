import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/adapters/chat_member_presentation_resolver.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/application/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/application/call_participant_presentation.dart';
import 'package:quwoquan_app/user/account/device_registration/application/device_push_endpoint_writer.dart';
import 'package:quwoquan_app/runtime/di/notification_dependencies.dart';
import 'package:quwoquan_app/runtime/di/rtc_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/core/providers/app_providers_app_state.dart';
import 'package:quwoquan_app/core/providers/app_providers_chat_search.dart';
final callParticipantPresentationResolverProvider =
    Provider<CallParticipantPresentationResolver>((ref) {
      return ChatMemberCallParticipantPresentationResolver(
        ref.watch(chatMemberRepositoryProvider),
      );
    });

CloudOperationInvocationContext _rtcInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  required bool command,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    idempotencyKey: command
        ? AppTraceContextStore.instance.newRequestId()
        : null,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

CloudOperationInvocationContext rtcOperationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  required bool command,
}) => _rtcInvocationContext(
  ref,
  surface: surface,
  clientPageId: clientPageId,
  command: command,
);

final incomingCallPresentationAcknowledgerProvider =
    Provider<IncomingCallPresentationAcknowledger>(
      (ref) =>
          NotificationProductionComposition.generatedAdapter<
            IncomingCallPresentationAcknowledger
          >(
            NotificationProductionAdapter.incomingCallPresentation,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext: (clientPageId) => rtcOperationInvocationContext(
              ref,
              surface: AppUiSurfaces.rtcIncoming,
              clientPageId: clientPageId,
              command: true,
            ),
          ),
    );

final devicePushEndpointWriterProvider = Provider<DevicePushEndpointWriter>(
  (ref) => UserProductionComposition.generatedAdapter<DevicePushEndpointWriter>(
    UserProductionAdapter.devicePushEndpoint,
    client: ref.watch(generatedCloudOperationClientProvider),
    clientContextSnapshot: ref.watch(cloudClientContextProvider).snapshot,
    invocationContext: (clientPageId) => rtcOperationInvocationContext(
      ref,
      surface: AppUiSurfaces.rtcIncoming,
      clientPageId: clientPageId,
      command: true,
    ),
  ),
);

final devicePushEndpointCoordinatorProvider =
    Provider<DevicePushEndpointCoordinator>((ref) {
      return DevicePushEndpointCoordinator(
        gateway: ref.watch(pushEndpointGatewayProvider),
        writer: ref.watch(devicePushEndpointWriterProvider),
      );
    });

final rtcCallLifecycleCommandWriterProvider =
    Provider.family<CallLifecycleCommandWriter, AppUiSurface>((ref, surface) {
      return RtcProductionComposition.generatedAdapter<
        CallLifecycleCommandWriter
      >(
        RtcProductionAdapter.callLifecycle,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {required command}) =>
            _rtcInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              command: command,
            ),
      );
    });

final rtcCallParticipantCommandWriterProvider =
    Provider.family<CallParticipantCommandWriter, AppUiSurface>((ref, surface) {
      return RtcProductionComposition.generatedAdapter<
        CallParticipantCommandWriter
      >(
        RtcProductionAdapter.callParticipant,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {required command}) =>
            _rtcInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              command: command,
            ),
      );
    });

final rtcCallMediaControlWriterProvider =
    Provider.family<CallMediaControlWriter, AppUiSurface>((ref, surface) {
      return RtcProductionComposition.generatedAdapter<CallMediaControlWriter>(
        RtcProductionAdapter.callMediaControl,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {required command}) =>
            _rtcInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              command: command,
            ),
      );
    });

final rtcCallScreenShareWriterProvider =
    Provider.family<CallScreenShareWriter, AppUiSurface>((ref, surface) {
      return RtcProductionComposition.generatedAdapter<CallScreenShareWriter>(
        RtcProductionAdapter.callScreenShare,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {required command}) =>
            _rtcInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              command: command,
            ),
      );
    });

final rtcCallQueryProvider = Provider.family<CallQuery, AppUiSurface>((
  ref,
  surface,
) {
  return RtcProductionComposition.generatedAdapter<CallQuery>(
    RtcProductionAdapter.callQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _rtcInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
});
