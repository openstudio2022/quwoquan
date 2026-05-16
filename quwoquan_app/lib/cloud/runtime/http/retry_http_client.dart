import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:http/http.dart' as http;

/// HTTP client wrapper with exponential backoff retry for transient failures.
///
/// Retries only on:
/// - Network errors (SocketException, TimeoutException)
/// - Server errors (5xx)
///
/// Idempotent methods (GET, HEAD, DELETE, PUT) are always retried.
/// POST/PATCH are only retried if [retryNonIdempotent] is true.
class RetryHttpClient extends http.BaseClient {
  RetryHttpClient({
    http.Client? inner,
    this.maxRetries = 2,
    this.initialBackoffMs = 500,
    this.maxBackoffMs = 8000,
    this.retryNonIdempotent = false,
  }) : _inner = inner ?? http.Client();

  final http.Client _inner;
  final int maxRetries;
  final int initialBackoffMs;
  final int maxBackoffMs;
  final bool retryNonIdempotent;

  static const _idempotentMethods = {'GET', 'HEAD', 'DELETE', 'PUT', 'OPTIONS'};

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final isIdempotent = _idempotentMethods.contains(request.method.toUpperCase());
    final shouldRetry = isIdempotent || retryNonIdempotent;

    for (var attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        final response = await _inner.send(_copyRequest(request));

        if (response.statusCode >= 500 && shouldRetry && attempt < maxRetries) {
          await _backoff(attempt);
          continue;
        }

        return response;
      } on SocketException {
        if (!shouldRetry || attempt == maxRetries) rethrow;
        await _backoff(attempt);
      } on TimeoutException {
        if (!shouldRetry || attempt == maxRetries) rethrow;
        await _backoff(attempt);
      }
    }

    return _inner.send(_copyRequest(request));
  }

  Future<void> _backoff(int attempt) async {
    final delayMs = math.min(
      initialBackoffMs * math.pow(2, attempt).toInt(),
      maxBackoffMs,
    );
    final jitter = (delayMs * 0.2 * (math.Random().nextDouble() - 0.5)).toInt();
    await Future<void>.delayed(Duration(milliseconds: delayMs + jitter));
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
