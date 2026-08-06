import 'dart:math' as math;

/// Cloud transport 的纯策略；不持有请求、连接或平台资源。
final class CloudRetryPolicy {
  const CloudRetryPolicy({
    this.maxRetries = 2,
    this.initialBackoff = const Duration(milliseconds: 500),
    this.maxBackoff = const Duration(seconds: 8),
  }) : assert(maxRetries >= 0);

  final int maxRetries;
  final Duration initialBackoff;
  final Duration maxBackoff;

  bool canRetryMethod(String method) {
    return method.toUpperCase() == 'GET' || method.toUpperCase() == 'HEAD';
  }

  bool canRetryStatus(int statusCode) {
    return statusCode == 429 ||
        statusCode == 502 ||
        statusCode == 503 ||
        statusCode == 504;
  }

  Duration delayFor({
    required int attempt,
    String? retryAfter,
    double jitterUnit = 0.5,
  }) {
    final retryAfterSeconds = int.tryParse(retryAfter?.trim() ?? '');
    if (retryAfterSeconds != null && retryAfterSeconds >= 0) {
      return Duration(
        seconds: math.min(retryAfterSeconds, maxBackoff.inSeconds),
      );
    }
    final exponentialMs = math.min(
      initialBackoff.inMilliseconds * math.pow(2, attempt).toInt(),
      maxBackoff.inMilliseconds,
    );
    final boundedJitter = jitterUnit.clamp(0.0, 1.0);
    final jitterMs = (exponentialMs * 0.2 * (boundedJitter - 0.5)).round();
    return Duration(milliseconds: math.max(0, exponentialMs + jitterMs));
  }
}
