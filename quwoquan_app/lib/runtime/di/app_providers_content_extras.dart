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
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_publication_continuation_registry.dart';

/// Canonical cross-object publication handlers are registered only after their
/// generated owner operation is available. Unknown continuations fail closed.
final postPublicationContinuationRegistryProvider =
    Provider<PostPublicationContinuationRegistry>(
      (ref) => PostPublicationContinuationRegistry(
        const <PostPublicationContinuationHandler>[],
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

/// workBrowser 沉浸详情态的想去状态读取：详情底栏想去按钮按
/// primaryHomepageId 锚点读取当前用户 wishlist 状态。
final workBrowserEntityWishlistStateReaderProvider =
    Provider<ContentEntityWishlistStateReader>(
      (ref) => ref
          .watch(_contentPostReaderFacetsProvider(AppUiSurfaces.workBrowser))
          .wishlistState,
    );

/// Gathering 详情页共同经历聚合区读取：某次行动的公开回顾内容分页。
final gatheringDetailGatheringPostsReaderProvider =
    Provider<ContentGatheringPostsReader>(
      (ref) => ref
          .watch(
            _contentPostReaderFacetsProvider(AppUiSurfaces.gatheringDetail),
          )
          .gatheringPosts,
    );

/// 四锚点社会证明读取（按 surface 装配）：gathering 详情发起人卡、
/// 实体主页近期行动区与沉浸详情内容锚点共用同一 typed 读面。
final gatheringDetailSocialProofReaderProvider =
    Provider<ContentGatheringSocialProofReader>(
      (ref) => ref
          .watch(
            _contentPostReaderFacetsProvider(AppUiSurfaces.gatheringDetail),
          )
          .gatheringSocialProof,
    );

final homepageDetailSocialProofReaderProvider =
    Provider<ContentGatheringSocialProofReader>(
      (ref) => ref
          .watch(_contentPostReaderFacetsProvider(AppUiSurfaces.homepageDetail))
          .gatheringSocialProof,
    );

final workBrowserSocialProofReaderProvider =
    Provider<ContentGatheringSocialProofReader>(
      (ref) => ref
          .watch(_contentPostReaderFacetsProvider(AppUiSurfaces.workBrowser))
          .gatheringSocialProof,
    );

/// 我的主页影响力卡「成行力」creator 锚点计数（REQ-008 / OPEN-007 收口）。
final profileHomeSocialProofReaderProvider =
    Provider<ContentGatheringSocialProofReader>(
      (ref) => ref
          .watch(_contentPostReaderFacetsProvider(AppUiSurfaces.profileHome))
          .gatheringSocialProof,
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
  final projectedPersonaId = persona?.personaId.trim() ?? '';
  final authenticatedPersonaId = ref
      .read(resolvedActivePersonaIdProvider)
      .trim();
  final personaId = projectedPersonaId.isNotEmpty
      ? projectedPersonaId
      : authenticatedPersonaId;
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
