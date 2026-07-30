package runtimeobservability

import (
	"context"
	"net/http"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"

	"go.opentelemetry.io/otel/trace"
)

const (
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

const (
	headerClientAccountID     = "X-Client-Account-Id"
	headerClientPersonaID     = "X-Client-Persona-Id"
	headerClientDeviceActorID = "X-Client-Device-Actor-Id"
	headerClientOperationID   = "X-Client-Operation-Id"
	headerClientPageID        = "X-Client-Page-Id"
	headerClientSurfaceID     = "X-Client-Surface-Id"
	headerClientRouteID       = "X-Client-Route-Id"
	headerClientSessionID     = "X-Client-Session-Id"
	headerReferralSource      = "X-Referral-Source"
	headerFeedRequestID       = "X-Feed-Request-Id"
	headerShareID             = "X-Share-Id"
	headerModelID             = "X-Model-Id"
	headerExperimentBucket    = "X-Experiment-Bucket"
	headerIdempotencyKey      = "Idempotency-Key"
)

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
		PersonaID:      h.Get("X-Client-Persona-Id"),
		PageID:         h.Get("X-Client-Page-Id"),
		DevicePlatform: h.Get("X-Client-Device-Platform"),
		AppVersion:     h.Get("X-Client-App-Version"),
	}
}

func buildOperationContextFromHeaders(h http.Header, meta CorrelationMeta) operation.Context {
	idempotencyKey := strings.TrimSpace(h.Get(headerIdempotencyKey))
	return operation.Context{
		OperationID:      strings.TrimSpace(h.Get(headerClientOperationID)),
		RequestID:        strings.TrimSpace(meta.RequestID),
		TraceID:          strings.TrimSpace(meta.TraceID),
		IdempotencyKey:   idempotencyKey,
		SessionID:        strings.TrimSpace(meta.SessionID),
		ClientPageID:     strings.TrimSpace(h.Get(headerClientPageID)),
		SurfaceID:        strings.TrimSpace(h.Get(headerClientSurfaceID)),
		RouteID:          strings.TrimSpace(h.Get(headerClientRouteID)),
		ReferralSource:   strings.TrimSpace(h.Get(headerReferralSource)),
		FeedRequestID:    strings.TrimSpace(h.Get(headerFeedRequestID)),
		ShareID:          strings.TrimSpace(h.Get(headerShareID)),
		ModelID:          strings.TrimSpace(h.Get(headerModelID)),
		ExperimentBucket: strings.TrimSpace(h.Get(headerExperimentBucket)),
		Actor: operation.ActorContext{
			AccountID:     strings.TrimSpace(h.Get(headerClientAccountID)),
			PersonaID:     strings.TrimSpace(h.Get(headerClientPersonaID)),
			DeviceActorID: strings.TrimSpace(h.Get(headerClientDeviceActorID)),
		},
	}
}

func applyOperationContextHeaders(h http.Header, current operation.Context) {
	setHeaderIfAbsent(h, headerClientOperationID, current.OperationID)
	setHeaderIfAbsent(h, "X-Request-Id", current.RequestID)
	setHeaderIfAbsent(h, "X-Trace-Id", current.TraceID)
	setHeaderIfAbsent(h, headerIdempotencyKey, current.IdempotencyKey)
	setHeaderIfAbsent(h, headerClientSessionID, current.SessionID)
	setHeaderIfAbsent(h, headerClientPageID, current.ClientPageID)
	setHeaderIfAbsent(h, headerClientSurfaceID, current.SurfaceID)
	setHeaderIfAbsent(h, headerClientRouteID, current.RouteID)
	setHeaderIfAbsent(h, headerReferralSource, current.ReferralSource)
	setHeaderIfAbsent(h, headerFeedRequestID, current.FeedRequestID)
	setHeaderIfAbsent(h, headerShareID, current.ShareID)
	setHeaderIfAbsent(h, headerModelID, current.ModelID)
	setHeaderIfAbsent(h, headerExperimentBucket, current.ExperimentBucket)
	setHeaderIfAbsent(h, headerClientAccountID, current.Actor.AccountID)
	setHeaderIfAbsent(h, headerClientPersonaID, current.Actor.PersonaID)
	setHeaderIfAbsent(h, headerClientDeviceActorID, current.Actor.DeviceActorID)
}

func setHeaderIfAbsent(h http.Header, name, value string) {
	if strings.TrimSpace(value) == "" || strings.TrimSpace(h.Get(name)) != "" {
		return
	}
	h.Set(name, value)
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
