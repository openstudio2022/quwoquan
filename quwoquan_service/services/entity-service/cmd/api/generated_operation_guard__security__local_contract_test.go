package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGeneratedEntityOperationGuardRejectsBlockedAndUnknownRoutes(t *testing.T) {
	t.Parallel()

	handlerCalls := 0
	guarded := generatedEntityOperationHandler(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		handlerCalls++
		w.WriteHeader(http.StatusOK)
	}))

	for _, testCase := range []struct {
		path       string
		wantStatus int
	}{
		{path: "/v1/homepages/search", wantStatus: http.StatusForbidden},
		{path: "/v1/homepages/homepage_22/object-page-bundle", wantStatus: http.StatusForbidden},
		{path: "/v1/homepages/homepage_22/introduction", wantStatus: http.StatusForbidden},
		{path: "/v1/entity/legacy-unregistered-route", wantStatus: http.StatusNotFound},
	} {
		recorder := httptest.NewRecorder()
		guarded.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, testCase.path, nil))
		if recorder.Code != testCase.wantStatus {
			t.Fatalf("GET %s status = %d, want %d; body=%s", testCase.path, recorder.Code, testCase.wantStatus, recorder.Body.String())
		}
	}
	if handlerCalls != 0 {
		t.Fatalf("blocked or unknown entity routes reached handler %d times", handlerCalls)
	}
}
