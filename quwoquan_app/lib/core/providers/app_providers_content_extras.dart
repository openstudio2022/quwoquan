part of 'app_providers.dart';

final class _ContentPostReaderDelegates {
  const _ContentPostReaderDelegates({
    required this.detail,
    required this.authorPosts,
  });

  final ContentPostDetailReader detail;
  final ContentAuthorPostsReader authorPosts;
}

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
      final delegates = cloudRepositoryImplForMode<_ContentPostReaderDelegates>(
        ref.watch(appDataSourceModeProvider),
        remote: () {
          final adapter = ref.watch(
            _remoteContentPostReaderAdapterProvider(surface),
          );
          return _ContentPostReaderDelegates(
            detail: adapter,
            authorPosts: adapter,
          );
        },
        mock: () {
          final adapter = MockContentRepository();
          return _ContentPostReaderDelegates(
            detail: adapter,
            authorPosts: adapter,
          );
        },
      );
      return CachedContentPostReader(
        detailDelegate: delegates.detail,
        authorPostsDelegate: delegates.authorPosts,
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

final userProfileContentAuthorPostsReaderProvider =
    Provider<ContentAuthorPostsReader>(
      (ref) => ref.watch(_contentPostReaderProvider(AppUiSurfaces.userProfile)),
    );

final _remoteContentPostSearchAdapterProvider =
    Provider<RemoteContentPostSearchAdapter>((ref) {
      return RemoteContentPostSearchAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _contentQueryInvocationContext(
          ref,
          surface: AppUiSurfaces.globalSearchNetworkResults,
          clientPageId: clientPageId,
        ),
      );
    });

final contentPostSearchRepositoryProvider =
    Provider<ContentPostSearchRepository>((ref) {
      return cloudRepositoryImplForMode(
        ref.watch(appDataSourceModeProvider),
        remote: () => ref.watch(_remoteContentPostSearchAdapterProvider),
        mock: MockContentRepository.new,
      );
    });

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

final footprintRepositoryProvider = Provider<FootprintRepository>(
  (ref) => cloudRepositoryImplForMode(
    ref.watch(appDataSourceModeProvider),
    remote: () => ref.watch(_remoteFootprintRepositoryProvider),
    mock: MockFootprintRepository.new,
  ),
);

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
    idempotencyKey: AppTraceContextStore.instance.newRequestId(),
  );
}
