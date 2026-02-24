package runtimeobservability

import (
	"net/http"
	"time"
)

type HTTPMiddlewareConfig struct {
	Service           string
	Origin            string
	Direction         string
	SourceID          string
	Src               string
	ServiceName       string
	ServiceInstanceID string
	EndpointResolver  func(r *http.Request) string
}

type responseRecorder struct {
	http.ResponseWriter
	status int
	size   int64
}

func (r *responseRecorder) WriteHeader(statusCode int) {
	r.status = statusCode
	r.ResponseWriter.WriteHeader(statusCode)
}

func (r *responseRecorder) Write(data []byte) (int, error) {
	n, err := r.ResponseWriter.Write(data)
	r.size += int64(n)
	return n, err
}

type HTTPServerMiddlewareConfig = HTTPMiddlewareConfig

func NewHTTPServerMiddleware(
	next http.Handler,
	cfg HTTPServerMiddlewareConfig,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) http.Handler {
	return HTTPServerMiddleware(cfg, ioLogger, processLogger, exceptionLogger)(next)
}

func HTTPServerMiddleware(
	cfg HTTPMiddlewareConfig,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) func(next http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			meta := buildCorrelationMetaFromHTTP(r)
			endpoint := r.URL.Path
			if cfg.EndpointResolver != nil {
				if resolved := cfg.EndpointResolver(r); resolved != "" {
					endpoint = resolved
				}
			}

			ctx := WithCorrelationMeta(r.Context(), meta)
			r = r.WithContext(ctx)

			rec := &responseRecorder{ResponseWriter: w, status: http.StatusOK}
			_ = processLogger.Write(ProcessTraceLog{
				SchemaVersion:     defaultSchemaVersion,
				Service:           cfg.Service,
				Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
				Origin:            cfg.Origin,
				Direction:         cfg.Direction,
				Endpoint:          endpoint,
				SourceID:          cfg.SourceID,
				TraceID:           meta.TraceID,
				RequestID:         meta.RequestID,
				SessionID:         meta.SessionID,
				Src:               cfg.Src,
				UserID:            meta.UserID,
				PersonaID:         meta.PersonaID,
				PageID:            meta.PageID,
				DevicePlatform:    meta.DevicePlatform,
				AppVersion:        meta.AppVersion,
				ServiceName:       cfg.ServiceName,
				ServiceInstanceID: cfg.ServiceInstanceID,
				Step:              "http_request",
				Event:             "received",
				Result:            "start",
				Level:             TraceLogLevelInfo,
			}, "", "", nil, nil)

			defer func() {
				if recovered := recover(); recovered != nil {
					rec.WriteHeader(http.StatusInternalServerError)
					_ = exceptionLogger.Write(ExceptionLog{
						SchemaVersion:     defaultSchemaVersion,
						Service:           cfg.Service,
						Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
						Origin:            cfg.Origin,
						Direction:         cfg.Direction,
						Endpoint:          endpoint,
						SourceID:          cfg.SourceID,
						TraceID:           meta.TraceID,
						RequestID:         meta.RequestID,
						SessionID:         meta.SessionID,
						Src:               cfg.Src,
						UserID:            meta.UserID,
						PersonaID:         meta.PersonaID,
						PageID:            meta.PageID,
						DevicePlatform:    meta.DevicePlatform,
						AppVersion:        meta.AppVersion,
						ServiceName:       cfg.ServiceName,
						ServiceInstanceID: cfg.ServiceInstanceID,
						ErrorCode:         "UNKNOWN.SYSTEM.internal_error",
						ErrorModule:       "UNKNOWN",
						ErrorKind:         "SYSTEM",
						ErrorReason:       "internal_error",
						UserMessage:       "系统开小差了，请稍后重试",
						DebugMessage:      "panic recovered",
						FailurePoint:      endpoint,
					}, "", "", nil, nil)
					_ = ioLogger.Write(IOAccessLog{
						SchemaVersion:     defaultSchemaVersion,
						Service:           cfg.Service,
						Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
						Origin:            cfg.Origin,
						Direction:         cfg.Direction,
						Endpoint:          endpoint,
						SourceID:          cfg.SourceID,
						TraceID:           meta.TraceID,
						RequestID:         meta.RequestID,
						SessionID:         meta.SessionID,
						Src:               cfg.Src,
						UserID:            meta.UserID,
						PersonaID:         meta.PersonaID,
						PageID:            meta.PageID,
						DevicePlatform:    meta.DevicePlatform,
						AppVersion:        meta.AppVersion,
						ServiceName:       cfg.ServiceName,
						ServiceInstanceID: cfg.ServiceInstanceID,
						Status:            "failed",
						DurationMs:        time.Since(start).Milliseconds(),
						ErrorCode:         "UNKNOWN.SYSTEM.internal_error",
						MessageSize:       rec.size,
					})
				}
			}()

			next.ServeHTTP(rec, r)
			status := "success"
			errorCode := ""
			if rec.status >= 500 {
				status = "failed"
				errorCode = "UNKNOWN.SYSTEM.internal_error"
				_ = exceptionLogger.Write(ExceptionLog{
					SchemaVersion:     defaultSchemaVersion,
					Service:           cfg.Service,
					Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
					Origin:            cfg.Origin,
					Direction:         cfg.Direction,
					Endpoint:          endpoint,
					SourceID:          cfg.SourceID,
					TraceID:           meta.TraceID,
					RequestID:         meta.RequestID,
					SessionID:         meta.SessionID,
					Src:               cfg.Src,
					UserID:            meta.UserID,
					PersonaID:         meta.PersonaID,
					PageID:            meta.PageID,
					DevicePlatform:    meta.DevicePlatform,
					AppVersion:        meta.AppVersion,
					ServiceName:       cfg.ServiceName,
					ServiceInstanceID: cfg.ServiceInstanceID,
					ErrorCode:         errorCode,
					ErrorModule:       "UNKNOWN",
					ErrorKind:         "SYSTEM",
					ErrorReason:       "internal_error",
					UserMessage:       "服务异常，请稍后重试",
					DebugMessage:      "http status >= 500",
					FailurePoint:      endpoint,
				}, "", "", nil, nil)
			}

			_ = processLogger.Write(ProcessTraceLog{
				SchemaVersion:     defaultSchemaVersion,
				Service:           cfg.Service,
				Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
				Origin:            cfg.Origin,
				Direction:         cfg.Direction,
				Endpoint:          endpoint,
				SourceID:          cfg.SourceID,
				TraceID:           meta.TraceID,
				RequestID:         meta.RequestID,
				SessionID:         meta.SessionID,
				Src:               cfg.Src,
				UserID:            meta.UserID,
				PersonaID:         meta.PersonaID,
				PageID:            meta.PageID,
				DevicePlatform:    meta.DevicePlatform,
				AppVersion:        meta.AppVersion,
				ServiceName:       cfg.ServiceName,
				ServiceInstanceID: cfg.ServiceInstanceID,
				Step:              "http_request",
				Event:             "completed",
				Result:            status,
				Level:             TraceLogLevelInfo,
			}, "", "", nil, nil)

			_ = ioLogger.Write(IOAccessLog{
				SchemaVersion:     defaultSchemaVersion,
				Service:           cfg.Service,
				Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
				Origin:            cfg.Origin,
				Direction:         cfg.Direction,
				Endpoint:          endpoint,
				SourceID:          cfg.SourceID,
				TraceID:           meta.TraceID,
				RequestID:         meta.RequestID,
				SessionID:         meta.SessionID,
				Src:               cfg.Src,
				UserID:            meta.UserID,
				PersonaID:         meta.PersonaID,
				PageID:            meta.PageID,
				DevicePlatform:    meta.DevicePlatform,
				AppVersion:        meta.AppVersion,
				ServiceName:       cfg.ServiceName,
				ServiceInstanceID: cfg.ServiceInstanceID,
				Status:            status,
				DurationMs:        time.Since(start).Milliseconds(),
				ErrorCode:         errorCode,
				MessageSize:       rec.size,
			})
		})
	}
}

