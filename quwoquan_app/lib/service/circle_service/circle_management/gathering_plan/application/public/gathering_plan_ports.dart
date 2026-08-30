import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';

/// GatheringPlan 对外只暴露「按 Gathering 读取当前计划的看板投影」这一个能力。
///
/// Plan 是 Gathering 的可选伴生对象：读取失败或未创建都必须由投影自身的
/// capability reason 表达，而不是抛给调用方去猜。因此本 port 返回值不可空、
/// 也不抛业务异常——调用方拿到的永远是一份可直接渲染的切片。
abstract interface class GatheringBoardPlanReader {
  Future<GatheringBoardPlanSlice> loadPlan(String gatheringId);
}

/// 远端读取面：只做调用与 wire 解码，传输失败如实抛出。
///
/// 与 [GatheringBoardPlanReader] 的区别是它**会**抛异常；把失败翻译成
/// capability reason 是 `GatheringBoardPlanReaderFacade` 的职责。
final class GatheringPlanRemoteReadResult {
  const GatheringPlanRemoteReadResult({
    required this.planId,
    required this.gatheringId,
    required this.planVersion,
    required this.currentRevisionId,
    required this.currentRevisionNumber,
    required this.currentRevisionDigest,
    required this.board,
  });

  final String planId;
  final String gatheringId;
  final int planVersion;
  final String currentRevisionId;
  final int currentRevisionNumber;
  final String currentRevisionDigest;
  final GatheringBoardPlanSlice board;
}

/// 一条 immutable PlanRevision 的 App 只读投影。
final class GatheringPlanRevisionRemoteReadResult {
  const GatheringPlanRevisionRemoteReadResult({
    required this.revisionId,
    required this.revisionNumber,
    required this.revisionDigest,
    required this.committedByPersonaId,
    required this.committedAt,
    required this.board,
  });

  final String revisionId;
  final int revisionNumber;
  final String revisionDigest;
  final String committedByPersonaId;
  final DateTime committedAt;
  final GatheringBoardPlanSlice board;
}

/// stable cursor 历史页；不向 App 泄露 cloud wire 类型。
final class GatheringPlanRevisionPageRemoteReadResult {
  const GatheringPlanRevisionPageRemoteReadResult({
    required this.items,
    required this.nextCursor,
    required this.hasMore,
  });

  final List<GatheringPlanRevisionRemoteReadResult> items;
  final String? nextCursor;
  final bool hasMore;
}

abstract interface class GatheringPlanBoardSliceSource {
  Future<GatheringBoardPlanSlice> readPlan(String gatheringId);
}
