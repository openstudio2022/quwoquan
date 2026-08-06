import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/footprint_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_status_reader.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
import 'package:quwoquan_app/runtime/di/app_providers_gathering_journey.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_publication_continuation_registry.dart';

/// Cross-object Post publication follow-up handlers aggregated from domain ports.
final postPublicationContinuationRegistryProvider =
    Provider<PostPublicationContinuationRegistry>(
      (ref) => ref.watch(
        gatheringJourneyPostPublicationContinuationRegistryProvider,
      ),
    );

final contentPostProjectionMapperProvider =
    Provider<ContentPostProjectionMapper>(
      (ref) => const ContentPostProjectionMapper(),
    );

final _contentPostReaderFacetsProvider =
    Provider.family<AppProductionContentPostReaderFacets, AppUiSurface>((
      ref,
      surface,
    ) {
      return ContentProductionComposition.contentPostReaderFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => contentQueryInvocationContext(
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
  return ContentProductionComposition.generatedAdapter<FootprintRepository>(
    ContentProductionAdapter.footprint,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => contentQueryInvocationContext(
      ref,
      surface: AppUiSurfaces.myFootprint,
      clientPageId: clientPageId,
    ),
  );
});

final footprintRepositoryProvider = Provider<FootprintRepository>((ref) {
  return ref.watch(_remoteFootprintRepositoryProvider);
});

CloudOperationInvocationContext contentQueryInvocationContext(
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

CloudOperationInvocationContext contentCommandInvocationContext(
  Ref ref, {
  required String clientPageId,
  AppUiSurface surface = AppUiSurfaces.createWorkspace,
  String? idempotencyKey,
}) {
  final base = contentQueryInvocationContext(
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
