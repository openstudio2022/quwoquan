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
  final personaId = persona?.subAccountId.trim() ?? '';
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
      (ref) => RemoteIncomingCallPresentationAcknowledger(
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
  (ref) => RemoteDevicePushEndpointWriter(
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
      return RemoteCallLifecycleCommandWriter(
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
      return RemoteCallParticipantCommandWriter(
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
      return RemoteCallMediaControlWriter(
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
      return RemoteCallScreenShareWriter(
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
  return RemoteCallQuery(
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
