// Code generated from contracts/metadata/_shared/runtime_observability.yaml. DO NOT EDIT.

final class RuntimeLogSignalMetadata {
  const RuntimeLogSignalMetadata({required this.owner, required this.producers, required this.logKind, required this.defaultSeverity, required this.environments, required this.attributeAllowlist, required this.correlationKeys, required this.backend, required this.retentionDays, required this.sampling, required this.alert, required this.runbook, required this.piiClassification});
  final String owner;
  final List<String> producers;
  final String logKind;
  final String defaultSeverity;
  final List<String> environments;
  final List<String> attributeAllowlist;
  final List<String> correlationKeys;
  final String backend;
  final int retentionDays;
  final String sampling;
  final String alert;
  final String runbook;
  final String piiClassification;
}

abstract final class RuntimeLogCatalog {
  static const String schema = 'observability.slim';
  static const Set<String> logKinds = <String>{'deploy', 'runtime', 'access', 'event', 'exception', 'audit'};
  static const Set<String> severityLevels = <String>{'DEBUG', 'INFO', 'WARN', 'ERROR'};
  static const Set<String> signals = <String>{'app.access.http', 'app.exception.flutter', 'app.exception.platform', 'app.performance.anr', 'app.performance.frame', 'app.performance.media', 'app.runtime.lifecycle', 'data.exception.stage', 'data.runtime.stage', 'ops.audit.control', 'ops.deploy.stackctl', 'ops.exception.runtime', 'ops.runtime.process', 'portal.exception.browser', 'service.access.http', 'service.audit.control', 'service.exception.runtime', 'service.runtime.process'};
  static const Set<String> forbiddenFields = <String>{'schemaVersion', 'eventVersion', 'contractVersion', 'protocolVersion', 'releaseVersion', 'releaseId', 'dataReleaseId'};
  static const Map<String, String> failureCodes = <String, String>{
    'app_native_previous_crash': 'APP.RUNTIME.native_previous_crash',
    'app_uncaught_flutter': 'APP.RUNTIME.uncaught_exception',
    'app_uncaught_platform': 'APP.RUNTIME.uncaught_platform_exception',
    'data_stage_failure': 'DATA.RUNTIME.stage_failed',
    'portal_uncaught_browser': 'PORTAL.RUNTIME.uncaught_browser_exception',
    'service_log_encoding': 'SERVICE.RUNTIME.log_encoding_failed',
  };
  static const Set<String> forbiddenAttributeKeys = <String>{'authorization', 'password', 'passwd', 'secret', 'token', 'apiKey', 'credential', 'cookie', 'phone', 'email', 'ssid', 'ip', 'preciseLocation', 'sessionId'};
  static const Set<String> highCardinalityMetricKeys = <String>{'userId', 'sessionId', 'requestId', 'traceId', 'rawPath'};
  static const Set<String> resourceVersionFields = <String>{'appVersion', 'service.version'};
  static const int maxBatchItems = 50;
  static const int maxCanonicalBodyBytes = 131072;
  static const int maxMessageBytes = 2048;
  static const int maxAttributes = 24;
  static const int maxAttributesBytes = 4096;
  static const int maxAttributeKeyLength = 64;
  static const int maxAttributeValueLength = 512;
  static const int rawRetentionDays = 3;
  static const int appBufferCapacity = 200;
  static const int appDeadLetterCapacity = 100;
  static const int serviceSpoolMaxBatches = 2000;
  static const int serviceDlqMaxBatches = 500;
  static const int deliveryTtlHours = 72;
  static const int retryBaseSeconds = 5;
  static const int retryMaxSeconds = 300;
  static const int retryMaxExponent = 6;
  static const int retryJitterPercent = 25;
  static const List<String> envelopeRequiredFields = <String>['schema', 'occurredAt', 'observedAt', 'logKind', 'severity', 'signal', 'message', 'resource'];
  static const Set<String> envelopeOptionalFields = <String>{'recordId', 'correlation', 'step', 'event', 'result', 'method', 'route', 'status', 'durationMs', 'action', 'target', 'errorCode', 'fingerprint', 'attributes'};
  static const List<String> resourceRequiredFields = <String>['sourceType', 'service'];
  static const Set<String> resourceOptionalFields = <String>{'environment', 'component', 'appVersion', 'service.version'};
  static const Set<String> correlationOptionalFields = <String>{'requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'};
  static const Map<String, List<String>> fieldOrder = <String, List<String>>{
    'deploy': <String>['step', 'result'],
    'runtime': <String>['event', 'result'],
    'access': <String>['method', 'route', 'status', 'durationMs'],
    'event': <String>['event', 'result'],
    'exception': <String>['errorCode'],
    'audit': <String>['action', 'target', 'result'],
  };
  static const Map<String, String> signalKinds = <String, String>{
    'app.access.http': 'access',
    'app.exception.flutter': 'exception',
    'app.exception.platform': 'exception',
    'app.performance.anr': 'event',
    'app.performance.frame': 'event',
    'app.performance.media': 'event',
    'app.runtime.lifecycle': 'runtime',
    'data.exception.stage': 'exception',
    'data.runtime.stage': 'runtime',
    'ops.audit.control': 'audit',
    'ops.deploy.stackctl': 'deploy',
    'ops.exception.runtime': 'exception',
    'ops.runtime.process': 'runtime',
    'portal.exception.browser': 'exception',
    'service.access.http': 'access',
    'service.audit.control': 'audit',
    'service.exception.runtime': 'exception',
    'service.runtime.process': 'runtime',
  };
  static const Map<String, String> signalDefaultSeverities = <String, String>{
    'app.access.http': 'INFO',
    'app.exception.flutter': 'ERROR',
    'app.exception.platform': 'ERROR',
    'app.performance.anr': 'ERROR',
    'app.performance.frame': 'WARN',
    'app.performance.media': 'WARN',
    'app.runtime.lifecycle': 'INFO',
    'data.exception.stage': 'ERROR',
    'data.runtime.stage': 'INFO',
    'ops.audit.control': 'INFO',
    'ops.deploy.stackctl': 'INFO',
    'ops.exception.runtime': 'ERROR',
    'ops.runtime.process': 'INFO',
    'portal.exception.browser': 'ERROR',
    'service.access.http': 'INFO',
    'service.audit.control': 'INFO',
    'service.exception.runtime': 'ERROR',
    'service.runtime.process': 'INFO',
  };
  static const Map<String, RuntimeLogSignalMetadata> signalRegistry = <String, RuntimeLogSignalMetadata>{
    'app.access.http': RuntimeLogSignalMetadata(owner: 'runtime-client-foundation', producers: <String>['dart'], logKind: 'access', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'app.exception.flutter': RuntimeLogSignalMetadata(owner: 'runtime-client-foundation', producers: <String>['dart'], logKind: 'exception', defaultSeverity: 'ERROR', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'app.exception.platform': RuntimeLogSignalMetadata(owner: 'runtime-client-foundation', producers: <String>['dart', 'android', 'ios'], logKind: 'exception', defaultSeverity: 'ERROR', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'app.performance.anr': RuntimeLogSignalMetadata(owner: 'runtime-client-foundation', producers: <String>['dart'], logKind: 'event', defaultSeverity: 'ERROR', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'stallMs', 'anrThresholdMs', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'app.performance.frame': RuntimeLogSignalMetadata(owner: 'runtime-client-foundation', producers: <String>['dart'], logKind: 'event', defaultSeverity: 'WARN', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'worstBuildFrameMs', 'worstRasterFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'app.performance.media': RuntimeLogSignalMetadata(owner: 'content-consumption', producers: <String>['dart', 'android', 'ios'], logKind: 'event', defaultSeverity: 'WARN', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'app.runtime.lifecycle': RuntimeLogSignalMetadata(owner: 'runtime-client-foundation', producers: <String>['dart'], logKind: 'runtime', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'data.exception.stage': RuntimeLogSignalMetadata(owner: 'runtime-data-engineering', producers: <String>['python'], logKind: 'exception', defaultSeverity: 'ERROR', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'data.runtime.stage': RuntimeLogSignalMetadata(owner: 'runtime-data-engineering', producers: <String>['python'], logKind: 'runtime', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'ops.audit.control': RuntimeLogSignalMetadata(owner: 'platform-ops-governance', producers: <String>['python'], logKind: 'audit', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'ops.deploy.stackctl': RuntimeLogSignalMetadata(owner: 'platform-ops-governance', producers: <String>['python'], logKind: 'deploy', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'ops.exception.runtime': RuntimeLogSignalMetadata(owner: 'platform-ops-governance', producers: <String>['python'], logKind: 'exception', defaultSeverity: 'ERROR', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'ops.runtime.process': RuntimeLogSignalMetadata(owner: 'platform-ops-governance', producers: <String>['python'], logKind: 'runtime', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'portal.exception.browser': RuntimeLogSignalMetadata(owner: 'product-ops-growth', producers: <String>['typescript'], logKind: 'exception', defaultSeverity: 'ERROR', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'service.access.http': RuntimeLogSignalMetadata(owner: 'system-architecture-and-engineering-guide', producers: <String>['go'], logKind: 'access', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'service.audit.control': RuntimeLogSignalMetadata(owner: 'platform-ops-governance', producers: <String>['go'], logKind: 'audit', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'service.exception.runtime': RuntimeLogSignalMetadata(owner: 'system-architecture-and-engineering-guide', producers: <String>['go'], logKind: 'exception', defaultSeverity: 'ERROR', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
    'service.runtime.process': RuntimeLogSignalMetadata(owner: 'system-architecture-and-engineering-guide', producers: <String>['go'], logKind: 'runtime', defaultSeverity: 'INFO', environments: <String>['alpha', 'beta', 'gamma', 'prod'], attributeAllowlist: <String>['source', 'exceptionType', 'stackFrameCount', 'sampledFrames', 'jankyFrames', 'worstFrameMs', 'jankThresholdMs', 'ttffMs', 'targetPositionMs', 'settledPositionMs', 'settleMs', 'droppedFrames', 'processedFrames', 'rendererMode', 'decoderQueueMode', 'decoderFallbackEnabled', 'module', 'kind', 'reason', 'failurePoint', 'inputKv', 'outputKv', 'stage', 'outcome', 'gate', 'artifactCount'], correlationKeys: <String>['requestId', 'traceId', 'spanId', 'operationId', 'pageName', 'surfaceId', 'executionId', 'workPackageId', 'environmentRunId', 'actorHash'], backend: 'elasticsearch', retentionDays: 3, sampling: 'warn_error', alert: 'runtime_signal_rate', runbook: 'runtime-diagnostics', piiClassification: 'redacted'),
  };
}
