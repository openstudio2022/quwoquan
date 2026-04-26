import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/tool_assessment.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/answer_gate_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_state.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';

/// Evaluates tool results post-execution to determine next action.
/// Tracks consecutive failures to break out of futile retry loops.
///
/// When [problemClass] is set, the assessor adapts its convergence
/// strategy:
///   - `realtime_info` / `simple_qa`: prefer fast convergence, skip
///     low-quality retry loops.
///   - `complex_reasoning` / `task_execution`: allow deeper search.
class ToolResultAssessor {
  ToolResultAssessor();

  int _consecutiveFailures = 0;
  int _consecutiveLowQuality = 0;
  static const int _maxConsecutiveFailures = 2;
  static const int _maxConsecutiveLowQuality = 2;

  /// Set before each run to influence convergence behavior.
  String problemClass = '';

  /// Unified answer boundary shared with synthesis and state kernel.
  AnswerBoundaryPolicy boundaryPolicy = const AnswerBoundaryPolicy();
  static const RetrievalOutcomeResolver _retrievalOutcomeResolver =
      RetrievalOutcomeResolver();
  static const AnswerGateResolver _answerGateResolver = AnswerGateResolver();

  bool get _isFastConvergence =>
      parseProblemClass(problemClass).isFastConvergence;

  void reset() {
    _consecutiveFailures = 0;
    _consecutiveLowQuality = 0;
  }

  ToolAssessment assess({
    required ReactRunState state,
    required bool lastStepSuccess,
    required Map<String, dynamic> lastObservation,
    required bool shouldReplan,
    required ReactPolicy policy,
  }) {
    final resultData =
        (lastObservation['data'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final retrievalOutcome = _retrievalOutcomeResolver.resolveFromToolResult(
      resultData: resultData,
      policy: boundaryPolicy,
    );
    final queryCount = _positiveInt(resultData['queryCount']);
    final referenceCount = retrievalOutcome.referenceCount;
    final coveredDimensions = _normalizedDimensions(
      retrievalOutcome.coveredDimensions,
    );
    final missingDimensions = _normalizedDimensions(
      retrievalOutcome.missingDimensions,
    );
    final canAnswerWithCurrentEvidence = _answerGateResolver
        .canAnswerWithCurrentEvidence(
          retrievalOutcome: retrievalOutcome,
          policy: boundaryPolicy,
        );
    if (state.shouldStopByBudget || state.shouldStopByIteration) {
      return ToolAssessment(
        assessmentType: AssessmentType.budgetExhausted,
        userMessage: '',
        shouldContinueLoop: false,
        allowAnswerWithCurrentEvidence: canAnswerWithCurrentEvidence,
        reasonCode: PlannerReasonCode.budgetBoundary,
        referenceCount: referenceCount,
        queryCount: queryCount,
        coveredDimensions: coveredDimensions,
        missingDimensions: missingDimensions,
      );
    }

    if (!lastStepSuccess) {
      _consecutiveFailures++;

      final loopDetected = lastObservation['loopDetected'] == true;
      if (loopDetected) {
        final pattern = (lastObservation['loopPattern'] as String?) ?? '';
        return ToolAssessment(
          assessmentType: AssessmentType.toolFailed,
          userMessage: '',
          shouldContinueLoop:
              pattern != 'global_circuit_breaker' &&
              _consecutiveFailures < _maxConsecutiveFailures,
          allowAnswerWithCurrentEvidence: canAnswerWithCurrentEvidence,
          reasonCode: PlannerReasonCode.targetedProbe,
          referenceCount: referenceCount,
          queryCount: queryCount,
          coveredDimensions: coveredDimensions,
          missingDimensions: missingDimensions,
        );
      }

      if (canAnswerWithCurrentEvidence) {
        return ToolAssessment(
          assessmentType: AssessmentType.sufficient,
          userMessage: '',
          shouldContinueLoop: false,
          allowAnswerWithCurrentEvidence: true,
          reasonCode: PlannerReasonCode.deliverIncrement,
          referenceCount: referenceCount,
          queryCount: queryCount,
          coveredDimensions: coveredDimensions,
          missingDimensions: missingDimensions,
        );
      }

      if (_consecutiveFailures >= _maxConsecutiveFailures) {
        return ToolAssessment(
          assessmentType: AssessmentType.toolFailed,
          userMessage: '',
          shouldContinueLoop: false,
          reasonCode: PlannerReasonCode.sourceUnstable,
          referenceCount: referenceCount,
          queryCount: queryCount,
          coveredDimensions: coveredDimensions,
          missingDimensions: missingDimensions,
        );
      }

      return ToolAssessment(
        assessmentType: AssessmentType.toolFailed,
        userMessage: '',
        shouldContinueLoop: true,
        reasonCode: PlannerReasonCode.sourceUnstable,
        referenceCount: referenceCount,
        queryCount: queryCount,
        coveredDimensions: coveredDimensions,
        missingDimensions: missingDimensions,
      );
    }

    _consecutiveFailures = 0;

    final qualityScore = resultData['qualityScore'] as num? ?? 0.0;
    if (qualityScore < policy.reflectionQualityScoreMin) {
      _consecutiveLowQuality++;
      final batchCoverageLooksUsable =
          queryCount >= 2 && referenceCount >= (queryCount * 2);
      if (batchCoverageLooksUsable || canAnswerWithCurrentEvidence) {
        return ToolAssessment(
          assessmentType: AssessmentType.sufficient,
          userMessage: '',
          shouldContinueLoop: false,
          allowAnswerWithCurrentEvidence: canAnswerWithCurrentEvidence,
          reasonCode: PlannerReasonCode.deliverIncrement,
          referenceCount: referenceCount,
          queryCount: queryCount,
          coveredDimensions: coveredDimensions,
          missingDimensions: missingDimensions,
        );
      }
      // Fast-convergence problem types accept whatever results are available
      // rather than entering additional search rounds.
      if (_isFastConvergence ||
          _consecutiveLowQuality >= _maxConsecutiveLowQuality) {
        return ToolAssessment(
          assessmentType: AssessmentType.sufficient,
          userMessage: '',
          shouldContinueLoop: false,
          allowAnswerWithCurrentEvidence: canAnswerWithCurrentEvidence,
          reasonCode: _isFastConvergence
              ? PlannerReasonCode.reduceWaitTime
              : PlannerReasonCode.deliverIncrement,
          referenceCount: referenceCount,
          queryCount: queryCount,
          coveredDimensions: coveredDimensions,
          missingDimensions: missingDimensions,
        );
      }
      return ToolAssessment(
        assessmentType: AssessmentType.needMoreSearch,
        userMessage: '',
        shouldContinueLoop: true,
        rewriteQuery: true,
        reasonCode: PlannerReasonCode.needMoreEvidence,
        referenceCount: referenceCount,
        queryCount: queryCount,
        coveredDimensions: coveredDimensions,
        missingDimensions: missingDimensions,
      );
    }
    _consecutiveLowQuality = 0;

    if (shouldReplan) {
      if (_isFastConvergence || canAnswerWithCurrentEvidence) {
        return ToolAssessment(
          assessmentType: AssessmentType.sufficient,
          userMessage: '',
          shouldContinueLoop: false,
          allowAnswerWithCurrentEvidence: canAnswerWithCurrentEvidence,
          reasonCode: PlannerReasonCode.deliverIncrement,
          referenceCount: referenceCount,
          queryCount: queryCount,
          coveredDimensions: coveredDimensions,
          missingDimensions: missingDimensions,
        );
      }
      return ToolAssessment(
        assessmentType: AssessmentType.needMoreSearch,
        userMessage: '',
        shouldContinueLoop: true,
        reasonCode: PlannerReasonCode.needMoreSearch,
        referenceCount: referenceCount,
        queryCount: queryCount,
        coveredDimensions: coveredDimensions,
        missingDimensions: missingDimensions,
      );
    }

    return ToolAssessment(
      assessmentType: AssessmentType.sufficient,
      userMessage: '',
      shouldContinueLoop: false,
      allowAnswerWithCurrentEvidence:
          canAnswerWithCurrentEvidence || !boundaryPolicy.evidenceRequired,
      reasonCode: PlannerReasonCode.evidenceReady,
      referenceCount: referenceCount,
      queryCount: queryCount,
      coveredDimensions: coveredDimensions,
      missingDimensions: missingDimensions,
    );
  }

  int _positiveInt(Object? value) {
    if (value is num) {
      final number = value.toInt();
      return number > 0 ? number : 0;
    }
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed == null || parsed <= 0) return 0;
    return parsed;
  }

  List<String> _normalizedDimensions(Object? value) {
    if (value is! List) {
      return const <String>[];
    }
    final seen = <String>{};
    final normalized = <String>[];
    for (final item in value) {
      final raw = item?.toString().trim() ?? '';
      if (raw.isEmpty) {
        continue;
      }
      final dimension = parseSearchPlanDimension(raw);
      final code = dimension != SearchPlanDimension.unknown
          ? dimension.wireName
          : raw;
      if (seen.add(code)) {
        normalized.add(code);
      }
    }
    return normalized;
  }
}
