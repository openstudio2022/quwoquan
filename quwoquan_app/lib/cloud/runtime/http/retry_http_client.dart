import 'dart:async';
import 'dart:math' as math;

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/transport/cloud_retry_policy.dart';

/// HTTP client wrapper with exponential backoff retry for transient failures.
///
/// 只自动重试可重放的 GET / HEAD。Command 的幂等重放由 generated operation
/// descriptor 与 executor 独立控制，禁止在 transport 全局开启。
class RetryHttpClient extends http.BaseClient {
  RetryHttpClient({
    http.Client? inner,
    this.policy = const CloudRetryPolicy(),
    math.Random? random,
    Future<void> Function(Duration delay)? sleeper,
  }) : _inner = inner ?? http.Client(),
       _random = random ?? math.Random(),
       _sleeper = sleeper ?? Future<void>.delayed;

  final http.Client _inner;
  final CloudRetryPolicy policy;
  final math.Random _random;
  final Future<void> Function(Duration delay) _sleeper;

  /// Generated operation executor owns retry accounting and calls this path
  /// so one transport invocation always equals one network attempt.
  Future<http.StreamedResponse> sendSingleAttempt(http.BaseRequest request) {
    return _inner.send(request);
  }

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final shouldRetry =
        policy.canRetryMethod(request.method) && request is http.Request;

    for (var attempt = 0; attempt <= policy.maxRetries; attempt++) {
      try {
        final response = await _inner.send(_copyRequest(request));
        if (shouldRetry &&
            attempt < policy.maxRetries &&
            policy.canRetryStatus(response.statusCode)) {
          await response.stream.drain<void>();
          await _waitBeforeRetry(
            attempt,
            retryAfter: response.headers['retry-after'],
          );
          continue;
        }
        return response;
      } on http.ClientException {
        if (!shouldRetry || attempt == policy.maxRetries) rethrow;
        await _waitBeforeRetry(attempt);
      } on TimeoutException {
        if (!shouldRetry || attempt == policy.maxRetries) rethrow;
        await _waitBeforeRetry(attempt);
      }
    }
    throw StateError('RetryHttpClient exhausted without response');
  }

  Future<void> _waitBeforeRetry(int attempt, {String? retryAfter}) {
    return _sleeper(
      policy.delayFor(
        attempt: attempt,
        retryAfter: retryAfter,
        jitterUnit: _random.nextDouble(),
      ),
    );
  }

  http.BaseRequest _copyRequest(http.BaseRequest original) {
    if (original is http.Request) {
      final copy = http.Request(original.method, original.url)
        ..headers.addAll(original.headers)
        ..body = original.body
        ..encoding = original.encoding;
      return copy;
    }
    return original;
  }

  @override
  void close() {
    _inner.close();
  }
}
