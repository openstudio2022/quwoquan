part of 'app_providers.dart';

final contentPostProjectionMapperProvider =
    Provider<ContentPostProjectionMapper>(
      (ref) => const ContentPostProjectionMapper(),
    );

final _contentPostReaderFacetsProvider =
    Provider.family<AppProductionContentPostReaderFacets, AppUiSurface>((
      ref,
      surface,
    ) {
      return AppProductionComposition.contentPostReaderFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _contentQueryInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
        postCache: ref.watch(postObjectCacheProvider),
        querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
        userProfileCache: ref.watch(userProfileCacheProvider),
        telemetrySink: ref.watch(cacheTelemetrySinkProvider),
      );
    });

final _contentPostReaderProvider =
    Provider.family<AppProductionContentPostReaderFacets, AppUiSurface>(
      (ref, surface) => ref.watch(_contentPostReaderFacetsProvider(surface)),
    );

final workBrowserContentPostDetailReaderProvider =
    Provider<ContentPostDetailReader>(
      (ref) => ref
          .watch(_contentPostReaderProvider(AppUiSurfaces.workBrowser))
          .detail,
    );

final globalSearchContentPostDetailReaderProvider =
    Provider<ContentPostDetailReader>(
      (ref) => ref
          .watch(
            _contentPostReaderProvider(
              AppUiSurfaces.globalSearchNetworkResults,
            ),
          )
          .detail,
    );

final createWorkspaceContentPostPublicationStatusReaderProvider =
    Provider<ContentPostPublicationStatusReader>(
      (ref) => ref
          .watch(
            _contentPostReaderFacetsProvider(AppUiSurfaces.createWorkspace),
          )
          .publicationStatus,
    );

final homepageDetailEntityWishlistStateReaderProvider =
    Provider<ContentEntityWishlistStateReader>(
      (ref) => ref
          .watch(_contentPostReaderFacetsProvider(AppUiSurfaces.homepageDetail))
          .wishlistState,
    );

final userProfileContentAuthorPostsReaderProvider =
    Provider<ContentAuthorPostsReader>(
      (ref) => ref
          .watch(_contentPostReaderProvider(AppUiSurfaces.userProfile))
          .authorPosts,
    );

final _remoteFootprintRepositoryProvider = Provider<FootprintRepository>((ref) {
  return AppProductionComposition.generatedAdapter<FootprintRepository>(
    AppProductionAdapter.contentFootprint,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _contentQueryInvocationContext(
      ref,
      surface: AppUiSurfaces.myFootprint,
      clientPageId: clientPageId,
    ),
  );
});

final footprintRepositoryProvider = Provider<FootprintRepository>((ref) {
  return ref.watch(_remoteFootprintRepositoryProvider);
});

CloudOperationInvocationContext _contentQueryInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
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

CloudOperationInvocationContext _contentCommandInvocationContext(
  Ref ref, {
  required String clientPageId,
  AppUiSurface surface = AppUiSurfaces.createWorkspace,
  String? idempotencyKey,
}) {
  final base = _contentQueryInvocationContext(
    ref,
    surface: surface,
    clientPageId: clientPageId,
  );
  return CloudOperationInvocationContext(
    surfaceId: base.surfaceId,
    clientPageId: base.clientPageId,
    actor: base.actor,
    routeId: base.routeId,
    idempotencyKey:
        idempotencyKey ?? AppTraceContextStore.instance.newRequestId(),
  );
}
