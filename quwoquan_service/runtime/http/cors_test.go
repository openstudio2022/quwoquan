package runtimehttp

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWithCORSAllowsLocalhostPreflight(t *testing.T) {
	handler := WithCORS(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTeapot)
	}), DefaultCORSOptions())

	req := httptest.NewRequest(http.MethodOptions, "/content/content/posts", nil)
	req.Header.Set("Origin", "http://127.0.0.1:43123")
	req.Header.Set("Access-Control-Request-Method", http.MethodPatch)
	req.Header.Set(
		"Access-Control-Request-Headers",
		"Authorization, Idempotency-Key, If-Match, X-Client-Page-Id, X-Client-Session-Id, X-Client-User-Id",
	)

	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusNoContent {
		t.Fatalf("expected status %d, got %d", http.StatusNoContent, rr.Code)
	}
	if got := rr.Header().Get("Access-Control-Allow-Origin"); got != "http://127.0.0.1:43123" {
		t.Fatalf("expected allow origin echo, got %q", got)
	}
	allowMethods := rr.Header().Get("Access-Control-Allow-Methods")
	for _, method := range []string{http.MethodGet, http.MethodPatch, http.MethodDelete, http.MethodOptions} {
		if !strings.Contains(allowMethods, method) {
			t.Fatalf("allow methods %q missing %s", allowMethods, method)
		}
	}
	allowHeaders := rr.Header().Get("Access-Control-Allow-Headers")
	for _, header := range []string{
		"Authorization",
		"Idempotency-Key",
		"If-Match",
		"X-Client-Page-Id",
		"X-Client-Session-Id",
		"X-Client-User-Id",
	} {
		if !strings.Contains(allowHeaders, header) {
			t.Fatalf("allow headers %q missing %s", allowHeaders, header)
		}
	}
}

func TestWithCORSRejectsUnknownOrigin(t *testing.T) {
	handler := WithCORS(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}), DefaultCORSOptions())

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	req.Header.Set("Origin", "https://evil.example")

	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, rr.Code)
	}
	if got := rr.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("expected no allow origin header, got %q", got)
	}
}
