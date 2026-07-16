package runtimeobservability

import (
	"encoding/json"
	"fmt"
	"strings"
)

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

func formatDelimitedLog(kind string, payload map[string]any) string {
	fields := logFieldOrder(kind)
	if len(fields) == 0 {
		fields = []string{"ts", "level", "msg"}
	}
	values := make([]string, 0, len(fields))
	message := compactLogMessage(payload)
	for _, field := range fields {
		if field == "msg" {
			values = append(values, message)
		} else {
			values = append(values, compactPrefixField(payload[field]))
		}
	}
	msgLines := strings.Split(strings.ReplaceAll(values[len(values)-1], "\r\n", "\n"), "\n")
	line := strings.Join(append(values[:len(values)-1], msgLines[0]), ",")
	for _, continuation := range msgLines[1:] {
		line += "\n\t" + continuation
	}
	return line
}

func logFieldOrder(kind string) []string {
	switch kind {
	case "access":
		return []string{"ts", "level", "method", "route", "status", "durMs", "req", "trace", "msg"}
	case "runtime", "event":
		return []string{"ts", "level", "event", "result", "req", "trace", "msg"}
	case "exception":
		return []string{"ts", "level", "err", "req", "trace", "msg"}
	case "audit":
		return []string{"ts", "level", "action", "target", "result", "msg"}
	default:
		return []string{"ts", "level", "msg"}
	}
}

func compactLogMessage(payload map[string]any) string {
	message := fmt.Sprint(payload["msg"])
	attrs, ok := payload["attrs"]
	if !ok || attrs == nil {
		return message
	}
	encoded, err := json.Marshal(attrs)
	if err != nil || len(encoded) == 0 || string(encoded) == "{}" {
		return message
	}
	if strings.TrimSpace(message) == "" {
		return "attrs=" + string(encoded)
	}
	return message + " attrs=" + string(encoded)
}

func compactPrefixField(value any) string {
	if value == nil {
		return ""
	}
	text := fmt.Sprint(value)
	text = strings.ReplaceAll(text, "\r\n", " ")
	text = strings.ReplaceAll(text, "\n", " ")
	text = strings.ReplaceAll(text, ",", "%2C")
	return text
}
