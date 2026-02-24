package runtimeobservability

import (
	"fmt"
	"net"
	"net/http"
	"time"
)

type HTTPClientMiddlewareConfig struct {
	Service           string
	Origin            string
	Direction         string
	SourceID          string
	Src               string
	ServiceName       string
	ServiceInstanceID string
	EndpointResolver  func(r *http.Request) string
}

type LoggedRoundTripper struct {
	base            http.RoundTripper
	cfg             HTTPClientMiddlewareConfig
	ioLogger        *IOAccessLogger
	processLogger   *ProcessTraceLogger
	exceptionLogger *ExceptionLogger
}

func NewLoggedRoundTripper(
	base http.RoundTripper,
	cfg HTTPClientMiddlewareConfig,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) *LoggedRoundTripper {
	if base == nil {
		base = http.DefaultTransport
	}
	return &LoggedRoundTripper{
		base:            base,
		cfg:             cfg,
		ioLogger:        ioLogger,
		processLogger:   processLogger,
		exceptionLogger: exceptionLogger,
	}
}

func (rt *LoggedRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	start := time.Now()
	meta, ok := CorrelationMetaFromContext(req.Context())
	if !ok {
		meta = buildCorrelationMetaFromHeaders(req.Header)
	}

	endpoint := req.URL.Path
	if rt.cfg.EndpointResolver != nil {
		if resolved := rt.cfg.EndpointResolver(req); resolved != "" {
			endpoint = resolved
		}
	}

	// Propagate unified tracing headers for outbound service calls.
	if req.Header.Get("X-Trace-Id") == "" {
		req.Header.Set("X-Trace-Id", meta.TraceID)
	}
	if req.Header.Get("X-Request-Id") == "" {
		req.Header.Set("X-Request-Id", meta.RequestID)
	}
	if req.Header.Get("X-Client-Session-Id") == "" {
		req.Header.Set("X-Client-Session-Id", meta.SessionID)
	}
	if req.Header.Get("X-Persona-Id") == "" && meta.PersonaID != "" {
		req.Header.Set("X-Persona-Id", meta.PersonaID)
	}
	if req.Header.Get("X-Client-Page-Id") == "" && meta.PageID != "" {
		req.Header.Set("X-Client-Page-Id", meta.PageID)
	}

	_ = rt.processLogger.Write(ProcessTraceLog{
		SchemaVersion:     defaultSchemaVersion,
		Service:           rt.cfg.Service,
		Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
		Origin:            rt.cfg.Origin,
		Direction:         rt.cfg.Direction,
		Endpoint:          endpoint,
		SourceID:          rt.cfg.SourceID,
		TraceID:           meta.TraceID,
		RequestID:         meta.RequestID,
		SessionID:         meta.SessionID,
		Src:               rt.cfg.Src,
		UserID:            meta.UserID,
		PersonaID:         meta.PersonaID,
		PageID:            meta.PageID,
		DevicePlatform:    meta.DevicePlatform,
		AppVersion:        meta.AppVersion,
		ServiceName:       rt.cfg.ServiceName,
		ServiceInstanceID: rt.cfg.ServiceInstanceID,
		Step:              "http_client_call",
		Event:             "start",
		Result:            "outbound",
		Level:             TraceLogLevelInfo,
	}, "", "", nil, nil)

	resp, err := rt.base.RoundTrip(req)
	status := "success"
	errorCode := ""
	var messageSize int64
	if resp != nil && resp.ContentLength > 0 {
		messageSize = resp.ContentLength
	}

	if err != nil {
		status = "failed"
		errorCode = "UNKNOWN.NETWORK.unavailable"
		if ne, ok := err.(net.Error); ok && ne.Timeout() {
			status = "timeout"
			errorCode = "UNKNOWN.NETWORK.timeout"
		}
		_ = rt.exceptionLogger.Write(ExceptionLog{
			SchemaVersion:     defaultSchemaVersion,
			Service:           rt.cfg.Service,
			Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
			Origin:            rt.cfg.Origin,
			Direction:         rt.cfg.Direction,
			Endpoint:          endpoint,
			SourceID:          rt.cfg.SourceID,
			TraceID:           meta.TraceID,
			RequestID:         meta.RequestID,
			SessionID:         meta.SessionID,
			Src:               rt.cfg.Src,
			UserID:            meta.UserID,
			PersonaID:         meta.PersonaID,
			PageID:            meta.PageID,
			DevicePlatform:    meta.DevicePlatform,
			AppVersion:        meta.AppVersion,
			ServiceName:       rt.cfg.ServiceName,
			ServiceInstanceID: rt.cfg.ServiceInstanceID,
			ErrorCode:         errorCode,
			ErrorModule:       "UNKNOWN",
			ErrorKind:         "NETWORK",
			ErrorReason:       "unavailable",
			UserMessage:       "下游服务不可用，请稍后重试",
			DebugMessage:      err.Error(),
			FailurePoint:      endpoint,
		}, "", "", nil, nil)
	} else if resp != nil && resp.StatusCode >= http.StatusInternalServerError {
		status = "failed"
		errorCode = "UNKNOWN.SYSTEM.internal_error"
		_ = rt.exceptionLogger.Write(ExceptionLog{
			SchemaVersion:     defaultSchemaVersion,
			Service:           rt.cfg.Service,
			Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
			Origin:            rt.cfg.Origin,
			Direction:         rt.cfg.Direction,
			Endpoint:          endpoint,
			SourceID:          rt.cfg.SourceID,
			TraceID:           meta.TraceID,
			RequestID:         meta.RequestID,
			SessionID:         meta.SessionID,
			Src:               rt.cfg.Src,
			UserID:            meta.UserID,
			PersonaID:         meta.PersonaID,
			PageID:            meta.PageID,
			DevicePlatform:    meta.DevicePlatform,
			AppVersion:        meta.AppVersion,
			ServiceName:       rt.cfg.ServiceName,
			ServiceInstanceID: rt.cfg.ServiceInstanceID,
			ErrorCode:         errorCode,
			ErrorModule:       "UNKNOWN",
			ErrorKind:         "SYSTEM",
			ErrorReason:       "internal_error",
			UserMessage:       "下游服务异常，请稍后重试",
			DebugMessage:      fmt.Sprintf("status=%d", resp.StatusCode),
			FailurePoint:      endpoint,
		}, "", "", nil, nil)
	}

	_ = rt.processLogger.Write(ProcessTraceLog{
		SchemaVersion:     defaultSchemaVersion,
		Service:           rt.cfg.Service,
		Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
		Origin:            rt.cfg.Origin,
		Direction:         rt.cfg.Direction,
		Endpoint:          endpoint,
		SourceID:          rt.cfg.SourceID,
		TraceID:           meta.TraceID,
		RequestID:         meta.RequestID,
		SessionID:         meta.SessionID,
		Src:               rt.cfg.Src,
		UserID:            meta.UserID,
		PersonaID:         meta.PersonaID,
		PageID:            meta.PageID,
		DevicePlatform:    meta.DevicePlatform,
		AppVersion:        meta.AppVersion,
		ServiceName:       rt.cfg.ServiceName,
		ServiceInstanceID: rt.cfg.ServiceInstanceID,
		Step:              "http_client_call",
		Event:             "end",
		Result:            status,
		Level:             TraceLogLevelInfo,
	}, "", "", nil, nil)

	_ = rt.ioLogger.Write(IOAccessLog{
		SchemaVersion:     defaultSchemaVersion,
		Service:           rt.cfg.Service,
		Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
		Origin:            rt.cfg.Origin,
		Direction:         rt.cfg.Direction,
		Endpoint:          endpoint,
		SourceID:          rt.cfg.SourceID,
		TraceID:           meta.TraceID,
		RequestID:         meta.RequestID,
		SessionID:         meta.SessionID,
		Src:               rt.cfg.Src,
		UserID:            meta.UserID,
		PersonaID:         meta.PersonaID,
		PageID:            meta.PageID,
		DevicePlatform:    meta.DevicePlatform,
		AppVersion:        meta.AppVersion,
		ServiceName:       rt.cfg.ServiceName,
		ServiceInstanceID: rt.cfg.ServiceInstanceID,
		Status:            status,
		DurationMs:        time.Since(start).Milliseconds(),
		ErrorCode:         errorCode,
		MessageSize:       messageSize,
	})

	return resp, err
}

