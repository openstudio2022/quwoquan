// 用户文案应迁至 prompt asset / tool metadata，见 canonical_truth_sources.md。禁止新增。
import 'package:quwoquan_app/assistant/conversation/explainability/default_processing_copy_bank.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/problem_framer.dart';

class NarrativeEngine {
  const NarrativeEngine();

  String heuristicReasoning({
    required ProblemFrame frame,
    required bool hasReferences,
  }) {
    return DefaultProcessingCopyBank.runtimeFallbackDisabledReason;
  }

  String fallbackReason({
    required ProblemFrame frame,
    required List<String> missingCriticalSlots,
    required bool hasEvidence,
    required bool evidenceSafe,
    required bool hasToolError,
  }) {
    return DefaultProcessingCopyBank.runtimeFallbackDisabledReason;
  }

  String askUserPrompt({required String slotId, required ProblemFrame frame}) {
    return '';
  }

  List<String> planningFramework(ProblemFrame frame) {
    return const <String>[];
  }
}
