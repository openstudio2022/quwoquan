package runtimeobservability

import (
	"context"
	"net/http"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel/trace"
)

const (
	defaultSchemaVersion = "v1"
	defaultSourceApp     = "app"
	defaultSourceService = "service"
)

type CorrelationMeta struct {
	TraceID        string
	RequestID      string
	SessionID      string
	UserID         string
	SubAccountID   string
	PageID         string
	DevicePlatform string
	AppVersion     string
}

type EndpointMeta struct {
	Origin            string
	Direction         string
	Endpoint          string
	SourceID          string
	Src               string
	Service           string
	ServiceName       string
	ServiceInstanceID string
}

func buildCorrelationMetaFromHTTP(r *http.Request) CorrelationMeta {
	meta := buildCorrelationMetaFromHeaders(r.Header)
	if meta.UserID == "" {
		meta.UserID = "anonymous"
	}
	return meta
}

func buildCorrelationMetaFromHeaders(h http.Header) CorrelationMeta {
	nowSeed := strconv.FormatInt(time.Now().UnixNano(), 36)
	traceID := h.Get("X-Trace-Id")
	if traceID == "" {
		traceID = "SVC.default.trace." + nowSeed
	}
	requestID := h.Get("X-Request-Id")
	if requestID == "" {
		requestID = "SVC.default.req." + nowSeed
	}
	sessionID := h.Get("X-Client-Session-Id")
	if sessionID == "" {
		sessionID = "sess-" + nowSeed
	}
	userID := h.Get("X-Client-User-Id")
	return CorrelationMeta{
		TraceID:        traceID,
		RequestID:      requestID,
		SessionID:      sessionID,
		UserID:         userID,
		SubAccountID:   h.Get("X-Client-Sub-Account-Id"),
		PageID:         h.Get("X-Client-Page-Id"),
		DevicePlatform: h.Get("X-Client-Device-Platform"),
		AppVersion:     h.Get("X-Client-App-Version"),
	}
}

type contextKey string

const contextKeyCorrelationMeta contextKey = "observability_correlation_meta"

func WithCorrelationMeta(ctx context.Context, meta CorrelationMeta) context.Context {
	return context.WithValue(ctx, contextKeyCorrelationMeta, meta)
}

func CorrelationMetaFromContext(ctx context.Context) (CorrelationMeta, bool) {
	v := ctx.Value(contextKeyCorrelationMeta)
	if v == nil {
		return CorrelationMeta{}, false
	}
	meta, ok := v.(CorrelationMeta)
	return meta, ok
}

func EnrichCorrelationMetaFromSpan(meta *CorrelationMeta, ctx context.Context) {
	span := trace.SpanFromContext(ctx)
	if !span.SpanContext().HasTraceID() {
		return
	}
	otelTraceID := span.SpanContext().TraceID().String()
	if meta.TraceID == "" || strings.HasPrefix(meta.TraceID, "SVC.default") {
		meta.TraceID = otelTraceID
	}
}
