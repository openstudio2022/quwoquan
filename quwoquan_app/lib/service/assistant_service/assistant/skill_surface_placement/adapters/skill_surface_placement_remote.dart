import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/application/skill_surface_placement_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantSkillSurfacePlacementInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// SkillSurfacePlacement 的 production generated-client adapter。
final class RemoteAssistantSkillSurfacePlacementAdapter
    implements AssistantSkillSurfacePlacementFacet {
  const RemoteAssistantSkillSurfacePlacementAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantSkillSurfacePlacementInvocationContextFactory
  invocationContext;

  @override
  Future<SkillSurfacePlacement> getSkillSurfacePlacement({
    required SkillSurfaceKind surfaceKind,
    required String surfaceId,
  }) {
    return client.assistantSkillSurfacePlacementGetSkillSurfacePlacement(
      GetSkillSurfacePlacementQuery(
        surfaceKind: surfaceKind,
        surfaceId: surfaceId,
      ),
      context: invocationContext(
        AssistantRequestPageIds.getSkillSurfacePlacement,
      ),
    );
  }

  @override
  Future<SkillSurfacePlacement> putSkillSurfacePlacement({
    required SkillSurfaceKind surfaceKind,
    required String surfaceId,
    required SkillSurfacePlacementPolicy policy,
    required List<String> disabledSkillIds,
    required SkillSurfacePlacementStatus status,
    required int expectedRevision,
    required String clientRequestId,
  }) {
    return client.assistantSkillSurfacePlacementPutSkillSurfacePlacement(
      PutSkillSurfacePlacementRequest(
        surfaceKind: surfaceKind,
        surfaceId: surfaceId,
        policy: policy,
        disabledSkillIds: disabledSkillIds,
        status: status,
        expectedRevision: expectedRevision,
      ),
      context: invocationContext(
        AssistantRequestPageIds.putSkillSurfacePlacement,
        idempotencyKey: clientRequestId,
      ),
    );
  }
}
