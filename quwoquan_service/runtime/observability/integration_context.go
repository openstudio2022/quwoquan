package runtimeobservability

import (
	"context"
	"net/http"
	"strconv"
	"time"
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
	PersonaID      string
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
	userID := h.Get("X-User-Id")
	return CorrelationMeta{
		TraceID:        traceID,
		RequestID:      requestID,
		SessionID:      sessionID,
		UserID:         userID,
		PersonaID:      h.Get("X-Persona-Id"),
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

