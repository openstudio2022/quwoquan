// 用户文案应迁至 prompt asset / metadata 模板层，见 canonical_truth_sources.md。禁止新增。
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/evidence_evaluator.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/default_processing_copy_bank.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/narrative_engine.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';

class BaselineComposedAnswer {
  const BaselineComposedAnswer({
    required this.markdown,
    required this.plainText,
    required this.interpretation,
    required this.reasoning,
    this.evidence = const <Map<String, dynamic>>[],
  });

  final String markdown;
  final String plainText;
  final String interpretation;
  final String reasoning;
  final List<Map<String, dynamic>> evidence;
}

class AnswerComposer {
  const AnswerComposer({this.narrativeEngine = const NarrativeEngine()});

  final NarrativeEngine narrativeEngine;

  BaselineComposedAnswer composeHeuristicAnswer({
    required ProblemFrame frame,
    required List<Map<String, dynamic>> observations,
  }) {
    return BaselineComposedAnswer(
      markdown: '',
      plainText: '',
      interpretation: DefaultProcessingCopyBank.runtimeFallbackDisabledInterpretation,
      reasoning: narrativeEngine.heuristicReasoning(
        frame: frame,
        hasReferences: observations.isNotEmpty,
      ),
      evidence: const <Map<String, dynamic>>[],
    );
  }

  BaselineComposedAnswer composeFallbackAnswer({
    required ProblemFrame frame,
    required SlotStateSnapshot slotState,
    required EvidenceEvaluationResult evidenceEvaluation,
    required String decisionMode,
    required List<String> missingCriticalSlots,
    required List<Map<String, dynamic>> toolErrors,
  }) {
    return BaselineComposedAnswer(
      markdown: '',
      plainText: '',
      interpretation: DefaultProcessingCopyBank.runtimeFallbackDisabledInterpretation,
      reasoning: narrativeEngine.fallbackReason(
        frame: frame,
        missingCriticalSlots: missingCriticalSlots,
        hasEvidence: evidenceEvaluation.entries.isNotEmpty,
        evidenceSafe: evidenceEvaluation.passed,
        hasToolError: toolErrors.isNotEmpty,
      ),
    );
  }
}
