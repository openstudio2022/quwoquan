import 'package:quwoquan_app/personal_assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/default_processing_copy_bank.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_state.dart';

enum ToolAssessmentType {
  sufficient,
  needMoreSearch,
  needDifferentTool,
  toolFailed,
  budgetExhausted,
}

class ToolAssessmentResult {
  const ToolAssessmentResult({
    required this.type,
    required this.userMessage,
    this.shouldContinueLoop = true,
    this.gapFill = false,
    this.rewriteQuery = false,
  });

  final ToolAssessmentType type;
  final String userMessage;
  final bool shouldContinueLoop;
  final bool gapFill;
  final bool rewriteQuery;
}

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

  bool get _isFastConvergence =>
      parseProblemClass(problemClass).isFastConvergence;

  void reset() {
    _consecutiveFailures = 0;
    _consecutiveLowQuality = 0;
  }

  ToolAssessmentResult assess({
    required ReactRunState state,
    required bool lastStepSuccess,
    required Map<String, dynamic> lastObservation,
    required bool shouldReplan,
    required ReactPolicy policy,
  }) {
    if (state.shouldStopByBudget || state.shouldStopByIteration) {
      return ToolAssessmentResult(
        type: ToolAssessmentType.budgetExhausted,
        userMessage: DefaultProcessingCopyBank.toolAssessMessage(
          ToolAssessMessageKey.budgetExhausted,
        ),
        shouldContinueLoop: false,
      );
    }

    if (!lastStepSuccess) {
      _consecutiveFailures++;

      final loopDetected = lastObservation['loopDetected'] == true;
      if (loopDetected) {
        final pattern = (lastObservation['loopPattern'] as String?) ?? '';
        return ToolAssessmentResult(
          type: ToolAssessmentType.needDifferentTool,
          userMessage: DefaultProcessingCopyBank.toolAssessMessage(
            ToolAssessMessageKey.loopDetected,
          ),
          shouldContinueLoop: pattern != 'global_circuit_breaker' &&
              _consecutiveFailures < _maxConsecutiveFailures,
        );
      }

      if (_consecutiveFailures >= _maxConsecutiveFailures) {
        return ToolAssessmentResult(
          type: ToolAssessmentType.toolFailed,
          userMessage: DefaultProcessingCopyBank.toolAssessMessage(
            ToolAssessMessageKey.toolFailedStop,
          ),
          shouldContinueLoop: false,
        );
      }

      return ToolAssessmentResult(
        type: ToolAssessmentType.toolFailed,
        userMessage: DefaultProcessingCopyBank.toolAssessMessage(
          ToolAssessMessageKey.toolFailedRetry,
        ),
        shouldContinueLoop: true,
      );
    }

    _consecutiveFailures = 0;

    final resultData =
        (lastObservation['data'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final queryCount = _positiveInt(resultData['queryCount']);
    final explicitReferenceCount = _positiveInt(resultData['referenceCount']);
    final referenceCount = explicitReferenceCount > 0
        ? explicitReferenceCount
        : ((resultData['references'] as List?)?.length ?? 0);
    final qualityScore =
        resultData['qualityScore'] as num? ?? 0.0;
    if (qualityScore < policy.reflectionQualityScoreMin) {
      _consecutiveLowQuality++;
      final batchCoverageLooksUsable =
          queryCount >= 2 && referenceCount >= (queryCount * 2);
      if (batchCoverageLooksUsable) {
        return ToolAssessmentResult(
          type: ToolAssessmentType.sufficient,
          userMessage: DefaultProcessingCopyBank.toolAssessMessage(
            ToolAssessMessageKey.batchUsable,
          ),
          shouldContinueLoop: false,
        );
      }
      // Fast-convergence problem types accept whatever results are available
      // rather than entering additional search rounds.
      if (_isFastConvergence ||
          _consecutiveLowQuality >= _maxConsecutiveLowQuality) {
        return ToolAssessmentResult(
          type: ToolAssessmentType.sufficient,
          userMessage: _isFastConvergence
              ? DefaultProcessingCopyBank.toolAssessMessage(
                  ToolAssessMessageKey.fastConverged,
                )
              : DefaultProcessingCopyBank.toolAssessMessage(
                  ToolAssessMessageKey.slowConverged,
                ),
          shouldContinueLoop: false,
        );
      }
      return ToolAssessmentResult(
        type: ToolAssessmentType.needMoreSearch,
        userMessage: queryCount >= 2
            ? DefaultProcessingCopyBank.toolAssessMessage(
                ToolAssessMessageKey.needMoreSearchMulti,
              )
            : DefaultProcessingCopyBank.toolAssessMessage(
                ToolAssessMessageKey.needMoreSearchSingle,
              ),
        shouldContinueLoop: true,
        rewriteQuery: true,
      );
    }
    _consecutiveLowQuality = 0;

    if (shouldReplan) {
      if (_isFastConvergence) {
        return ToolAssessmentResult(
          type: ToolAssessmentType.sufficient,
          userMessage: DefaultProcessingCopyBank.toolAssessMessage(
            ToolAssessMessageKey.replanFast,
          ),
          shouldContinueLoop: false,
        );
      }
      return ToolAssessmentResult(
        type: ToolAssessmentType.needMoreSearch,
        userMessage: queryCount >= 2
            ? DefaultProcessingCopyBank.toolAssessMessage(
                ToolAssessMessageKey.replanMulti,
              )
            : DefaultProcessingCopyBank.toolAssessMessage(
                ToolAssessMessageKey.replanSingle,
              ),
        shouldContinueLoop: true,
      );
    }

    return ToolAssessmentResult(
      type: ToolAssessmentType.sufficient,
      userMessage: referenceCount > 0 && queryCount >= 2
          ? DefaultProcessingCopyBank.toolAssessMessage(
              ToolAssessMessageKey.finalMulti,
              queryCount: queryCount,
            )
          : referenceCount > 0
          ? DefaultProcessingCopyBank.toolAssessMessage(
              ToolAssessMessageKey.finalRefs,
            )
          : DefaultProcessingCopyBank.toolAssessMessage(
              ToolAssessMessageKey.finalDefault,
            ),
      shouldContinueLoop: false,
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
}
