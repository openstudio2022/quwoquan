package local_contract

import (
	"net/http"
	"net/http/httptest"
	"testing"

	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
)

func TestGeneratedAssistantPrivilegedOperationHandlerFailsClosed(t *testing.T) {
	t.Parallel()
	nextCalls := 0
	handler := assistanthttp.GeneratedPrivilegedOperationHandler(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			nextCalls++
			w.WriteHeader(http.StatusNoContent)
		}),
	)

	for _, testCase := range []struct {
		method string
		path   string
	}{
		{method: http.MethodPost, path: "/internal/assistant/learning/facts"},
		{method: http.MethodGet, path: "/assistant/ops/learning-summary"},
	} {
		request := httptest.NewRequest(testCase.method, testCase.path, nil)
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		if recorder.Code < http.StatusBadRequest {
			t.Fatalf(
				"%s %s status=%d must fail closed",
				testCase.method,
				testCase.path,
				recorder.Code,
			)
		}
	}
	if nextCalls != 0 {
		t.Fatalf("privileged operation reached owner handler %d time(s)", nextCalls)
	}
}

func TestGeneratedAssistantPrivilegedOperationHandlerLeavesOwnerRoutesIntact(
	t *testing.T,
) {
	t.Parallel()
	handler := assistanthttp.GeneratedPrivilegedOperationHandler(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/suggested-actions",
		nil,
	)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusNoContent {
		t.Fatalf("owner route status=%d want=%d", recorder.Code, http.StatusNoContent)
	}
}
