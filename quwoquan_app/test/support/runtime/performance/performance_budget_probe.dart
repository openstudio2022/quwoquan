/// 端侧性能预算采样 harness（测试树内共享基建，不进入环境 App）。
///
/// 采样语义：在 widget 测试环境测量「一次受控操作」的 wall time（如单次
/// `tester.pump`、一次发送到时间线确认），以固定 seed 数据规模 + 重复采样
/// 中位数对照预算。它守护的是量级劣化（例如每帧全列表重建、O(n^2) 渲染），
/// 不冒充真机帧时长；真机预算由设备矩阵与 TTID 棘轮承载。
///
/// 预算数值是受版本控制的预算声明（本文件），阈值语义归属对应节点 spec 的
/// 预算 REQ；测试正文禁止再写第二份预算值。
///
/// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-006
library;

/// 会话域性能预算声明。
///
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#req-001
abstract final class MessageRuntimePerformanceBudgets {
  /// 打开会话到首条消息可见的耗时预算（测试环境 wall time）。
  static const double openToFirstMessageFrameBudgetMs = 3000;

  /// 长会话滚动中，单次滚动 pump 的中位耗时预算（测试环境 wall time）。
  static const double scrollMedianPumpBudgetMs = 80;

  /// 长会话滚动中，单次 pump 超过该阈值视为一次 jank（测试环境 wall time）。
  static const double scrollJankFrameThresholdMs = 200;

  /// 长会话滚动的 jank 比预算：超阈值帧数 / 总采样帧数。
  static const double scrollJankRatioBudget = 0.2;

  /// 发送一条消息到时间线出现已发送气泡的确认耗时预算（测试环境 wall time）。
  static const double sendConfirmBudgetMs = 2000;
}

/// 重复采样 + 中位数比较的性能探针。
class PerformanceBudgetProbe {
  PerformanceBudgetProbe();

  final List<double> _samplesMs = <double>[];

  List<double> get samplesMs => List<double>.unmodifiable(_samplesMs);

  int get sampleCount => _samplesMs.length;

  /// 测量一次操作的 wall time 并记录样本，返回本次耗时（毫秒）。
  Future<double> measure(Future<void> Function() action) async {
    final stopwatch = Stopwatch()..start();
    await action();
    stopwatch.stop();
    final elapsedMs = stopwatch.elapsedMicroseconds / 1000;
    _samplesMs.add(elapsedMs);
    return elapsedMs;
  }

  double get medianMs => percentileMs(0.5);

  double percentileMs(double quantile) {
    if (_samplesMs.isEmpty) {
      return 0;
    }
    final sorted = List<double>.of(_samplesMs)..sort();
    var index = (quantile * sorted.length).ceil() - 1;
    if (index < 0) {
      index = 0;
    }
    if (index >= sorted.length) {
      index = sorted.length - 1;
    }
    return sorted[index];
  }

  /// 超过 [frameThresholdMs] 的样本占比。
  double jankRatio(double frameThresholdMs) {
    if (_samplesMs.isEmpty) {
      return 0;
    }
    final janky = _samplesMs.where((sample) => sample > frameThresholdMs).length;
    return janky / _samplesMs.length;
  }

  void reset() => _samplesMs.clear();
}

/// 预算断言结果：让测试给出可读的超预算失败信息，而不是裸布尔。
class PerformanceBudgetViolation implements Exception {
  PerformanceBudgetViolation(this.message);

  final String message;

  @override
  String toString() => 'PerformanceBudgetViolation: $message';
}

/// 断言 [actualMs] 不超过 [budgetMs]；超预算抛出带上下文的失败。
void expectWithinBudgetMs({
  required String label,
  required double actualMs,
  required double budgetMs,
}) {
  if (actualMs > budgetMs) {
    throw PerformanceBudgetViolation(
      '$label: actual ${actualMs.toStringAsFixed(2)}ms exceeds budget '
      '${budgetMs.toStringAsFixed(2)}ms',
    );
  }
}

/// 断言比率类指标（如 jank 比）不超过预算。
void expectWithinRatioBudget({
  required String label,
  required double actualRatio,
  required double budgetRatio,
}) {
  if (actualRatio > budgetRatio) {
    throw PerformanceBudgetViolation(
      '$label: actual ratio ${actualRatio.toStringAsFixed(3)} exceeds budget '
      '${budgetRatio.toStringAsFixed(3)}',
    );
  }
}
