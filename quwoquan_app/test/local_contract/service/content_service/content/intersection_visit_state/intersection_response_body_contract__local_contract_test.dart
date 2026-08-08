// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
// readiness_case: intersection_visit_state_get_my_intersection_summary_app_local
// readiness_case: intersection_visit_state_get_object_intersections_app_local
// readiness_case: intersection_visit_state_list_my_intersections_app_local
// readiness_case: intersection_visit_state_mark_intersections_visited_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_visit_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('intersection generated response contract', () {
    late _IntersectionExecutor executor;
    late RemoteIntersectionRepository repository;

    setUp(() {
      executor = _IntersectionExecutor();
      repository = RemoteIntersectionRepository(
        client: GeneratedCloudOperationClient(executor),
        myIntersectionsInvocationContext: _context,
        objectIntersectionsInvocationContext: _context,
      );
    });

    test('metadata keeps the object/page/ack transport shapes', () {
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds
              .contentIntersectionVisitStateGetMyIntersectionSummary,
        ).responseBodyKind,
        'object',
      );
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds.contentIntersectionVisitStateListMyIntersections,
        ).responseBodyKind,
        'page',
      );
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds
              .contentIntersectionVisitStateGetObjectIntersections,
        ).responseBodyKind,
        'page',
      );
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds
              .contentIntersectionVisitStateMarkIntersectionsVisited,
        ).responseBodyKind,
        'ack',
      );
    });

    test('summary is decoded by the generated canonical owner', () async {
      final summary = await repository.getMyIntersectionSummary();
      expect(summary, isA<IntersectionInboxSummary>());
      expect(summary.totalCount, 1);
      expect(
        executor.operationId,
        AppCloudOperationIds
            .contentIntersectionVisitStateGetMyIntersectionSummary,
      );
    });

    test('my intersection page decodes generated typed items', () async {
      final items = await repository.listMyIntersections();
      expect(items, isA<List<IntersectionReason>>());
      expect(items.single.dimension, 'identity');
      expect(
        executor.operationId,
        AppCloudOperationIds.contentIntersectionVisitStateListMyIntersections,
      );
    });

    test('object intersection page decodes generated typed items', () async {
      final items = await repository.getObjectIntersections(
        objectId: 'obj_1',
        objectType: 'person',
      );
      expect(items, isA<List<IntersectionReason>>());
      expect(items.single.primaryText, '你的8位校友关注了这里');
      expect(
        executor.operationId,
        AppCloudOperationIds
            .contentIntersectionVisitStateGetObjectIntersections,
      );
    });

    test('visit command still returns void at the public port', () async {
      final writer = RemoteIntersectionVisitWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );
      await expectLater(
        writer.markIntersectionsVisited(
          dimension: IntersectionDimension.identity,
        ),
        completes,
      );
      expect(
        executor.operationId,
        AppCloudOperationIds
            .contentIntersectionVisitStateMarkIntersectionsVisited,
      );
    });
  });
}

CloudOperationInvocationContext _context(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: 'myIntersections',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
  );
}

final class _IntersectionExecutor implements CloudOperationExecutor {
  String? operationId;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationId = operation.canonicalOperationId;
    final reason = intersectionReasonFixture(
      dimension: 'identity',
      primaryText: '你的8位校友关注了这里',
      lifecycleState: 'active',
    );
    final response = switch (operation.canonicalOperationId) {
      AppCloudOperationIds
          .contentIntersectionVisitStateGetMyIntersectionSummary =>
        <String, Object?>{
          'totalCount': 1,
          'totalNewCount': 1,
          'dimensions': <Object?>[],
          'generatedAt': '2026-06-20T00:00:00Z',
          'totalStrengthenedCount': 0,
          'totalReactivatedCount': 0,
        },
      AppCloudOperationIds.contentIntersectionVisitStateListMyIntersections =>
        <String, Object?>{
          'items': <Object?>[reason.toWire()],
          'dimension': 'identity',
          'hasMore': false,
        },
      AppCloudOperationIds
          .contentIntersectionVisitStateGetObjectIntersections =>
        <String, Object?>{
          'items': <Object?>[reason.toWire()],
          'objectId': 'obj_1',
          'objectType': 'person',
        },
      AppCloudOperationIds
          .contentIntersectionVisitStateMarkIntersectionsVisited =>
        <String, Object?>{
          'dimensions': <String>['identity'],
          'status': 'visited',
        },
      _ => throw StateError(
        'Unexpected intersection operation ${operation.canonicalOperationId}',
      ),
    };
    requestEncoder();
    return responseDecoder(response);
  }
}
