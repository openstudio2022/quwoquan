part of 'app_providers.dart';

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
          AppProductionComposition.generatedAdapter<
            IncomingCallPresentationAcknowledger
          >(
            AppProductionAdapter.incomingCallPresentation,
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
  (ref) => AppProductionComposition.generatedAdapter<DevicePushEndpointWriter>(
    AppProductionAdapter.devicePushEndpoint,
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
      return AppProductionComposition.generatedAdapter<
        CallLifecycleCommandWriter
      >(
        AppProductionAdapter.rtcCallLifecycle,
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
      return AppProductionComposition.generatedAdapter<
        CallParticipantCommandWriter
      >(
        AppProductionAdapter.rtcCallParticipant,
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
      return AppProductionComposition.generatedAdapter<CallMediaControlWriter>(
        AppProductionAdapter.rtcCallMediaControl,
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
      return AppProductionComposition.generatedAdapter<CallScreenShareWriter>(
        AppProductionAdapter.rtcCallScreenShare,
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
  return AppProductionComposition.generatedAdapter<CallQuery>(
    AppProductionAdapter.rtcCallQuery,
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
