package runtimeobservability

import "strings"

func compactIOAccessLog(entry IOAccessLog) map[string]any {
	payload := map[string]any{
		"ts":     entry.TS,
		"level":  levelForResult(entry.Status),
		"msg":    entry.Endpoint,
		"method": compactAccessMethod(entry),
		"route":  entry.Endpoint,
		"status": entry.Status,
		"durMs":  entry.DurationMs,
		"req":    entry.Req,
		"trace":  entry.Trace,
		"resource": serviceLogResource(
			entry.ServiceName,
			entry.Service,
			entry.Origin,
			entry.AppVersion,
		),
		"correlation": serviceLogCorrelation(entry.Req, entry.Trace, entry.PageID),
	}
	if entry.ErrorCode != "" {
		payload["err"] = entry.ErrorCode
	}
	return compactMap(payload)
}

func compactProcessTraceLog(entry ProcessTraceLog) map[string]any {
	payload := map[string]any{
		"ts":     entry.TS,
		"level":  strings.ToUpper(entry.Level),
		"msg":    entry.Step,
		"event":  entry.Event,
		"result": entry.Result,
		"req":    entry.Req,
		"trace":  entry.Trace,
		"resource": serviceLogResource(
			entry.ServiceName,
			entry.Service,
			entry.Origin,
			entry.AppVersion,
		),
		"correlation": serviceLogCorrelation(entry.Req, entry.Trace, entry.PageID),
	}
	attrs := map[string]any{}
	if len(entry.IO.InputKV) > 0 {
		attrs["inputKv"] = entry.IO.InputKV
	}
	if len(entry.IO.OutputKV) > 0 {
		attrs["outputKv"] = entry.IO.OutputKV
	}
	if len(attrs) > 0 {
		payload["attrs"] = attrs
	}
	return compactMap(payload)
}

func compactExceptionLog(entry ExceptionLog) map[string]any {
	message := entry.UserMessage
	if message == "" {
		message = entry.DebugMessage
	}
	payload := map[string]any{
		"ts":    entry.TS,
		"level": "ERROR",
		"msg":   message,
		"err":   entry.ErrorCode,
		"req":   entry.Req,
		"trace": entry.Trace,
		"resource": serviceLogResource(
			entry.ServiceName,
			entry.Service,
			entry.Origin,
			entry.AppVersion,
		),
		"correlation": serviceLogCorrelation(entry.Req, entry.Trace, entry.PageID),
	}
	attrs := map[string]any{
		"module":       entry.ErrorModule,
		"kind":         entry.ErrorKind,
		"reason":       entry.ErrorReason,
		"failurePoint": entry.FailurePoint,
	}
	if len(entry.IO.InputKV) > 0 {
		attrs["inputKv"] = entry.IO.InputKV
	}
	if len(entry.IO.OutputKV) > 0 {
		attrs["outputKv"] = entry.IO.OutputKV
	}
	payload["attrs"] = compactMap(attrs)
	if entry.StackHash != "" || entry.FailurePoint != "" {
		payload["fingerprint"] = exceptionFingerprint(
			entry.ErrorCode,
			entry.FailurePoint,
			entry.StackHash,
		)
	}
	return compactMap(payload)
}

func levelForResult(result string) string {
	switch result {
	case "failed", "timeout":
		return "ERROR"
	case "retry":
		return "WARN"
	default:
		return "INFO"
	}
}

func compactAccessMethod(entry IOAccessLog) string {
	if strings.TrimSpace(entry.Method) != "" {
		return strings.ToUpper(entry.Method)
	}
	if strings.Contains(entry.Origin, ".mq") {
		return "MQ"
	}
	if strings.Contains(entry.Origin, ".grpc") {
		return "GRPC"
	}
	if strings.Contains(entry.Origin, ".http") {
		return "HTTP"
	}
	if strings.TrimSpace(entry.Direction) != "" {
		return strings.ToUpper(entry.Direction)
	}
	return "IO"
}

func compactMap(input map[string]any) map[string]any {
	output := map[string]any{}
	for key, value := range input {
		switch typed := value.(type) {
		case string:
			if strings.TrimSpace(typed) != "" {
				output[key] = typed
			}
		case int:
			output[key] = typed
		case int64:
			output[key] = typed
		case map[string]any:
			if len(typed) > 0 {
				output[key] = typed
			}
		default:
			if value != nil {
				output[key] = value
			}
		}
	}
	return output
}

func formatRuntimeLog(kind string, payload map[string]any) string {
	return formatCanonicalRuntimeLog(kind, payload)
}

func serviceLogResource(
	serviceName string,
	service string,
	component string,
	appVersion string,
) map[string]any {
	return compactMap(map[string]any{
		"sourceType": "service",
		"service":    firstNonEmpty(serviceName, service, "runtime-observability"),
		"component":  component,
		"service.version": appVersion,
	})
}

func serviceLogCorrelation(
	requestID string,
	traceID string,
	pageName string,
) map[string]any {
	return compactMap(map[string]any{
		"requestId": requestID,
		"traceId":   traceID,
		"pageName":  pageName,
	})
}

func exceptionFingerprint(errorCode string, failurePoint string, stackHash string) string {
	parts := []string{strings.TrimSpace(errorCode), strings.TrimSpace(failurePoint), strings.TrimSpace(stackHash)}
	return strings.Join(parts, ":")
}
