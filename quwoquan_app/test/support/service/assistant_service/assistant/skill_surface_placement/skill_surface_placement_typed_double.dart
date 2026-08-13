import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/application/skill_surface_placement_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// SkillSurfacePlacement 的对象级 typed in-memory double：
/// 每个 surface 最多一条 placement，PUT 走 expectedRevision CAS。
class InMemoryAssistantSkillSurfacePlacementFacet
    implements AssistantSkillSurfacePlacementFacet {
  InMemoryAssistantSkillSurfacePlacementFacet({
    Iterable<SkillSurfacePlacement> placements =
        const <SkillSurfacePlacement>[],
  }) {
    for (final placement in placements) {
      _placements[_key(placement.surfaceKind, placement.surfaceId)] = placement;
    }
  }

  final Map<String, SkillSurfacePlacement> _placements =
      <String, SkillSurfacePlacement>{};
  final List<({String clientRequestId, SkillSurfacePlacement saved})>
  putReceipts = <({String clientRequestId, SkillSurfacePlacement saved})>[];

  static String _key(SkillSurfaceKind surfaceKind, String surfaceId) =>
      '${surfaceKind.wireName}:$surfaceId';

  @override
  Future<SkillSurfacePlacement> getSkillSurfacePlacement({
    required SkillSurfaceKind surfaceKind,
    required String surfaceId,
  }) async {
    final placement = _placements[_key(surfaceKind, surfaceId)];
    if (placement == null) {
      throw StateError('skill surface placement not found');
    }
    return placement;
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
  }) async {
    final key = _key(surfaceKind, surfaceId);
    final current = _placements[key];
    if ((current?.revision ?? 0) != expectedRevision) {
      throw StateError('skill surface placement revision conflict');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final next = SkillSurfacePlacement(
      id: current?.id ?? 'placement:$key',
      surfaceKind: surfaceKind,
      surfaceId: surfaceId,
      policy: policy,
      disabledSkillIds: List<String>.unmodifiable(disabledSkillIds),
      status: status,
      revision: expectedRevision + 1,
      createdAt: current?.createdAt ?? now,
      updatedAt: now,
    );
    _placements[key] = next;
    putReceipts.add((clientRequestId: clientRequestId, saved: next));
    return next;
  }
}
