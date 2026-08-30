import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/adapters/gathering_plan_wire_codec.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/application/public/gathering_plan_ports.dart';

/// 把远端读取失败降级为看板可渲染切片的唯一位置。
///
/// 远端 facet 只做 operation 调用与 wire 解码并如实抛出传输失败；未创建 /
/// 无权限 / 暂不可用这三种 capability reason 是看板的展示策略，由这里单点
/// 翻译，而不是让每个调用方各写一份降级分支。
final class GatheringBoardPlanReaderFacade implements GatheringBoardPlanReader {
  const GatheringBoardPlanReaderFacade(this._source);

  final GatheringPlanBoardSliceSource _source;

  @override
  Future<GatheringBoardPlanSlice> loadPlan(String gatheringId) async {
    try {
      return await _source.readPlan(gatheringId);
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
