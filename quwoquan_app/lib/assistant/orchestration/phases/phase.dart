import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';

/// Base interface for agent loop phases.
abstract class Phase {
  String get phaseId;

  Future<PhaseOutput> run(PhaseInput input);
}
