import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart'
    as phase_owner;
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/execution_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';

/// Execution: runs through the local phase execution owner.
class ExecutionPhase implements Phase {
  ExecutionPhase(
    phase_owner.LocalPhaseExecutionOwner owner, {
    ExecutionRunner? runner,
  }) : _runner =
           runner ??
           ExecutionRunner(
             executeBridgeFromState: owner.executeBridgeFromState,
           );

  final ExecutionRunner _runner;

  @override
  String get phaseId => 'execution';

  @override
  Future<PhaseOutput> run(PhaseInput input) => _runner.run(input);
}
