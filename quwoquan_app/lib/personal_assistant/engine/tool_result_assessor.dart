import 'package:quwoquan_app/personal_assistant/contracts/runtime_policies.dart';
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
class ToolResultAssessor {
  ToolResultAssessor();

  int _consecutiveFailures = 0;
  int _consecutiveLowQuality = 0;
  static const int _maxConsecutiveFailures = 2;
  static const int _maxConsecutiveLowQuality = 2;

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
      return const ToolAssessmentResult(
        type: ToolAssessmentType.budgetExhausted,
        userMessage: '已收集到部分信息，开始组织回答',
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
          userMessage: '多次尝试未获得新信息，基于已有信息回答',
          shouldContinueLoop: pattern != 'global_circuit_breaker' &&
              _consecutiveFailures < _maxConsecutiveFailures,
        );
      }

      if (_consecutiveFailures >= _maxConsecutiveFailures) {
        return const ToolAssessmentResult(
          type: ToolAssessmentType.toolFailed,
          userMessage: '搜索暂时不可用，将基于已有知识回答',
          shouldContinueLoop: false,
        );
      }

      return const ToolAssessmentResult(
        type: ToolAssessmentType.toolFailed,
        userMessage: '搜索遇到问题，再尝试一次',
        shouldContinueLoop: true,
      );
    }

    _consecutiveFailures = 0;

    final qualityScore =
        (lastObservation['data'] as Map?)?['qualityScore'] as num? ?? 0.0;
    if (qualityScore < policy.reflectionQualityScoreMin) {
      _consecutiveLowQuality++;
      if (_consecutiveLowQuality >= _maxConsecutiveLowQuality) {
        return const ToolAssessmentResult(
          type: ToolAssessmentType.sufficient,
          userMessage: '已尽力搜索，基于已有信息回答',
          shouldContinueLoop: false,
        );
      }
      return const ToolAssessmentResult(
        type: ToolAssessmentType.needMoreSearch,
        userMessage: '找到的信息不够全面，扩大搜索范围',
        shouldContinueLoop: true,
        rewriteQuery: true,
      );
    }
    _consecutiveLowQuality = 0;

    if (shouldReplan) {
      return const ToolAssessmentResult(
        type: ToolAssessmentType.needMoreSearch,
        userMessage: '还需要更多信息来回答您的问题',
        shouldContinueLoop: true,
      );
    }

    final refs = (lastObservation['data'] as Map?)?['references'] as List?;
    final refCount = refs?.length ?? 0;
    return ToolAssessmentResult(
      type: ToolAssessmentType.sufficient,
      userMessage: refCount > 0
          ? '已找到 $refCount 条相关资料'
          : '信息获取完成',
      shouldContinueLoop: false,
    );
  }
}
