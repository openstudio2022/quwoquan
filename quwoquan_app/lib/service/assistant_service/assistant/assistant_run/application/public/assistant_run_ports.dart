import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// AssistantRun 是 process_manager（saga）对象，端侧写面按
// `APP_PROCESS_PORT_NAMING` 使用 `*ProcessCommandWriter`、读面使用
// `*ProcessQuery`，与聚合的 `*CommandWriter` 在类型上不可混用。
//
// 三个 start 端口落在同一条 `StartAssistantRun` 流程启动操作上（都由
// [AssistantRunIntentProcessCommandWriter.startAssistantRunIntent] 包成
// [AssistantRunIntent] tagged union 提交），但它们授予调用方的能力不同：
// 创作入口只应能发起 creationAssistance，不应顺带获得取消 Run 或发起任意
// intent 的能力。这层能力隔离在 composition 中真实生效，因此保留三个窄端口，
// 只统一为 process 命名。

/// answer intent 的 process 写端口：以纯文本发起并可取消一次 Run。
abstract class AssistantAnswerRunProcessCommandWriter {
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  });

  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  });
}

/// generated tagged-union intent 的 process 写端口。
abstract class AssistantRunIntentProcessCommandWriter {
  Future<AssistantRunEnvelopeWire> startAssistantRunIntent({
    required String sessionId,
    required String clientRequestId,
    required AssistantRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  });
}

abstract class AssistantRunProcessQuery {
  Future<AssistantRunEnvelopeWire> getAssistantRun({required String runId});
}

abstract class AssistantRunEventStream {
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  });
}

/// AssistantRun 的显式运行中控制端口。
abstract class AssistantRunControlFacet {
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  });

  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  });

  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  });

  Future<AssistantToolApprovalResult> approveAssistantToolUse({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  });

  Future<AssistantRunEnvelopeWire> submitDeviceActionReceipt({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required AssistantDeviceActionExecutionReceipt receipt,
  });
}

/// creationAssistance intent 的 process 写端口：创作辅助只创建 AssistantRun，
/// 不拥有独立执行路由，也不获得取消能力。
abstract class AssistantCreationRunProcessCommandWriter {
  Future<AssistantRunEnvelopeWire> startCreationRun({
    required String sessionId,
    required String clientRequestId,
    required AssistantCreationRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  });
}

/// 全网搜索的跨 AssistantSession/AssistantRun 显式 public facade。
abstract class AssistantSearchRunFacade {
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  });
}
