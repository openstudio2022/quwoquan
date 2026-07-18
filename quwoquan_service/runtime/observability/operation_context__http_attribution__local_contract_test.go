package runtimeobservability

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/runtime/operation"
)

func TestHTTPServerMiddlewareBuildsTypedOperationContext(t *testing.T) {
	var standard bytes.Buffer
	var errorOutput bytes.Buffer
	filter := NewKVMetadataFilter(nil)
	processLogger, err := NewProcessTraceLogger(&standard, &errorOutput, TraceLogLevelInfo, filter)
	if err != nil {
		t.Fatalf("create process logger: %v", err)
	}
	exceptionLogger, err := NewExceptionLogger(&standard, &errorOutput, filter)
	if err != nil {
		t.Fatalf("create exception logger: %v", err)
	}

	var captured operation.Context
	handler := HTTPServerMiddleware(
		HTTPMiddlewareConfig{Service: "content-service"},
		NewIOAccessLogger(&standard),
		processLogger,
		exceptionLogger,
	)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var exists bool
		captured, exists = operation.FromContext(r.Context())
		if !exists {
			t.Fatal("typed operation context missing")
		}
		w.WriteHeader(http.StatusNoContent)
	}))

	request := httptest.NewRequest(http.MethodPost, "/content/posts/post-1:publish", nil)
	request.Header.Set("X-Request-Id", "request-1")
	request.Header.Set("X-Trace-Id", "trace-1")
	request.Header.Set("Idempotency-Key", "idempotency-1")
	request.Header.Set("X-Client-Session-Id", "session-1")
	request.Header.Set("X-Client-Page-Id", "content.post.editor")
	request.Header.Set("X-Client-Surface-Id", "content.create.editor")
	request.Header.Set("X-Client-Route-Id", "content.post.edit")
	request.Header.Set("X-Client-Operation-Id", "content.post.PublishPost")
	request.Header.Set("X-Client-Account-Id", "account-1")
	request.Header.Set("X-Client-Persona-Id", "persona-1")
	request.Header.Set("X-Client-Device-Actor-Id", "device-1")
	request.Header.Set("X-Referral-Source", "discovery.feed")
	request.Header.Set("X-Feed-Request-Id", "feed-1")
	request.Header.Set("X-Share-Id", "share-1")
	request.Header.Set("X-Model-Id", "ranker-v3")
	request.Header.Set("X-Experiment-Bucket", "treatment-b")

	handler.ServeHTTP(httptest.NewRecorder(), request)

	if err := captured.Validate(operation.ActorPersona); err != nil {
		t.Fatalf("validate operation context: %v", err)
	}
	if captured.ClientPageID != "content.post.editor" ||
		captured.SurfaceID != "content.create.editor" ||
		captured.RouteID != "content.post.edit" {
		t.Fatalf("page attribution drift: %+v", captured)
	}
	if captured.IdempotencyKey != "idempotency-1" {
		t.Fatalf("idempotency attribution drift: %+v", captured)
	}
	if captured.Actor.AccountID != "account-1" ||
		captured.Actor.PersonaID != "persona-1" ||
		captured.Actor.DeviceActorID != "device-1" {
		t.Fatalf("actor attribution drift: %+v", captured.Actor)
	}
	if captured.ReferralSource != "discovery.feed" ||
		captured.FeedRequestID != "feed-1" ||
		captured.ShareID != "share-1" ||
		captured.ModelID != "ranker-v3" ||
		captured.ExperimentBucket != "treatment-b" {
		t.Fatalf("journey attribution drift: %+v", captured)
	}
}

func TestOperationContextHeadersPropagateWithoutOverwritingExplicitHop(t *testing.T) {
	headers := http.Header{"X-Client-Operation-Id": []string{"internal.override"}}
	applyOperationContextHeaders(headers, operation.Context{
		OperationID:    "content.post.PublishPost",
		RequestID:      "request-1",
		TraceID:        "trace-1",
		IdempotencyKey: "idempotency-1",
		SessionID:      "session-1",
		ClientPageID:   "content.post.editor",
		Actor: operation.ActorContext{
			PersonaID: "persona-1",
		},
	})

	if got := headers.Get("X-Client-Operation-Id"); got != "internal.override" {
		t.Fatalf("explicit hop operation overwritten: %q", got)
	}
	if got := headers.Get("X-Client-Persona-Id"); got != "persona-1" {
		t.Fatalf("persona not propagated: %q", got)
	}
	if got := headers.Get("X-Trace-Id"); got != "trace-1" {
		t.Fatalf("trace not propagated: %q", got)
	}
	if got := headers.Get("Idempotency-Key"); got != "idempotency-1" {
		t.Fatalf("idempotency key not propagated: %q", got)
	}
}
