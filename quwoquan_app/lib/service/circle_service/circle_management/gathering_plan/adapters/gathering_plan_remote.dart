import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/adapters/gathering_plan_wire_codec.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/application/public/gathering_plan_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

/// 每次 operation 调用都要带自己的 invocation context，由装配方注入。
typedef GatheringPlanInvocationContextFactory =
    cloud.CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// GatheringPlan 的唯一 production 读取面。
///
/// 只做 operation 调用与 wire 解码；传输失败如实抛出，由
/// `GatheringBoardPlanReaderFacade` 翻译成看板的 capability reason。
final class RemoteGatheringPlanFacet implements GatheringPlanBoardSliceSource {
  const RemoteGatheringPlanFacet({
    required this.client,
    required this.invocationContext,
  });

  final cloud.GeneratedCloudOperationClient client;
  final GatheringPlanInvocationContextFactory invocationContext;

  @override
  Future<GatheringBoardPlanSlice> readPlan(String gatheringId) async {
    return (await readPlanResult(gatheringId)).board;
  }

  Future<GatheringPlanRemoteReadResult> readPlanResult(
    String gatheringId,
  ) async {
    final wire = await client.circleGatheringPlanGetGatheringPlan(
      cloud.GatheringPlanByGatheringQuery(gatheringId: gatheringId),
      context: invocationContext(CircleRequestPageIds.getGatheringPlan),
    );
    return GatheringPlanRemoteReadResult(
      planId: wire.id,
      gatheringId: wire.gatheringId,
      planVersion: wire.version,
      currentRevisionId: wire.currentRevisionId,
      currentRevisionNumber: wire.currentRevisionNumber,
      currentRevisionDigest: wire.currentRevisionDigest,
      board: gatheringBoardPlanFromWire(wire),
    );
  }

  /// 按 canonical keyset cursor 读取 immutable revision history。
  Future<GatheringPlanRevisionPageRemoteReadResult> listPlanRevisions(
    String planId, {
    String? cursor,
    int? limit,
  }) async {
    final wire = await client.circleGatheringPlanListGatheringPlanRevisions(
      cloud.GatheringPlanRevisionPageQuery(
        planId: planId,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(
        CircleRequestPageIds.listGatheringPlanRevisions,
      ),
    );
    return GatheringPlanRevisionPageRemoteReadResult(
      items: wire.items
          .map(
            (revision) => GatheringPlanRevisionRemoteReadResult(
              revisionId: revision.revisionId,
              revisionNumber: revision.revisionNumber,
              revisionDigest: revision.revisionDigest,
              committedByPersonaId: revision.committedByPersonaId,
              committedAt: revision.committedAt,
              board: gatheringBoardPlanRevisionFromWire(revision),
            ),
          )
          .toList(growable: false),
      nextCursor: wire.nextCursor,
      hasMore: wire.hasMore,
    );
  }
}
