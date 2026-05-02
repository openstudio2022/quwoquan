import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart'
    as phase_owner;
import 'package:quwoquan_app/assistant/orchestration/pipelines/execution_pipeline.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/execution_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';

/// Execution: runs through the execution pipeline.
class ExecutionPhase implements Phase {
  /// Preferred pipeline-based constructor.
  ExecutionPhase(ExecutionPipeline pipeline, {ExecutionRunner? runner})
    : _runner =
          runner ?? ExecutionRunner(executeBridgeFromState: pipeline.execute);

  /// Current constructor for backward compatibility with tests.
  @Deprecated('Use the pipeline constructor')
  ExecutionPhase.fromOwner(
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
