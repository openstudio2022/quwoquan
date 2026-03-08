import 'dart:math' show min, max;

/// Truncates tool results to prevent context window overflow.
/// Inspired by OpenClaw's tool-result-truncation.ts.
class ToolResultTruncator {
  const ToolResultTruncator({
    this.maxContextShareRatio = 0.3,
    this.hardMaxChars = 200000,
    this.minKeepChars = 1500,
    this.contextWindowChars = 60000,
  });

  final double maxContextShareRatio;
  final int hardMaxChars;
  final int minKeepChars;
  final int contextWindowChars;

  String truncate(String result) {
    final maxChars = min(
      (contextWindowChars * maxContextShareRatio).toInt(),
      hardMaxChars,
    );
    if (result.length <= maxChars) return result;

    final keepChars = max(maxChars - 80, minKeepChars);
    final cutPoint = result.lastIndexOf('\n', keepChars);
    final effectiveCut =
        (cutPoint > keepChars * 0.8) ? cutPoint : keepChars;
    return '${result.substring(0, effectiveCut)}\n\n[内容已截断，原始 ${result.length} 字符]';
  }
}
