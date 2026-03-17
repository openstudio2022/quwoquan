import 'package:quwoquan_app/assistant/conversation/orchestration/agent_loop.dart'
    as legacy_agent;
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/execution_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';

/// Execution: runs through a typed phase-side runner backed by the legacy bridge.
class ExecutionPhase implements Phase {
  ExecutionPhase(
    legacy_agent.PersonalAssistantAgentLoop legacy, {
    ExecutionRunner? runner,
  }) : _runner =
           runner ??
           ExecutionRunner(
             executeBridgeFromState: legacy.executeBridgeFromState,
           );

  final ExecutionRunner _runner;

  @override
  String get phaseId => 'execution';

  @override
  Future<PhaseOutput> run(PhaseInput input) => _runner.run(input);
}
