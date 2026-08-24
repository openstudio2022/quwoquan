import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
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
/// 计划读不到不得让整个看板失败：未创建 / 无权限 / 其他失败分别落到独立的
/// capability reason，由看板 Plan 区自己表达，不与活动主体事实混淆。
final class RemoteGatheringPlanFacet implements GatheringBoardPlanReader {
  const RemoteGatheringPlanFacet({
    required this.client,
    required this.invocationContext,
  });

  final cloud.GeneratedCloudOperationClient client;
  final GatheringPlanInvocationContextFactory invocationContext;

  @override
  Future<GatheringBoardPlanSlice> loadPlan(String gatheringId) async {
    try {
      final wire = await client.circleGatheringPlanGetGatheringPlan(
        cloud.GatheringPlanByGatheringQuery(gatheringId: gatheringId),
        context: invocationContext(CircleRequestPageIds.getGatheringPlan),
      );
      return gatheringBoardPlanFromWire(wire);
    } on CloudException catch (error) {
      return gatheringBoardPlanUnavailable(
        switch (error.type) {
          CloudErrorType.notFound =>
            GatheringBoardCapabilityUnavailableReason.notConfigured,
          CloudErrorType.forbidden =>
            GatheringBoardCapabilityUnavailableReason.permissionDenied,
          _ => GatheringBoardCapabilityUnavailableReason.temporarilyUnavailable,
        },
        switch (error.type) {
          CloudErrorType.notFound => ChatText.boardPlanNotConfigured,
          CloudErrorType.forbidden => ChatText.boardPlanPermissionDenied,
          _ => ChatText.boardPlanUnavailable,
        },
      );
    }
  }
}
