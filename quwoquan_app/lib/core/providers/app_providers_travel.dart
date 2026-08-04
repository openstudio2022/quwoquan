import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_guide_assignment/application/trip_guide_assignment_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_guide_assignment/application/trip_guide_assignment_facet.dart';
import 'package:quwoquan_app/application/travel/trip_collaboration_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_collaboration_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_content_link/application/trip_content_link_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_content_link/application/trip_content_link_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/application/trip_journey_query.dart';
import 'package:quwoquan_app/travel/travel/trip_moment/application/trip_moment_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_moment/application/trip_moment_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_creation_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_creation_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_directory.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_share_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_share_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_share_publication_continuation.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_template/application/trip_template_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_template/application/trip_template_facet.dart';
import 'package:quwoquan_app/application/content/post/post_publication_continuation_registry.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/di/travel_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/core/providers/app_providers_app_state.dart';
import 'package:quwoquan_app/core/providers/app_providers_chat_search.dart';
import 'package:quwoquan_app/core/providers/app_providers_operations.dart';
final tripCollaborationFacetProvider = Provider<TripCollaborationFacet>((ref) {
  return TravelProductionComposition.tripCollaborationFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripCollaborationCoordinatorProvider =
    Provider<TripCollaborationCoordinator>(
      (ref) => TripCollaborationCoordinator(
        ref.watch(tripCollaborationFacetProvider),
        (scope) => 'travel-$scope-${const Uuid().v4()}',
      ),
    );

final tripContentLinkFacetProvider = Provider<TripContentLinkFacet>((ref) {
  return TravelProductionComposition.tripContentLinkFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripContentLinkCoordinatorProvider = Provider<TripContentLinkCoordinator>(
  (ref) => TripContentLinkCoordinator(
    ref.watch(tripContentLinkFacetProvider),
    (scope) => 'travel-content-link-$scope-${const Uuid().v4()}',
  ),
);

final postPublicationContinuationRegistryProvider =
    Provider<PostPublicationContinuationRegistry>((ref) {
      return PostPublicationContinuationRegistry(<
        PostPublicationContinuationHandler
      >[
        TripSharePublicationContinuationHandler(
          shareFacet: ref.watch(tripShareFacetProvider),
          journeyLoader: ref.watch(tripJourneyLoaderProvider),
          contentLinkCoordinator: ref.watch(tripContentLinkCoordinatorProvider),
        ),
      ]);
    });

final tripGuideAssignmentFacetProvider = Provider<TripGuideAssignmentFacet>((
  ref,
) {
  return TravelProductionComposition.tripGuideAssignmentFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripGuideAssignmentCoordinatorProvider =
    Provider<TripGuideAssignmentCoordinator>((ref) {
      return TripGuideAssignmentCoordinator(
        facet: ref.watch(tripGuideAssignmentFacetProvider),
        idempotencyKeyFactory: () => 'travel-guide-${const Uuid().v4()}',
        taskKeyFactory: () => 'guide-task-${const Uuid().v4()}',
      );
    });

/// 当前 Persona 自有 Trip 列表。分页状态由页面持有，Remote 仅执行 canonical
/// keyset query，避免把用户的 Trip 真相复制到 App 本地状态仓库。
final tripPlanDirectoryProvider = Provider<TripPlanDirectory>((ref) {
  return TravelProductionComposition.tripPlanDirectory(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (AppUiSurface surface, String clientPageId) =>
        _travelOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
  );
});

final tripPlanCreationFacetProvider = Provider<TripPlanCreationFacet>((ref) {
  return TravelProductionComposition.tripPlanCreationFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripPlanCreationCoordinatorProvider =
    Provider<TripPlanCreationCoordinator>(
      (ref) => TripPlanCreationCoordinator(
        ref.watch(tripPlanCreationFacetProvider),
        () => 'travel-trip-${const Uuid().v4()}',
      ),
    );

final tripPlanRevisionFacetProvider = Provider<TripPlanRevisionFacet>((ref) {
  return TravelProductionComposition.tripPlanRevisionFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripPlanRevisionCoordinatorProvider =
    Provider<TripPlanRevisionCoordinator>(
      (ref) => TripPlanRevisionCoordinator(
        ref.watch(tripPlanRevisionFacetProvider),
        () => 'travel-revision-${const Uuid().v4()}',
      ),
    );

final tripMomentFacetProvider = Provider<TripMomentFacet>((ref) {
  return TravelProductionComposition.tripMomentFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripMomentCoordinatorProvider = Provider<TripMomentCoordinator>((ref) {
  return TripMomentCoordinator(
    facet: ref.watch(tripMomentFacetProvider),
    idempotencyKeyFactory: () => 'travel-moment-${const Uuid().v4()}',
  );
});

/// Travel production read graph：唯一 generated-client adapter，经应用层 loader
/// 并发组合当前计划、时间线、地图、成员、随拍、内容、Placement 与导游任务。
final tripJourneyQueryProvider = Provider<TripJourneyQuery>((ref) {
  return TravelProductionComposition.travelJourneyQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    surface: AppUiSurfaces.travelTimeline,
    invocationContext: (AppUiSurface surface, String clientPageId) =>
        _travelOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
  );
});

final tripJourneyLoaderProvider = Provider<TripJourneyLoader>((ref) {
  return TripJourneyLoader(ref.watch(tripJourneyQueryProvider));
});

final tripJourneySnapshotProvider = FutureProvider.autoDispose
    .family<TripJourneySnapshot, String>((ref, tripId) {
      return ref.watch(tripJourneyLoaderProvider).load(tripId);
    });

final tripGuideAssigneeLabelsProvider = FutureProvider.autoDispose
    .family<Map<String, String>, String>((ref, tripId) async {
      final snapshot = await ref.watch(
        tripJourneySnapshotProvider(tripId).future,
      );
      final personaIds = <String>{
        for (final membership in snapshot.memberships.memberships)
          if (membership.state == TripMembershipState.active)
            membership.personaId,
        for (final assignment in snapshot.guideAssignments.assignments)
          assignment.assigneePersonaId,
      };
      final query = ref.watch(
        personaQueryProvider(AppUiSurfaces.travelTimeline),
      );
      final entries = await Future.wait(
        personaIds.map((personaId) async {
          final profile = await query.getPersonaProfile(personaId);
          final displayName = profile.displayName.trim().isNotEmpty
              ? profile.displayName.trim()
              : profile.userHandle.trim();
          if (displayName.isEmpty) {
            throw StateError('Trip member has no public display label');
          }
          return MapEntry<String, String>(personaId, displayName);
        }),
      );
      return Map<String, String>.unmodifiable(Map.fromEntries(entries));
    });

final tripMapProvider = FutureProvider.autoDispose.family<TripMapView, String>((
  ref,
  tripId,
) {
  final query = TravelProductionComposition.travelJourneyQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    surface: AppUiSurfaces.travelMap,
    invocationContext: (AppUiSurface surface, String clientPageId) =>
        _travelOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
  );
  return query.getMap(tripId);
});

final tripShareFacetProvider = Provider<TripShareFacet>((ref) {
  return TravelProductionComposition.tripShareFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripShareCoordinatorProvider = Provider<TripShareCoordinator>((ref) {
  return TripShareCoordinator(
    facet: ref.watch(tripShareFacetProvider),
    idempotencyKeyFactory: () => 'travel-share-${const Uuid().v4()}',
  );
});

final tripShareSnapshotProvider = FutureProvider.autoDispose
    .family<TripShareSnapshot, String>((ref, snapshotId) {
      return ref.watch(tripShareFacetProvider).getSnapshot(snapshotId);
    });

final tripTemplateFacetProvider = Provider<TripTemplateFacet>((ref) {
  return TravelProductionComposition.tripTemplateFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (AppUiSurface surface, String clientPageId, {String? idempotencyKey}) =>
            _travelOperationInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
});

final tripTemplateCoordinatorProvider = Provider<TripTemplateCoordinator>((
  ref,
) {
  return TripTemplateCoordinator(
    facet: ref.watch(tripTemplateFacetProvider),
    itemIdFactory: (_) => 'template-item-${const Uuid().v4()}',
    idempotencyKeyFactory: () => 'travel-template-${const Uuid().v4()}',
  );
});

final tripPlanTemplatesProvider = FutureProvider.autoDispose((ref) {
  return ref.watch(tripTemplateFacetProvider).listTemplates();
});

CloudOperationInvocationContext _travelOperationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  String? idempotencyKey,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    idempotencyKey: idempotencyKey,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}
