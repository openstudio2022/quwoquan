import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';

class AssistantPipelineSynthesisAssessment {
  const AssistantPipelineSynthesisAssessment({
    required this.synthesisReadiness,
    required this.evidenceLedger,
    required this.evidenceEvaluation,
  });

  final SynthesisReadinessResult synthesisReadiness;
  final List<EvidenceLedgerEntry> evidenceLedger;
  final EvidenceEvaluationResult evidenceEvaluation;
}
