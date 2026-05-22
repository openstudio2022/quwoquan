package runtimeobservability

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"

	rterr "quwoquan_service/runtime/errors"
)

var (
	httpRequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "http",
		Subsystem: "server",
		Name:      "requests_total",
		Help:      "Total HTTP requests by service, route, method, and status code.",
	}, []string{"service", "route", "method", "status"})

	httpDurationSeconds = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "http",
		Subsystem: "server",
		Name:      "duration_seconds",
		Help:      "HTTP request duration in seconds.",
		Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10},
	}, []string{"service", "route", "method"})

	httpInflightRequests = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "http",
		Subsystem: "server",
		Name:      "inflight_requests",
		Help:      "Number of in-flight HTTP requests.",
	}, []string{"service"})

	httpResponseBytes = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "http",
		Subsystem: "server",
		Name:      "response_bytes",
		Help:      "HTTP response size in bytes.",
		Buckets:   []float64{100, 1000, 10000, 100000, 1e6, 1e7},
	}, []string{"service", "route", "method"})

	httpErrorCodesTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "http",
		Subsystem: "server",
		Name:      "error_codes_total",
		Help:      "HTTP error responses by structured error code.",
	}, []string{"service", "error_code", "module", "kind"})
)

var statusBuckets atomic.Value

func init() {
	statusBuckets.Store(make(map[string]string, 64))
}

func statusCodeStr(code int) string {
	m := statusBuckets.Load().(map[string]string)
	if s, ok := m[strconv.Itoa(code)]; ok {
		return s
	}
	s := strconv.Itoa(code)
	newM := make(map[string]string, len(m)+1)
	for k, v := range m {
		newM[k] = v
	}
	newM[s] = s
	statusBuckets.Store(newM)
	return s
}

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
	wrote  bool
	body   []byte
}

func (r *responseRecorder) WriteHeader(statusCode int) {
	if r.wrote {
		return
	}
	r.status = statusCode
	r.wrote = true
	r.ResponseWriter.WriteHeader(statusCode)
}

func (r *responseRecorder) Write(data []byte) (int, error) {
	if !r.wrote {
		r.status = http.StatusOK
		r.wrote = true
	}
	n, err := r.ResponseWriter.Write(data)
	r.size += int64(n)
	if len(r.body) < 64*1024 {
		remaining := 64*1024 - len(r.body)
		if len(data) < remaining {
			remaining = len(data)
		}
		r.body = append(r.body, data[:remaining]...)
	}
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

			svc := cfg.Service
			method := r.Method
			httpInflightRequests.WithLabelValues(svc).Inc()
			defer httpInflightRequests.WithLabelValues(svc).Dec()

			rec := &responseRecorder{ResponseWriter: w, status: http.StatusOK}

			// Extract W3C traceparent from inbound headers for distributed tracing.
			prop := otel.GetTextMapPropagator()
			ctx := prop.Extract(r.Context(), propagation.HeaderCarrier(r.Header))
			ctx, span := otel.Tracer("http.server").Start(ctx, "http.request",
				trace.WithAttributes(
					attribute.String("http.method", r.Method),
					attribute.String("http.route", endpoint),
					attribute.String("service.name", svc),
				),
				trace.WithSpanKind(trace.SpanKindServer),
			)
			defer func() {
				span.SetAttributes(attribute.Int("http.status_code", rec.status))
				if rec.status >= 500 {
					span.SetStatus(codes.Error, "HTTP "+statusCodeStr(rec.status))
				}
				span.End()
			}()

			EnrichCorrelationMetaFromSpan(&meta, ctx)
			ctx = WithCorrelationMeta(ctx, meta)
			r = r.WithContext(ctx)
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
				SubAccountID:      meta.SubAccountID,
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
					if !rec.wrote {
						rterr.WriteHTTPError(
							rec,
							rterr.NewAppError(
								rterr.NewCode(rterr.ModuleUnknown, rterr.KindSystem, rterr.DefaultInternalReason),
								rterr.DefaultUserMessage,
								fmt.Sprintf("panic recovered: %v", recovered),
							),
							rterr.HTTPWriteOptionsFromRequest(r),
						)
					}
					details := exceptionDetails{
						code:           "UNKNOWN.SYSTEM.internal_error",
						module:         "UNKNOWN",
						kind:           "SYSTEM",
						reason:         "internal_error",
						runtimeOrigin:  "system",
						runtimeNature:  "bug",
						userMessage:    "系统开小差了，请稍后重试",
						debugMessage:   "panic recovered",
						failurePoint:   endpoint,
						businessObject: "cloud_request",
						functionModule: "runtime_panic",
					}
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
						SubAccountID:      meta.SubAccountID,
						PageID:            meta.PageID,
						DevicePlatform:    meta.DevicePlatform,
						AppVersion:        meta.AppVersion,
						ServiceName:       cfg.ServiceName,
						ServiceInstanceID: cfg.ServiceInstanceID,
						ErrorCode:         details.code,
						ErrorModule:       details.module,
						ErrorKind:         details.kind,
						ErrorReason:       details.reason,
						RuntimeOrigin:     details.runtimeOrigin,
						RuntimeNature:     details.runtimeNature,
						UserMessage:       details.userMessage,
						DebugMessage:      details.debugMessage,
						FailurePoint:      details.failurePoint,
						BusinessObject:    details.businessObject,
						FunctionModule:    details.functionModule,
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
						SubAccountID:      meta.SubAccountID,
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
			var errDetails exceptionDetails
			if rec.status >= 400 {
				errDetails = exceptionDetailsFromResponse(rec, endpoint)
				errorCode = errDetails.code
			}
			if rec.status >= 500 {
				status = "failed"
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
					SubAccountID:      meta.SubAccountID,
					PageID:            meta.PageID,
					DevicePlatform:    meta.DevicePlatform,
					AppVersion:        meta.AppVersion,
					ServiceName:       cfg.ServiceName,
					ServiceInstanceID: cfg.ServiceInstanceID,
					ErrorCode:         errDetails.code,
					ErrorModule:       errDetails.module,
					ErrorKind:         errDetails.kind,
					ErrorReason:       errDetails.reason,
					RuntimeOrigin:     errDetails.runtimeOrigin,
					RuntimeNature:     errDetails.runtimeNature,
					UserMessage:       errDetails.userMessage,
					DebugMessage:      errDetails.debugMessage,
					FailurePoint:      errDetails.failurePoint,
					BusinessObject:    errDetails.businessObject,
					FunctionModule:    errDetails.functionModule,
				}, "", "", nil, nil)
			}

			elapsed := time.Since(start).Seconds()
			statusStr := statusCodeStr(rec.status)
			httpRequestsTotal.WithLabelValues(svc, endpoint, method, statusStr).Inc()
			httpDurationSeconds.WithLabelValues(svc, endpoint, method).Observe(elapsed)
			httpResponseBytes.WithLabelValues(svc, endpoint, method).Observe(float64(rec.size))
			if rec.status >= 400 && errorCode != "" {
				mod, knd, _ := splitRuntimeErrorCode(errorCode)
				httpErrorCodesTotal.WithLabelValues(svc, errorCode, mod, knd).Inc()
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
				SubAccountID:      meta.SubAccountID,
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
				SubAccountID:      meta.SubAccountID,
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

type exceptionDetails struct {
	code           string
	module         string
	kind           string
	reason         string
	runtimeOrigin  string
	runtimeNature  string
	userMessage    string
	debugMessage   string
	failurePoint   string
	businessObject string
	functionModule string
}

func exceptionDetailsFromResponse(rec *responseRecorder, endpoint string) exceptionDetails {
	details := defaultHTTPExceptionDetails(endpoint)
	var resp rterr.ErrorResponse
	if len(rec.body) == 0 || json.Unmarshal(rec.body, &resp) != nil || resp.Code == "" {
		return details
	}
	module, kind, reason := splitRuntimeErrorCode(resp.Code)
	details.code = resp.Code
	details.module = firstNonEmpty(module, resp.Module, details.module)
	details.kind = firstNonEmpty(kind, resp.Kind, details.kind)
	details.reason = firstNonEmpty(reason, resp.Reason, details.reason)
	details.runtimeOrigin = firstNonEmpty(resp.Origin, details.runtimeOrigin)
	details.runtimeNature = firstNonEmpty(resp.Nature, details.runtimeNature)
	details.userMessage = firstNonEmpty(resp.UserMessage, details.userMessage)
	if resp.DebugMessage != "" && resp.DebugMessage != rterr.RedactedDebugMessage {
		details.debugMessage = resp.DebugMessage
	}
	if resp.Location.BusinessObject != "" {
		details.businessObject = resp.Location.BusinessObject
	}
	if resp.Location.FunctionModule != "" {
		details.functionModule = resp.Location.FunctionModule
	}
	return details
}

func defaultHTTPExceptionDetails(endpoint string) exceptionDetails {
	return exceptionDetails{
		code:           "UNKNOWN.SYSTEM.internal_error",
		module:         "UNKNOWN",
		kind:           "SYSTEM",
		reason:         "internal_error",
		runtimeOrigin:  "system",
		runtimeNature:  "bug",
		userMessage:    "服务异常，请稍后重试",
		debugMessage:   "http status >= 500",
		failurePoint:   endpoint,
		businessObject: "cloud_request",
		functionModule: "http_middleware",
	}
}

func splitRuntimeErrorCode(code string) (string, string, string) {
	parts := strings.SplitN(code, ".", 3)
	if len(parts) != 3 {
		return "", "", ""
	}
	return parts[0], parts[1], parts[2]
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
