import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantRun answer intent 写端口。
abstract class AssistantAnswerRunCommandWriter {
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

/// AssistantRun generated tagged-union intent 的对象级写端口。
abstract class AssistantRunIntentCommandWriter {
  Future<AssistantRunEnvelopeWire> startAssistantRunIntent({
    required String sessionId,
    required String clientRequestId,
    required AssistantRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  });
}

abstract class AssistantRunQuery {
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

/// 创作辅助只创建 AssistantRun，不拥有独立执行路由。
abstract class AssistantCreationRunCommandWriter {
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
