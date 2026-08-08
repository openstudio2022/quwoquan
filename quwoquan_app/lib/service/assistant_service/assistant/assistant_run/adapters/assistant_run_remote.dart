import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantRunInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// AssistantRun generated-client adapter。
final class AssistantRunGeneratedAdapter
    implements
        AssistantAnswerRunProcessCommandWriter,
        AssistantRunIntentProcessCommandWriter,
        AssistantRunProcessQuery,
        AssistantRunEventStream,
        AssistantCreationRunProcessCommandWriter {
  const AssistantRunGeneratedAdapter({
    required this.client,
    required this.invocationContext,
    required this.presentationCapabilities,
    this.networkSurface = false,
  });

  final GeneratedCloudOperationClient client;
  final AssistantRunInvocationContextFactory invocationContext;
  final AssistantPresentationCapabilitySnapshotFactory presentationCapabilities;
  final bool networkSurface;

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    final run = await startAssistantRunIntent(
      sessionId: sessionId,
      clientRequestId: clientRequestId,
      intent: AssistantRunIntent(
        kind: AssistantRunIntentKind.answer,
        answer: AssistantAnswerRunIntent(text: text.trim()),
      ),
      contextSnapshot: intersectionEvidenceRefs.isEmpty
          ? null
          : AssistantContextSnapshot(
              intersectionEvidenceRefs:
                  List<AssistantIntersectionEvidenceRef>.unmodifiable(
                    intersectionEvidenceRefs,
                  ),
            ),
    );
    _debugAssistantRun(
      'run decoded sessionId=${run.sessionId} runId=${run.runId} traceId=${run.traceId}',
    );
    return run;
  }

  @override
  Future<AssistantRunEnvelopeWire> startCreationRun({
    required String sessionId,
    required String clientRequestId,
    required AssistantCreationRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  }) {
    return startAssistantRunIntent(
      sessionId: sessionId,
      clientRequestId: clientRequestId,
      intent: AssistantRunIntent(
        kind: AssistantRunIntentKind.creationAssistance,
        creationAssistance: intent,
      ),
      contextSnapshot: contextSnapshot,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRunIntent({
    required String sessionId,
    required String clientRequestId,
    required AssistantRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    final requestId = _requireRunRequestId(
      clientRequestId,
      AppCloudOperationIds.assistantAssistantRunStartAssistantRun,
    );
    final surfacePolicy = networkSurface
        ? AssistantPresentationSurfacePolicy.network
        : AssistantPresentationSurfacePolicy.personal;
    final capabilitySnapshot = presentationCapabilities(surfacePolicy);
    if (capabilitySnapshot.surfacePolicy != surfacePolicy) {
      throw StateError(
        'Assistant presentation capability factory returned the wrong surface policy',
      );
    }
    return client.assistantAssistantRunStartAssistantRun(
      AssistantStartRunRequest(
        sessionId: sessionId,
        clientRequestId: requestId,
        intent: intent,
        contextSnapshot: contextSnapshot,
        surfaceCapabilities: AssistantSurfaceCapabilities(
          surfaceId: networkSurface
              ? AppUiSurfaces.globalSearchNetworkResults.id
              : AppUiSurfaces.personalAssistantDialog.id,
          supportedNodeKinds: capabilitySnapshot.supportedNodeWireNames,
          supportedActionIntents: capabilitySnapshot.supportedActionIntents,
          viewportClass: capabilitySnapshot.viewportClass.wireName,
          platform: capabilitySnapshot.platform,
          theme: capabilitySnapshot.themeWireName,
          textScale: capabilitySnapshot.textScale,
          reducedMotion: capabilitySnapshot.reducedMotion,
          offline: capabilitySnapshot.offline,
        ),
      ),
      context: invocationContext(
        AssistantRequestPageIds.startAssistantRun,
        idempotencyKey: requestId,
        networkSurface: networkSurface,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({required String runId}) {
    final normalizedRunId = _requireRunId(
      runId,
      AppCloudOperationIds.assistantAssistantRunGetAssistantRun,
    );
    return client.assistantAssistantRunGetAssistantRun(
      AssistantRunByIdQuery(runId: normalizedRunId),
      context: invocationContext(
        AssistantRequestPageIds.getAssistantRun,
        networkSurface: networkSurface,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    final requestId = _requireRunRequestId(
      commandRequestId,
      AppCloudOperationIds.assistantAssistantRunCancelAssistantRun,
    );
    return client.assistantAssistantRunCancelAssistantRun(
      AssistantRunCommandRequest(runId: runId),
      context: invocationContext(
        AssistantRequestPageIds.cancelAssistantRun,
        idempotencyKey: requestId,
        networkSurface: networkSurface,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  }) {
    final requestId = _requireRunRequestId(
      commandRequestId,
      AppCloudOperationIds.assistantAssistantRunPauseAssistantRun,
    );
    return client.assistantAssistantRunPauseAssistantRun(
      AssistantPauseRunRequest(
        runId: runId,
        reason: reason.trim().isEmpty ? null : reason.trim(),
      ),
      context: invocationContext(
        AssistantRequestPageIds.pauseAssistantRun,
        idempotencyKey: requestId,
        networkSurface: networkSurface,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    final requestId = _requireRunRequestId(
      commandRequestId,
      AppCloudOperationIds.assistantAssistantRunResumeAssistantRun,
    );
    return client.assistantAssistantRunResumeAssistantRun(
      AssistantRunCommandRequest(runId: runId),
      context: invocationContext(
        AssistantRequestPageIds.resumeAssistantRun,
        idempotencyKey: requestId,
        networkSurface: networkSurface,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) {
    final requestId = _requireRunRequestId(
      commandRequestId,
      AppCloudOperationIds.assistantAssistantRunSteerAssistantRun,
    );
    return client.assistantAssistantRunSteerAssistantRun(
      AssistantSteerRunRequest(runId: runId, instruction: instruction),
      context: invocationContext(
        AssistantRequestPageIds.steerAssistantRun,
        idempotencyKey: requestId,
        networkSurface: networkSurface,
      ),
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) {
    final normalizedRunId = _requireRunId(
      runId,
      AppCloudOperationIds.assistantAssistantRunStreamAssistantRunEvents,
    );
    return client.assistantAssistantRunStreamAssistantRunEvents(
      AssistantRunEventStreamQuery(
        runId: normalizedRunId,
        resumeToken: lastEventId.trim().isEmpty ? null : lastEventId.trim(),
      ),
      context: invocationContext(
        AssistantRequestPageIds.streamAssistantRunEvents,
        networkSurface: networkSurface,
      ),
    );
  }
}

/// 只经 approved generated graph 暴露 Run 控制、工具批准与设备回执能力。
///
/// production composition 不调用已退休的 ContinueAssistantToolUse，也不绕过
/// generated client 拼装请求。
final class AssistantRunHandoffControlAdapter
    implements AssistantRunControlFacet {
  const AssistantRunHandoffControlAdapter({required this.generated});

  final AssistantRunGeneratedAdapter generated;

  @override
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  }) {
    return generated.pauseAssistantRun(
      runId: runId,
      commandRequestId: commandRequestId,
      reason: reason,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return generated.resumeAssistantRun(
      runId: runId,
      commandRequestId: commandRequestId,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) {
    return generated.steerAssistantRun(
      runId: runId,
      commandRequestId: commandRequestId,
      instruction: instruction,
    );
  }

  @override
  Future<AssistantToolApprovalResult> approveAssistantToolUse({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  }) {
    final requestId = _requireRunRequestId(
      commandRequestId,
      AppCloudOperationIds.assistantAssistantRunApproveAssistantToolUse,
    );
    return generated.client.assistantAssistantRunApproveAssistantToolUse(
      AssistantApproveToolUseRequest(
        runId: runId,
        toolInvocationId: toolInvocationId,
        decision: decision,
        approvalPermit: approvalPermit,
        installationId: installationId,
        deviceId: deviceId,
      ),
      context: generated.invocationContext(
        AssistantRequestPageIds.approveAssistantToolUse,
        idempotencyKey: requestId,
        networkSurface: generated.networkSurface,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> submitDeviceActionReceipt({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required AssistantDeviceActionExecutionReceipt receipt,
  }) {
    final requestId = _requireRunRequestId(
      commandRequestId,
      AppCloudOperationIds.assistantAssistantRunSubmitDeviceActionReceipt,
    );
    return generated.client.assistantAssistantRunSubmitDeviceActionReceipt(
      AssistantSubmitDeviceActionReceiptRequest(
        runId: runId,
        toolInvocationId: toolInvocationId,
        receipt: receipt,
      ),
      context: generated.invocationContext(
        AssistantRequestPageIds.submitDeviceActionReceipt,
        idempotencyKey: requestId,
        networkSurface: generated.networkSurface,
      ),
    );
  }
}

String _requireRunRequestId(String value, String operation) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(
      value,
      'clientRequestId',
      '$operation requires a stable client request identity',
    );
  }
  return normalized;
}

String _requireRunId(String value, String operation) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(
      value,
      'runId',
      '$operation requires a canonical run identity',
    );
  }
  return normalized;
}

void _debugAssistantRun(String message) {
  if (!kDebugMode && !kProfileMode) {
    return;
  }
  debugPrint('[assistant-run] $message');
}
