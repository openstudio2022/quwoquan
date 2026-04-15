import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// Typed replacement for `LocalPhaseExecutionOwner.synthesizeDraftBridge`.
///
/// During the transition period this delegates to the owner's bridge method.
/// Post-migration the owner dependency will be removed and the core logic
/// (synthesis template assembly, LLM streaming call, draft construction)
/// will live here directly.
class SynthesisPipeline {
  const SynthesisPipeline({required LocalPhaseExecutionOwner owner})
      : _owner = owner;

  final LocalPhaseExecutionOwner _owner;

  // ASSISTANT_WEAK_TYPE: EXTENSION_MAP — transitional, will migrate to ExecutionPhaseSnapshot
  Future<SynthesisDraft> buildDraft(
    AssistantRunRequest request, {
    required Map<String, dynamic> executionSnapshot,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) {
    return _owner.synthesizeDraftBridge(
      request,
      executionSnapshot: executionSnapshot,
      onTraceEvent: onTraceEvent,
    );
  }
}
