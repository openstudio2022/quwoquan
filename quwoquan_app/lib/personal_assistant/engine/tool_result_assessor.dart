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
      problemClass == 'realtime_info' || problemClass == 'simple_qa';

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
        userMessage: '已经有一批能支撑判断的信息了，我先把最重要的结论整理给你。',
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
          userMessage: '这几次拿到的新信息不多，我不想让你白等，先基于已确认的内容回答。',
          shouldContinueLoop: pattern != 'global_circuit_breaker' &&
              _consecutiveFailures < _maxConsecutiveFailures,
        );
      }

      if (_consecutiveFailures >= _maxConsecutiveFailures) {
        return const ToolAssessmentResult(
          type: ToolAssessmentType.toolFailed,
          userMessage: '这轮搜索不太稳定，我先把已经确认的部分整理给你。',
          shouldContinueLoop: false,
        );
      }

      return const ToolAssessmentResult(
        type: ToolAssessmentType.toolFailed,
        userMessage: '这一批资料不够稳，我换个来源再试一下。',
        shouldContinueLoop: true,
      );
    }

    _consecutiveFailures = 0;

    final resultData =
        (lastObservation['data'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final queryCount = _positiveInt(resultData['queryCount']);
    final referenceCount =
        _positiveInt(resultData['referenceCount']) ??
        ((resultData['references'] as List?)?.length ?? 0);
    final qualityScore =
        resultData['qualityScore'] as num? ?? 0.0;
    if (qualityScore < policy.reflectionQualityScoreMin) {
      _consecutiveLowQuality++;
      final batchCoverageLooksUsable =
          queryCount >= 2 && referenceCount >= (queryCount * 2);
      if (batchCoverageLooksUsable) {
        return ToolAssessmentResult(
          type: ToolAssessmentType.sufficient,
          userMessage: '这批方向已经有可用信息了，我先帮你收拢重复和差异。',
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
              ? '关键信息已经够用了，我开始直接整理回答。'
              : '我先不继续拖时间了，基于已经确认的信息整理给你。',
          shouldContinueLoop: false,
        );
      }
      return ToolAssessmentResult(
        type: ToolAssessmentType.needMoreSearch,
        userMessage: queryCount >= 2
            ? '现在主线已经有了，但还差一处会影响判断的空缺，我再替你补查那一块。'
            : '这轮结果还差一点落点，我换更具体的问法再查一次。',
        shouldContinueLoop: true,
        rewriteQuery: true,
      );
    }
    _consecutiveLowQuality = 0;

    if (shouldReplan) {
      if (_isFastConvergence) {
        return const ToolAssessmentResult(
          type: ToolAssessmentType.sufficient,
          userMessage: '关键信息已经够了，我直接整理给你。',
          shouldContinueLoop: false,
        );
      }
      return ToolAssessmentResult(
        type: ToolAssessmentType.needMoreSearch,
        userMessage: queryCount >= 2
            ? '目前大方向已经有了，但还缺一处会影响结论的信息，我再补一轮。'
            : '还差一块关键信息能让结论更稳，我继续补一下。',
        shouldContinueLoop: true,
      );
    }

    return ToolAssessmentResult(
      type: ToolAssessmentType.sufficient,
      userMessage: referenceCount > 0 && queryCount >= 2
          ? '关键信息已经够用了，我开始把$queryCount个方向里的重复和差异收拢成结论。'
          : referenceCount > 0
          ? '关键依据已经基本对齐了，我开始按你更容易看的顺序整理答案。'
          : '关键信息已经够用了，我开始整理答案。',
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
