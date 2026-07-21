package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestContentLivenessDoesNotDependOnReadiness(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/livez", nil)
	response := httptest.NewRecorder()

	contentLivenessHandler(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("liveness must remain process-only, got %d", response.Code)
	}
	if got := response.Body.String(); got != `{"status":"live"}` {
		t.Fatalf("unexpected liveness body: %q", got)
	}
}

func TestContentLivenessRejectsNonGetMethods(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/livez", nil)
	response := httptest.NewRecorder()

	contentLivenessHandler(response, request)

	if response.Code != http.StatusMethodNotAllowed {
		t.Fatalf("unexpected liveness method status: %d", response.Code)
	}
}
