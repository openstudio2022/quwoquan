import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart'
    as phase_owner;
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/finalize_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

/// Finalize: persist session, learning, return response.
class FinalizePhase implements Phase {
  /// Preferred pipeline-based constructor.
  const FinalizePhase({required FinalizeRunner runner}) : _runner = runner;

  /// Current constructor for backward compatibility with tests.
  @Deprecated('Use the named-parameter pipeline constructor')
  FinalizePhase.fromOwner(
    phase_owner.LocalPhaseExecutionOwner owner, {
    FinalizeRunner? runner,
  }) : _runner = runner ?? owner.buildFinalizeRunner();

  final FinalizeRunner _runner;

  @override
  String get phaseId => 'finalize';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final pendingResponse = input.state.pendingResponse;
    if (pendingResponse == null) {
      return PhaseOutput(state: input.state);
    }
    final snapshot = input.state.executionPhaseSnapshot;
    final hasExecution = snapshot is ExecutionPhaseSuccess;
    if (!hasExecution) {
      return PhaseOutput(state: input.state, response: pendingResponse);
    }
    final finalizedResponse = await _runner.finalize(
      coerceAssistantRunRequest(input.request),
      executionSnapshot: snapshot,
      response: pendingResponse,
    );
    return PhaseOutput(state: input.state, response: finalizedResponse);
  }
}
