// Code generated from contracts/metadata/_shared/runtime_observability.yaml. DO NOT EDIT.

package runtimeobservability

const ObservabilitySchema = "observability.slim"

type CatalogSignalMetadata struct {
	Owner              string
	Producers          []string
	LogKind            string
	DefaultSeverity    string
	Environments       []string
	AttributeAllowlist []string
	CorrelationKeys    []string
	Backend            string
	RetentionDays      int
	Sampling           string
	Alert              string
	Runbook            string
	PIIClassification  string
}

var CatalogLogKinds = map[string]struct{}{
	"deploy":    {},
	"runtime":   {},
	"access":    {},
	"event":     {},
	"exception": {},
	"audit":     {},
}

var CatalogSeverityLevels = map[string]struct{}{
	"DEBUG": {},
	"INFO":  {},
	"WARN":  {},
	"ERROR": {},
}

var CatalogSignals = map[string]struct{}{
	"app.access.http":           {},
	"app.exception.flutter":     {},
	"app.exception.platform":    {},
	"app.performance.anr":       {},
	"app.performance.frame":     {},
	"app.performance.media":     {},
	"app.runtime.lifecycle":     {},
	"data.exception.stage":      {},
	"data.runtime.stage":        {},
	"ops.audit.control":         {},
	"ops.deploy.stackctl":       {},
	"ops.exception.runtime":     {},
	"ops.runtime.process":       {},
	"portal.exception.browser":  {},
	"service.access.http":       {},
	"service.audit.control":     {},
	"service.exception.runtime": {},
	"service.runtime.process":   {},
}

var CatalogForbiddenFields = map[string]struct{}{
	"schemaVersion":   {},
	"eventVersion":    {},
	"contractVersion": {},
	"protocolVersion": {},
	"releaseVersion":  {},
	"releaseId":       {},
	"dataReleaseId":   {},
}

var CatalogFailureCodes = map[string]string{
	"app_native_previous_crash": "APP.RUNTIME.native_previous_crash",
	"app_uncaught_flutter":      "APP.RUNTIME.uncaught_exception",
	"app_uncaught_platform":     "APP.RUNTIME.uncaught_platform_exception",
	"data_stage_failure":        "DATA.RUNTIME.stage_failed",
	"portal_uncaught_browser":   "PORTAL.RUNTIME.uncaught_browser_exception",
	"service_log_encoding":      "SERVICE.RUNTIME.log_encoding_failed",
}

var CatalogForbiddenAttributeKeys = map[string]struct{}{
	"authorization":   {},
	"password":        {},
	"passwd":          {},
	"secret":          {},
	"token":           {},
	"apiKey":          {},
	"credential":      {},
	"cookie":          {},
	"phone":           {},
	"email":           {},
	"ssid":            {},
	"ip":              {},
	"preciseLocation": {},
	"sessionId":       {},
}

var CatalogHighCardinalityMetricKeys = map[string]struct{}{
	"userId":    {},
	"sessionId": {},
	"requestId": {},
	"traceId":   {},
	"rawPath":   {},
}

const CatalogMaxBatchItems = 50

const CatalogMaxCanonicalBodyBytes = 131072

const CatalogMaxMessageBytes = 2048

const CatalogMaxAttributes = 24

const CatalogMaxAttributesBytes = 4096

const CatalogMaxAttributeKeyLength = 64

const CatalogMaxAttributeValueLength = 512

const CatalogRawRetentionDays = 3

const CatalogAppBufferCapacity = 200

const CatalogAppDeadLetterCapacity = 100

const CatalogServiceSpoolMaxBatches = 2000

const CatalogServiceDLQMaxBatches = 500

const CatalogDeliveryTTLHours = 72

const CatalogRetryBaseSeconds = 5

const CatalogRetryMaxSeconds = 300

const CatalogRetryMaxExponent = 6

const CatalogRetryJitterPercent = 25

var CatalogEnvelopeRequiredFields = []string{"schema", "occurredAt", "observedAt", "logKind", "severity", "signal", "message", "resource"}

var CatalogEnvelopeOptionalFields = []string{"recordId", "correlation", "step", "event", "result", "method", "route", "status", "durationMs", "action", "target", "errorCode", "fingerprint", "attributes"}

var CatalogResourceRequiredFields = []string{"sourceType", "service"}

var CatalogResourceOptionalFields = []string{"environment", "component", "appVersion", "service.version"}

var CatalogCorrelationOptionalFields = []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"}

var CatalogFieldOrder = map[string][]string{
	"deploy":    {"step", "result"},
	"runtime":   {"event", "result"},
	"access":    {"method", "route", "status", "durationMs"},
	"event":     {"event", "result"},
	"exception": {"errorCode"},
	"audit":     {"action", "target", "result"},
}

var CatalogRequiredFields = map[string]map[string]struct{}{
	"deploy":    {"step": {}, "result": {}},
	"runtime":   {"event": {}, "result": {}},
	"access":    {"method": {}, "route": {}, "status": {}, "durationMs": {}},
	"event":     {"event": {}, "result": {}},
	"exception": {"errorCode": {}},
	"audit":     {"action": {}, "target": {}, "result": {}},
}

var CatalogSignalLogKinds = map[string]string{
	"app.access.http":           "access",
	"app.exception.flutter":     "exception",
	"app.exception.platform":    "exception",
	"app.performance.anr":       "event",
	"app.performance.frame":     "event",
	"app.performance.media":     "event",
	"app.runtime.lifecycle":     "runtime",
	"data.exception.stage":      "exception",
	"data.runtime.stage":        "runtime",
	"ops.audit.control":         "audit",
	"ops.deploy.stackctl":       "deploy",
	"ops.exception.runtime":     "exception",
	"ops.runtime.process":       "runtime",
	"portal.exception.browser":  "exception",
	"service.access.http":       "access",
	"service.audit.control":     "audit",
	"service.exception.runtime": "exception",
	"service.runtime.process":   "runtime",
}

var CatalogSignalDefaultSeverities = map[string]string{
	"app.access.http":           "INFO",
	"app.exception.flutter":     "ERROR",
	"app.exception.platform":    "ERROR",
	"app.performance.anr":       "ERROR",
	"app.performance.frame":     "WARN",
	"app.performance.media":     "WARN",
	"app.runtime.lifecycle":     "INFO",
	"data.exception.stage":      "ERROR",
	"data.runtime.stage":        "INFO",
	"ops.audit.control":         "INFO",
	"ops.deploy.stackctl":       "INFO",
	"ops.exception.runtime":     "ERROR",
	"ops.runtime.process":       "INFO",
	"portal.exception.browser":  "ERROR",
	"service.access.http":       "INFO",
	"service.audit.control":     "INFO",
	"service.exception.runtime": "ERROR",
	"service.runtime.process":   "INFO",
}

var CatalogSignalRegistry = map[string]CatalogSignalMetadata{
	"app.access.http": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "access",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.exception.flutter": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.exception.platform": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart", "android", "ios"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.performance.anr": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "event",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "stallMs", "anrThresholdMs", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.performance.frame": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "event",
		DefaultSeverity:    "WARN",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "worstBuildFrameMs", "worstRasterFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.performance.media": {
		Owner:              "content-consumption",
		Producers:          []string{"dart", "android", "ios"},
		LogKind:            "event",
		DefaultSeverity:    "WARN",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"app.runtime.lifecycle": {
		Owner:              "runtime-client-foundation",
		Producers:          []string{"dart"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"data.exception.stage": {
		Owner:              "runtime-data-engineering",
		Producers:          []string{"python"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"data.runtime.stage": {
		Owner:              "runtime-data-engineering",
		Producers:          []string{"python"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.audit.control": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "audit",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.deploy.stackctl": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "deploy",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.exception.runtime": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"ops.runtime.process": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"python"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"portal.exception.browser": {
		Owner:              "product-ops-growth",
		Producers:          []string{"typescript"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.access.http": {
		Owner:              "system-architecture-and-engineering-guide",
		Producers:          []string{"go"},
		LogKind:            "access",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.audit.control": {
		Owner:              "platform-ops-governance",
		Producers:          []string{"go"},
		LogKind:            "audit",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.exception.runtime": {
		Owner:              "system-architecture-and-engineering-guide",
		Producers:          []string{"go"},
		LogKind:            "exception",
		DefaultSeverity:    "ERROR",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
	"service.runtime.process": {
		Owner:              "system-architecture-and-engineering-guide",
		Producers:          []string{"go"},
		LogKind:            "runtime",
		DefaultSeverity:    "INFO",
		Environments:       []string{"alpha", "beta", "gamma", "prod"},
		AttributeAllowlist: []string{"source", "exceptionType", "stackFrameCount", "sampledFrames", "jankyFrames", "worstFrameMs", "jankThresholdMs", "ttffMs", "targetPositionMs", "settledPositionMs", "settleMs", "droppedFrames", "processedFrames", "rendererMode", "decoderQueueMode", "decoderFallbackEnabled", "module", "kind", "reason", "failurePoint", "inputKv", "outputKv", "stage", "outcome", "gate", "artifactCount"},
		CorrelationKeys:    []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"},
		Backend:            "elasticsearch",
		RetentionDays:      3,
		Sampling:           "warn_error",
		Alert:              "runtime_signal_rate",
		Runbook:            "runtime-diagnostics",
		PIIClassification:  "redacted",
	},
}
