package http

import (
	"net/http"
	"net/http/httptest"
	"testing"

	rtgov "quwoquan_service/runtime/governance"
)

// When the in-flight limiter is full, the boundary sheds with a typed 503 and a
// Retry-After hint instead of invoking the downstream handler.
func TestMaxInflightMiddlewareShedsWhenFull(t *testing.T) {
	limiter := rtgov.NewInflightLimiter(1)
	if !limiter.Acquire() { // saturate so the middleware sees a full limiter
		t.Fatalf("setup: expected to acquire the only slot")
	}
	defer limiter.Release()

	downstreamCalled := false
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		downstreamCalled = true
		w.WriteHeader(http.StatusOK)
	})
	h := MaxInflightMiddleware(limiter)(next)

	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/v1/search", nil))

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d, want 503", rec.Code)
	}
	if downstreamCalled {
		t.Fatalf("downstream handler must not run when load is shed")
	}
	if rec.Header().Get("Retry-After") == "" {
		t.Fatalf("expected Retry-After hint on shed response")
	}
}

// Under capacity the request passes through and the slot is released afterward.
func TestMaxInflightMiddlewarePassesThroughAndReleases(t *testing.T) {
	limiter := rtgov.NewInflightLimiter(1)
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if limiter.Inflight() != 1 {
			t.Errorf("inflight=%d during handler, want 1", limiter.Inflight())
		}
		w.WriteHeader(http.StatusOK)
	})
	h := MaxInflightMiddleware(limiter)(next)

	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/v1/search", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d, want 200", rec.Code)
	}
	if limiter.Inflight() != 0 {
		t.Fatalf("inflight=%d after request, want 0 (slot released)", limiter.Inflight())
	}
}
