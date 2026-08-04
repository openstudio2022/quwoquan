import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Skill 数据控制的确认型端口。创建、确认与恢复都复用同一
/// [SkillDataControlRequest.requestId]；网络未知结果不得创建替代请求。
abstract class AssistantSkillDataControlFacet {
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

  Future<SkillDataControlRequest> getSkillDataControlRequest({
    required String requestId,
  });
}
