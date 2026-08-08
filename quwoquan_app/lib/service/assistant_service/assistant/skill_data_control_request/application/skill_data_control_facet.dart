import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// SkillDataControlRequest 是 process_manager（saga）对象：请求经
// pendingConfirmation -> executing -> completed/cancelled/failed 推进状态机。
// 按 `APP_PROCESS_PORT_NAMING`，端侧写面用 `*ProcessCommandWriter`、读面用
// `*ProcessQuery`，并且读写分离，避免读取端顺带获得推进流程的能力。

/// Skill 数据控制的确认型 process 写端口。创建与确认复用同一
/// [SkillDataControlRequest.requestId]；网络未知结果不得创建替代请求。
abstract class SkillDataControlProcessCommandWriter {
  Future<SkillDataControlMutationReceipt> createSkillDataControlRequest({
    required String skillId,
    required List<SkillDataControlAction> requestedActions,
    required String clientRequestId,
  });

  Future<SkillDataControlMutationReceipt> confirmSkillDataControlRequest({
    required String requestId,
    required int expectedRevision,
    required bool confirmed,
    required String clientRequestId,
  });
}

/// Skill 数据控制的 process 读端口：恢复与轮询都只读同一 requestId。
abstract class SkillDataControlProcessQuery {
  Future<SkillDataControlRequest> getSkillDataControlRequest({
    required String requestId,
  });
}
