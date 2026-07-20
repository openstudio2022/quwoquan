part of 'app_providers.dart';

final contentPostProjectionMapperProvider =
    Provider<ContentPostProjectionMapper>(
      (ref) => const ContentPostProjectionMapper(),
    );

final _remoteContentPostReaderAdapterProvider =
    Provider.family<RemoteContentPostReaderAdapter, AppUiSurface>((
      ref,
      surface,
    ) {
      return RemoteContentPostReaderAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _contentQueryInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      );
    });

final _contentPostReaderProvider =
    Provider.family<CachedContentPostReader, AppUiSurface>((ref, surface) {
      final adapter = ref.watch(
        _remoteContentPostReaderAdapterProvider(surface),
      );
      return CachedContentPostReader(
        detailDelegate: adapter,
        authorPostsDelegate: adapter,
        postCache: ref.watch(postObjectCacheProvider),
        querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
        userProfileCache: ref.watch(userProfileCacheProvider),
        telemetrySink: ref.watch(cacheTelemetrySinkProvider),
      );
    });

final workBrowserContentPostDetailReaderProvider =
    Provider<ContentPostDetailReader>(
      (ref) => ref.watch(_contentPostReaderProvider(AppUiSurfaces.workBrowser)),
    );

final globalSearchContentPostDetailReaderProvider =
    Provider<ContentPostDetailReader>(
      (ref) => ref.watch(
        _contentPostReaderProvider(AppUiSurfaces.globalSearchNetworkResults),
      ),
    );

final createWorkspaceContentPostPublicationStatusReaderProvider =
    Provider<ContentPostPublicationStatusReader>(
      (ref) => ref.watch(
        _remoteContentPostReaderAdapterProvider(AppUiSurfaces.createWorkspace),
      ),
    );

final homepageDetailEntityWishlistStateReaderProvider =
    Provider<ContentEntityWishlistStateReader>(
      (ref) => ref.watch(
        _remoteContentPostReaderAdapterProvider(AppUiSurfaces.homepageDetail),
      ),
    );

final userProfileContentAuthorPostsReaderProvider =
    Provider<ContentAuthorPostsReader>(
      (ref) => ref.watch(_contentPostReaderProvider(AppUiSurfaces.userProfile)),
    );

final _remoteFootprintRepositoryProvider = Provider<RemoteFootprintRepository>((
  ref,
) {
  return RemoteFootprintRepository(
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

CloudOperationInvocationContext _contentCommandInvocationContext(
  Ref ref, {
  required String clientPageId,
  String? idempotencyKey,
}) {
  final base = _contentQueryInvocationContext(
    ref,
    surface: AppUiSurfaces.createWorkspace,
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
