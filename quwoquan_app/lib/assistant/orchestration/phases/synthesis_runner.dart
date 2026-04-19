import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

typedef BuildSynthesisDraft =
    Future<SynthesisDraft> Function(
      AssistantRunRequest request, {
      required ExecutionPhaseSnapshot executionSnapshot,
      void Function(AssistantTraceEvent event)? onTraceEvent,
    });

typedef MaterializeSynthesisDraft =
    Future<AssistantRunResponse> Function(
      AssistantRunRequest request, {
      required SynthesisDraft draft,
      void Function(AssistantTraceEvent event)? onTraceEvent,
    });

class SynthesisRunner {
  const SynthesisRunner({
    required this.buildDraft,
    required this.materialize,
  });

  final BuildSynthesisDraft buildDraft;
  final MaterializeSynthesisDraft materialize;

  Future<AssistantRunResponse> synthesize(
    AssistantRunRequest request, {
    required ExecutionPhaseSnapshot executionSnapshot,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final draft = await buildDraft(
      request,
      executionSnapshot: executionSnapshot,
      onTraceEvent: onTraceEvent,
    );
    return materialize(
      request,
      draft: draft,
      onTraceEvent: onTraceEvent,
    );
  }
}
