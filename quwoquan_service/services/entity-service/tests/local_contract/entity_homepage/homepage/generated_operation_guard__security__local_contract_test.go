package local_contract

import (
	"net/http"
	"net/http/httptest"
	"testing"

	entityguard "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/operationguard"
)

func TestGeneratedEntityOperationGuardUsesCurrentCommercialContract(t *testing.T) {
	handlerCalls := 0
	guarded := entityguard.Handler(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		handlerCalls++
		w.WriteHeader(http.StatusOK)
	}))

	for _, testCase := range []struct {
		method     string
		path       string
		wantStatus int
	}{
		{method: http.MethodGet, path: "/homepages/search", wantStatus: http.StatusOK},
		{method: http.MethodPost, path: "/homepages/candidates", wantStatus: http.StatusUnauthorized},
		{method: http.MethodGet, path: "/entity/legacy-unregistered-route", wantStatus: http.StatusNotFound},
	} {
		recorder := httptest.NewRecorder()
		guarded.ServeHTTP(recorder, httptest.NewRequest(testCase.method, testCase.path, nil))
		if recorder.Code != testCase.wantStatus {
			t.Fatalf("%s %s status = %d, want %d; body=%s", testCase.method, testCase.path, recorder.Code, testCase.wantStatus, recorder.Body.String())
		}
	}
	if handlerCalls != 1 {
		t.Fatalf("only the ready public route without authentication may reach handler, calls=%d", handlerCalls)
	}
}
