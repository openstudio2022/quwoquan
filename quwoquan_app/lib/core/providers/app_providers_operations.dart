part of 'app_providers.dart';

final cloudClientContextProvider = Provider<CloudClientContextProvider>((ref) {
  return const AppCloudClientContextProvider();
});

final cloudRuntimeEnvironmentProvider = Provider<CloudRuntimeEnvironment>((
  ref,
) {
  return CloudRuntimeEnvironment.fromCompileTime();
});

final generatedCloudOperationClientProvider =
    Provider<GeneratedCloudOperationClient>((ref) {
      final clientContext = ref.watch(cloudClientContextProvider);
      return buildGeneratedCloudOperationClient(
        httpClient: ref.watch(cloudHttpClientProvider),
        clientContextProvider: clientContext,
        environment: ref.watch(cloudRuntimeEnvironmentProvider),
        telemetrySink: AppCloudOperationTelemetrySink(
          clientContextProvider: clientContext,
        ),
      );
    });

final opsVisitRepositoryProvider = Provider<OpsVisitRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteOpsVisitRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    );
  }
  return MockOpsVisitRepository();
});

final locationGatewayProvider = Provider<LocationGateway>((ref) {
  return const GeolocatorLocationGateway();
});

final _createLocationRemoteAdapterProvider =
    Provider<RemoteLocationQueryAdapter>((ref) {
      return RemoteLocationQueryAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _locationInvocationContext(
          ref,
          surface: AppUiSurfaces.createWorkspace,
          clientPageId: clientPageId,
        ),
      );
    });

final createLocationNearbyReaderProvider = Provider<NearbyLocationReader>((
  ref,
) {
  return ref.watch(_createLocationRemoteAdapterProvider);
});

final createLocationSearchReaderProvider = Provider<LocationSearchReader>((
  ref,
) {
  return ref.watch(_createLocationRemoteAdapterProvider);
});

final globalSearchLocationReaderProvider = Provider<LocationSearchReader>((
  ref,
) {
  return RemoteLocationQueryAdapter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _locationInvocationContext(
      ref,
      surface: AppUiSurfaces.globalSearchNetworkResults,
      clientPageId: clientPageId,
    ),
  );
});

final createLocationCoordinatorProvider = Provider<CreateLocationCoordinator>((
  ref,
) {
  return CreateLocationCoordinator(
    nearbyReader: ref.watch(createLocationNearbyReaderProvider),
    searchReader: ref.watch(createLocationSearchReaderProvider),
    locationGateway: ref.watch(locationGatewayProvider),
  );
});

final _contentReportRemoteAdapterProvider =
    Provider.family<RemoteContentReportAdapter, AppUiSurface>((ref, surface) {
      return RemoteContentReportAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      );
    });

final homeFeedContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportRemoteAdapterProvider(AppUiSurfaces.homeFeed),
      );
    });

final workBrowserContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportRemoteAdapterProvider(AppUiSurfaces.workBrowser),
      );
    });

final userProfileContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportRemoteAdapterProvider(AppUiSurfaces.userProfile),
      );
    });

final _profileUpdateProposalRemoteProvider =
    Provider.family<RemoteProfileUpdateProposalFacet, AppUiSurface>(
      (ref, surface) => RemoteProfileUpdateProposalFacet(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {required command}) =>
            _profileUpdateProposalInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              command: command,
            ),
      ),
    );

final profileEditProposalCommandWriterProvider =
    Provider<ProfileUpdateProposalCommandWriter>((ref) {
      return ref.watch(
        _profileUpdateProposalRemoteProvider(AppUiSurfaces.profileEdit),
      );
    });

final profileEditProposalQueryReaderProvider =
    Provider<ProfileUpdateProposalQueryReader>((ref) {
      return ref.watch(
        _profileUpdateProposalRemoteProvider(AppUiSurfaces.profileEdit),
      );
    });

final assistantProfileProposalCommandWriterProvider =
    Provider<ProfileUpdateProposalCommandWriter>((ref) {
      return ref.watch(
        _profileUpdateProposalRemoteProvider(
          AppUiSurfaces.personalAssistantDialog,
        ),
      );
    });

CloudOperationInvocationContext _profileUpdateProposalInvocationContext(
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
    idempotencyKey: command ? const Uuid().v4() : null,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

CloudOperationInvocationContext _reportInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.subAccountId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    idempotencyKey: const Uuid().v4(),
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

CloudOperationInvocationContext _locationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.subAccountId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}
