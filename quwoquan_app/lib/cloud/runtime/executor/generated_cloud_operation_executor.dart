import 'dart:async';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_operation_header_factory.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_json_transport.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_retry_policy.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CloudTelemetryFailureObserver =
    void Function(Object error, StackTrace stackTrace);

final class AppGeneratedCloudOperationExecutor
    implements CloudOperationExecutor {
  AppGeneratedCloudOperationExecutor({
    required this.environment,
    required this.transport,
    required this.headerFactory,
    required this.telemetrySink,
    this.retryPolicy = const CloudRetryPolicy(),
    DateTime Function()? now,
    Future<void> Function(Duration delay)? sleeper,
    double Function()? jitterUnit,
    CloudTelemetryFailureObserver? telemetryFailureObserver,
  }) : _now = now ?? DateTime.now,
       _sleeper = sleeper ?? Future<void>.delayed,
       _jitterUnit = jitterUnit ?? _defaultJitterUnit,
       _telemetryFailureObserver =
           telemetryFailureObserver ?? _ignoreTelemetryFailure;

  final CloudRuntimeEnvironment environment;
  final CloudJsonTransport transport;
  final CloudOperationHeaderFactory headerFactory;
  final CloudOperationTelemetrySink telemetrySink;
  final CloudRetryPolicy retryPolicy;
  final DateTime Function() _now;
  final Future<void> Function(Duration delay) _sleeper;
  final double Function() _jitterUnit;
  final CloudTelemetryFailureObserver _telemetryFailureObserver;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    _validateInvocation(operation, context);
    final startedAt = _now();
    final operationDeadline = startedAt.add(
      Duration(milliseconds: operation.timeoutMilliseconds),
    );
    final requestedDeadline = context.deadlineAt;
    final deadline =
        requestedDeadline != null &&
            requestedDeadline.isBefore(operationDeadline)
        ? requestedDeadline
        : operationDeadline;
    try {
      context.cancellation?.throwIfCancelled();
    } catch (error, stackTrace) {
      Error.throwWithStackTrace(
        _asCloudException(error, operation),
        stackTrace,
      );
    }
    if (!deadline.isAfter(_now())) {
      throw _asCloudException(
        TimeoutException(
          '${operation.canonicalOperationId} deadline exhausted',
        ),
        operation,
      );
    }
    late final CloudOperationRequestPayload payload;
    late final Map<String, String> encodedHeaders;
    try {
      payload = requestEncoder();
      encodedHeaders = _validatedEncodedHeaders(payload.headers, operation);
      _validateVersionPrecondition(operation, encodedHeaders);
    } catch (error, stackTrace) {
      Error.throwWithStackTrace(
        _asCloudException(error, operation),
        stackTrace,
      );
    }
    late final Map<String, String> requestHeaders;
    try {
      final runtimeHeaders = headerFactory.build(
        operation: operation,
        invocation: context,
        effectiveDeadlineAt: deadline,
      );
      for (final key in encodedHeaders.keys) {
        if (runtimeHeaders.keys.any(
          (existing) => existing.toLowerCase() == key.toLowerCase(),
        )) {
          throw StateError(
            'Encoded header conflicts with runtime header: $key',
          );
        }
      }
      requestHeaders = <String, String>{...runtimeHeaders, ...encodedHeaders};
    } catch (error, stackTrace) {
      Error.throwWithStackTrace(
        _asCloudException(error, operation),
        stackTrace,
      );
    }
    final maxAttempts = operation.maxAttempts < 1 ? 1 : operation.maxAttempts;
    final replaySafe = _isReplaySafe(operation, context);

    for (var attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        context.cancellation?.throwIfCancelled();
      } catch (error, stackTrace) {
        Error.throwWithStackTrace(
          _asCloudException(error, operation),
          stackTrace,
        );
      }
      final remaining = deadline.difference(_now());
      if (remaining <= Duration.zero) {
        throw _asCloudException(
          TimeoutException(
            '${operation.canonicalOperationId} deadline exhausted',
          ),
          operation,
        );
      }
      final stopwatch = Stopwatch()..start();
      final abortTrigger = _OperationAbortTrigger(
        remaining: remaining,
        cancellation: context.cancellation,
      );
      try {
        final response = await transport.send(
          CloudJsonTransportRequest(
            method: operation.method,
            authMode: operation.authMode,
            uri: _resolveUri(
              operation.pathTemplate,
              payload.pathParameters,
              payload.queryParameters,
            ),
            gatewayOrigin: environment.gatewayBaseUri,
            headers: <String, String>{
              ...requestHeaders,
              'X-Client-Attempt': '$attempt',
            },
            abortTrigger: abortTrigger.future,
            body: _bodyAsJsonMap(operation, payload.body),
          ),
        );
        final decoded = responseDecoder(response);
        stopwatch.stop();
        _record(
          operation: operation,
          context: context,
          elapsed: stopwatch.elapsed,
          succeeded: true,
          attempt: attempt,
          requestHeaders: requestHeaders,
        );
        return decoded;
      } catch (error, stackTrace) {
        stopwatch.stop();
        final cloudError = _normalizeAttemptError(
          error,
          operation,
          context.cancellation,
        );
        var effectiveError = cloudError;
        var effectiveStackTrace = stackTrace;
        var retryReason = _retryReason(cloudError);
        var shouldRetry =
            attempt < maxAttempts &&
            replaySafe &&
            retryReason != null &&
            deadline.isAfter(_now());
        if (shouldRetry && cloudError.statusCode == 401) {
          final refreshRemaining = deadline.difference(_now());
          if (refreshRemaining <= Duration.zero) {
            shouldRetry = false;
          } else {
            final refreshAbortTrigger = _OperationAbortTrigger(
              remaining: refreshRemaining,
              cancellation: context.cancellation,
            );
            try {
              shouldRetry = await transport.refreshAuthorization(
                abortTrigger: refreshAbortTrigger.future,
              );
            } catch (refreshError, refreshStackTrace) {
              effectiveError = _normalizeAttemptError(
                refreshError,
                operation,
                context.cancellation,
              );
              effectiveStackTrace = refreshStackTrace;
              retryReason = null;
              shouldRetry = false;
            } finally {
              refreshAbortTrigger.dispose();
            }
          }
        }
        Duration? retryDelay;
        if (shouldRetry) {
          retryDelay = _retryDelay(effectiveError, completedAttempt: attempt);
          if (retryDelay >= deadline.difference(_now())) {
            shouldRetry = false;
          }
        }
        _record(
          operation: operation,
          context: context,
          elapsed: stopwatch.elapsed,
          succeeded: false,
          attempt: attempt,
          requestHeaders: requestHeaders,
          statusCode: effectiveError.statusCode,
          failureCode: effectiveError.runtimeFailure.code,
          retryReason: shouldRetry ? retryReason : null,
          recoveryAction: shouldRetry
              ? 'retry'
              : effectiveError.runtimeFailure.recovery.action,
          disruptionLevel: shouldRetry
              ? 'silent'
              : effectiveError.runtimeFailure.recovery.disruptionLevel,
        );
        if (!shouldRetry) {
          Error.throwWithStackTrace(effectiveError, effectiveStackTrace);
        }
        try {
          await _waitBeforeRetry(
            retryDelay!,
            deadline: deadline,
            cancellation: context.cancellation,
          );
        } catch (waitError, waitStackTrace) {
          final waitCloudError = _asCloudException(waitError, operation);
          _record(
            operation: operation,
            context: context,
            elapsed: Duration.zero,
            succeeded: false,
            attempt: attempt,
            requestHeaders: requestHeaders,
            failureCode: waitCloudError.runtimeFailure.code,
            retryReason: 'retry_interrupted',
            recoveryAction: waitCloudError.runtimeFailure.recovery.action,
            disruptionLevel:
                waitCloudError.runtimeFailure.recovery.disruptionLevel,
          );
          Error.throwWithStackTrace(waitCloudError, waitStackTrace);
        }
      } finally {
        abortTrigger.dispose();
      }
    }
    throw CloudErrorMapper.invalidResponse(
      message: 'Generated operation attempt loop exhausted',
      requestPath: operation.pathTemplate,
      functionModule: 'generated_cloud_operation_executor',
    );
  }

  Map<String, String> _validatedEncodedHeaders(
    Map<String, String> headers,
    CloudOperationContract operation,
  ) {
    const allowed = <String>{'if-match'};
    final normalized = <String, String>{};
    for (final entry in headers.entries) {
      final name = entry.key.trim();
      final value = entry.value.trim();
      if (!allowed.contains(name.toLowerCase()) || value.isEmpty) {
        throw CloudErrorMapper.invalidResponse(
          message: 'Unsupported operation-specific request header: $name',
          requestPath: operation.pathTemplate,
          functionModule: 'generated_cloud_operation_executor',
        );
      }
      normalized[name] = value;
    }
    return Map<String, String>.unmodifiable(normalized);
  }

  void _validateVersionPrecondition(
    CloudOperationContract operation,
    Map<String, String> headers,
  ) {
    String? ifMatch;
    for (final entry in headers.entries) {
      if (entry.key.toLowerCase() == 'if-match') {
        ifMatch = entry.value.trim();
        break;
      }
    }
    if (operation.versionPrecondition == 'if_match') {
      if (ifMatch == null || !RegExp(r'^"[1-9][0-9]*"$').hasMatch(ifMatch)) {
        throw CloudErrorMapper.invalidResponse(
          message:
              '${operation.canonicalOperationId} requires a quoted positive If-Match version',
          requestPath: operation.pathTemplate,
          functionModule: 'generated_cloud_operation_executor',
        );
      }
      return;
    }
    if (ifMatch != null) {
      throw CloudErrorMapper.invalidResponse(
        message:
            '${operation.canonicalOperationId} forbids caller version negotiation',
        requestPath: operation.pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
  }

  Uri _resolveUri(
    String pathTemplate,
    Map<String, String> pathParameters,
    Map<String, String> queryParameters,
  ) {
    if (!pathTemplate.startsWith('/') ||
        pathTemplate.contains('?') ||
        pathTemplate.contains('#')) {
      throw CloudErrorMapper.invalidResponse(
        message:
            'Operation path template must be an absolute path without query/fragment',
        requestPath: pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
    final placeholders = RegExp(r'\{([^{}]+)\}');
    final operationSegments = pathTemplate
        .split('/')
        .where((segment) => segment.isNotEmpty)
        .map((segment) {
          return segment.replaceAllMapped(placeholders, (match) {
            final name = match.group(1)!;
            final value = pathParameters[name]?.trim() ?? '';
            if (value.isEmpty) {
              throw CloudErrorMapper.invalidResponse(
                message: 'Missing path parameter: $name',
                requestPath: pathTemplate,
                functionModule: 'generated_cloud_operation_executor',
              );
            }
            return value;
          });
        })
        .toList(growable: false);
    final unresolved = operationSegments.any(placeholders.hasMatch);
    if (unresolved) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Unresolved operation path template',
        requestPath: pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
    final baseSegments = environment.gatewayBaseUri.pathSegments
        .where((segment) => segment.isNotEmpty)
        .toList(growable: false);
    return Uri(
      scheme: environment.gatewayBaseUri.scheme,
      userInfo: environment.gatewayBaseUri.userInfo,
      host: environment.gatewayBaseUri.host,
      port: environment.gatewayBaseUri.hasPort
          ? environment.gatewayBaseUri.port
          : null,
      pathSegments: <String>[...baseSegments, ...operationSegments],
      queryParameters: queryParameters.isEmpty ? null : queryParameters,
    );
  }

  CloudJsonMap? _bodyAsJsonMap(CloudOperationContract operation, Object? body) {
    if (body == null) return null;
    if (operation.method.toUpperCase() == 'GET' ||
        operation.method.toUpperCase() == 'HEAD') {
      throw CloudErrorMapper.invalidResponse(
        message:
            '${operation.canonicalOperationId} ${operation.method} cannot carry body',
        requestPath: operation.pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
    if (body is Map<String, dynamic>) return body;
    if (body is Map) return Map<String, dynamic>.from(body);
    throw CloudErrorMapper.invalidResponse(
      message: 'Generated Cloud operation body must be a JSON object',
      requestPath: operation.pathTemplate,
      functionModule: 'generated_cloud_operation_executor',
    );
  }

  void _validateInvocation(
    CloudOperationContract operation,
    CloudOperationInvocationContext context,
  ) {
    if (operation.commercialStatus != 'ready') {
      throw CloudErrorMapper.invalidResponse(
        message:
            '${operation.canonicalOperationId} is not commercially enabled',
        requestPath: operation.pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
    if (operation.timeoutMilliseconds <= 0) {
      throw CloudErrorMapper.invalidResponse(
        message:
            '${operation.canonicalOperationId} has no executable timeout budget',
        requestPath: operation.pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
    if (operation.idempotency == 'required' &&
        (context.idempotencyKey?.trim().isEmpty ?? true)) {
      throw CloudErrorMapper.invalidResponse(
        message:
            '${operation.canonicalOperationId} requires an idempotency key',
        requestPath: operation.pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
    if (context.cancellation != null && operation.cancellation != 'supported') {
      throw CloudErrorMapper.invalidResponse(
        message:
            '${operation.canonicalOperationId} does not support cancellation',
        requestPath: operation.pathTemplate,
        functionModule: 'generated_cloud_operation_executor',
      );
    }
  }

  bool _isReplaySafe(
    CloudOperationContract operation,
    CloudOperationInvocationContext context,
  ) {
    if (operation.retryMode == 'none' || operation.retryMode.isEmpty) {
      return false;
    }
    final method = operation.method.toUpperCase();
    if (method == 'GET' || method == 'HEAD' || method == 'OPTIONS') {
      return true;
    }
    return (operation.idempotency == 'required' ||
            operation.idempotency == 'optional') &&
        (context.idempotencyKey?.trim().isNotEmpty ?? false);
  }

  CloudException _normalizeAttemptError(
    Object error,
    CloudOperationContract operation,
    CloudOperationCancellationSignal? cancellation,
  ) {
    if (error is http.RequestAbortedException) {
      return _asCloudException(
        cancellation?.isCancelled ?? false
            ? const CloudOperationCancelledException()
            : TimeoutException(
                '${operation.canonicalOperationId} exceeded its deadline',
              ),
        operation,
      );
    }
    return _asCloudException(error, operation);
  }

  CloudException _asCloudException(
    Object error,
    CloudOperationContract operation,
  ) {
    if (error is CloudException) return error;
    return CloudErrorMapper.fromException(
      error,
      requestPath: operation.pathTemplate,
    );
  }

  String? _retryReason(CloudException error) {
    final statusCode = error.statusCode;
    if (statusCode == 401) return 'authorization_refresh';
    if (statusCode != null && retryPolicy.canRetryStatus(statusCode)) {
      return statusCode == 429 ? 'retry_after' : 'retryable_status';
    }
    return switch (error.type) {
      CloudErrorType.timeout => 'timeout',
      CloudErrorType.network => 'network',
      CloudErrorType.rateLimited => 'retry_after',
      _ => null,
    };
  }

  Duration _retryDelay(CloudException error, {required int completedAttempt}) {
    final retryAfter = error.retryAfter;
    if (retryAfter != null) {
      return retryAfter;
    }
    final recoveryAfterSeconds = error.runtimeFailure.recovery.afterSeconds;
    if (recoveryAfterSeconds > 0) {
      return Duration(seconds: recoveryAfterSeconds);
    }
    return retryPolicy.delayFor(
      attempt: completedAttempt - 1,
      jitterUnit: _jitterUnit(),
    );
  }

  Future<void> _waitBeforeRetry(
    Duration delay, {
    required DateTime deadline,
    CloudOperationCancellationSignal? cancellation,
  }) async {
    cancellation?.throwIfCancelled();
    final remaining = deadline.difference(_now());
    if (remaining <= Duration.zero || delay >= remaining) {
      throw TimeoutException('Operation deadline exhausted during backoff');
    }
    if (delay <= Duration.zero) return;
    if (cancellation == null) {
      await _sleeper(delay);
      return;
    }
    final outcome =
        await Future.any<_RetryWaitOutcome>(<Future<_RetryWaitOutcome>>[
          _sleeper(delay).then((_) => _RetryWaitOutcome.elapsed),
          cancellation.whenCancelled.then((_) => _RetryWaitOutcome.cancelled),
        ]);
    if (outcome == _RetryWaitOutcome.cancelled) {
      throw const CloudOperationCancelledException();
    }
  }

  void _record({
    required CloudOperationContract operation,
    required CloudOperationInvocationContext context,
    required Duration elapsed,
    required bool succeeded,
    required int attempt,
    Map<String, String>? requestHeaders,
    int? statusCode,
    String? failureCode,
    String? retryReason,
    String? recoveryAction,
    String? disruptionLevel,
  }) {
    try {
      telemetrySink.record(
        CloudOperationTelemetryEvent(
          canonicalOperationId: operation.canonicalOperationId,
          surfaceId: context.surfaceId,
          method: operation.method,
          pathTemplate: operation.pathTemplate,
          elapsed: elapsed,
          succeeded: succeeded,
          attempt: attempt,
          requestId: requestHeaders?['X-Request-Id'],
          traceId: requestHeaders?['X-Trace-Id'],
          statusCode: statusCode,
          failureCode: failureCode,
          retryReason: retryReason,
          recoveryAction: recoveryAction,
          disruptionLevel: disruptionLevel,
        ),
      );
    } catch (error, stackTrace) {
      _telemetryFailureObserver(error, stackTrace);
    }
  }
}

/// Per-attempt abort source whose deadline timer is released as soon as the
/// transport attempt finishes. A bare `Future.delayed` would otherwise remain
/// reachable until the full operation deadline even after a successful call.
final class _OperationAbortTrigger {
  _OperationAbortTrigger({
    required Duration remaining,
    required CloudOperationCancellationSignal? cancellation,
  }) {
    _deadlineTimer = Timer(remaining, _complete);
    cancellation?.whenCancelled.then((_) => _complete());
  }

  final Completer<void> _completer = Completer<void>();
  late final Timer _deadlineTimer;
  bool _disposed = false;

  Future<void> get future => _completer.future;

  void _complete() {
    if (_disposed || _completer.isCompleted) {
      return;
    }
    _completer.complete();
  }

  void dispose() {
    if (_disposed) {
      return;
    }
    _disposed = true;
    _deadlineTimer.cancel();
  }
}

enum _RetryWaitOutcome { elapsed, cancelled }

double _defaultJitterUnit() => 0.5;

void _ignoreTelemetryFailure(Object error, StackTrace stackTrace) {
  // Telemetry is deliberately non-blocking; production composition can inject
  // a secondary observer without changing the business operation outcome.
}
