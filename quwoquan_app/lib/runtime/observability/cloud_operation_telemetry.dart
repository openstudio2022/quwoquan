final class CloudOperationTelemetryEvent {
  const CloudOperationTelemetryEvent({
    required this.canonicalOperationId,
    required this.surfaceId,
    required this.method,
    required this.pathTemplate,
    required this.elapsed,
    required this.succeeded,
    required this.attempt,
    this.requestId,
    this.traceId,
    this.statusCode,
    this.failureCode,
    this.retryReason,
    this.recoveryAction,
    this.disruptionLevel,
    this.cacheSource = 'network',
  });

  final String canonicalOperationId;
  final String surfaceId;
  final String method;
  final String pathTemplate;
  final Duration elapsed;
  final bool succeeded;
  final int attempt;
  final String? requestId;
  final String? traceId;
  final int? statusCode;
  final String? failureCode;
  final String? retryReason;
  final String? recoveryAction;
  final String? disruptionLevel;
  final String cacheSource;
}

abstract interface class CloudOperationTelemetrySink {
  void record(CloudOperationTelemetryEvent event);
}
