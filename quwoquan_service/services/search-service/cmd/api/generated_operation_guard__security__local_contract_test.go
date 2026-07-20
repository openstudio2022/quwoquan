package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGeneratedSearchOperationGuardUsesCurrentContract(t *testing.T) {
	t.Parallel()

	handlerCalls := 0
	guarded := generatedSearchOperationHandler(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			handlerCalls++
			w.WriteHeader(http.StatusOK)
		},
	))

	for _, testCase := range []struct {
		method     string
		path       string
		wantStatus int
	}{
		{method: http.MethodPost, path: "/search", wantStatus: http.StatusOK},
		{method: http.MethodGet, path: "/search/hot-queries", wantStatus: http.StatusOK},
		{method: http.MethodGet, path: "/search/recent", wantStatus: http.StatusUnauthorized},
		{method: http.MethodPost, path: "/v1/search", wantStatus: http.StatusNotFound},
		{method: http.MethodGet, path: "/search/unregistered", wantStatus: http.StatusNotFound},
	} {
		recorder := httptest.NewRecorder()
		guarded.ServeHTTP(
			recorder,
			httptest.NewRequest(testCase.method, testCase.path, nil),
		)
		if recorder.Code != testCase.wantStatus {
			t.Fatalf(
				"%s %s status=%d, want=%d; body=%s",
				testCase.method,
				testCase.path,
				recorder.Code,
				testCase.wantStatus,
				recorder.Body.String(),
			)
		}
	}
	if handlerCalls != 2 {
		t.Fatalf("only ready public operations may reach handler, calls=%d", handlerCalls)
	}
}
