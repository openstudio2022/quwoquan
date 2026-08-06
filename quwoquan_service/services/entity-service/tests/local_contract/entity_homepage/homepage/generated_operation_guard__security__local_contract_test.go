package local_contract

import (
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	entityguard "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/operationguard"
)

func TestGeneratedEntityOperationGuardUsesCanonicalCommercialContract(t *testing.T) {
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
		// The runtime boundary is not the routing authority: an unregistered
		// path stays the owner mux's 404, not this middleware's.
		{method: http.MethodGet, path: "/entity/retired-unregistered-route", wantStatus: http.StatusOK},
	} {
		recorder := httptest.NewRecorder()
		guarded.ServeHTTP(recorder, httptest.NewRequest(testCase.method, testCase.path, nil))
		if recorder.Code != testCase.wantStatus {
			t.Fatalf("%s %s status = %d, want %d; body=%s", testCase.method, testCase.path, recorder.Code, testCase.wantStatus, recorder.Body.String())
		}
	}
	if handlerCalls != 2 {
		t.Fatalf("authenticated-only routes must still fail closed, calls=%d", handlerCalls)
	}
}

// Commercial fail-closed is owned by api-edge. Inside entity-service a blocked
// operation must stay callable, otherwise it can never produce the evidence
// that turns it ready; the public boundary must keep rejecting it.
func TestEntityRuntimeBoundaryAdmitsBlockedOperationsThatEdgeStillRejects(t *testing.T) {
	descriptors := entityguard.Descriptors()
	runtimeBoundary := entityguard.Handler(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	publicBoundary := rtauth.RequireGeneratedOperationAuthorization(descriptors)(
		http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
			t.Fatal("blocked entity operation reached a handler through api-edge")
		}),
	)

	examined := 0
	defer func() {
		// Entity currently declares no blocked operation, so this assertion is
		// dormant by design: it engages the moment one appears. The boundary
		// semantics themselves are locked unconditionally in
		// runtime/auth/operation_runtime_guard__security__local_contract_test.go.
		t.Logf("blocked entity operations examined: %d", examined)
	}()
	for _, descriptor := range descriptors {
		if descriptor.CommercialStatus == "ready" ||
			descriptor.AuthMode == "deny" ||
			descriptor.Idempotency == "required" ||
			descriptor.VersionPrecondition != "" ||
			descriptor.Principal != "persona" {
			continue
		}
		examined++
		request := func() *http.Request {
			request := httptest.NewRequest(
				descriptor.Method,
				entityServePath(descriptor.PathTemplate),
				nil,
			)
			return request.WithContext(rtauth.WithPrincipal(
				request.Context(),
				rtauth.Principal{Actor: operation.ActorContext{
					AccountID: "account-entity-guard",
					PersonaID: "persona-entity-guard",
				}},
			))
		}
		recorder := httptest.NewRecorder()
		runtimeBoundary.ServeHTTP(recorder, request())
		if recorder.Code != http.StatusNoContent {
			t.Fatalf(
				"blocked %s status=%d must stay callable in-process",
				descriptor.CanonicalOperationID,
				recorder.Code,
			)
		}
		edgeRecorder := httptest.NewRecorder()
		publicBoundary.ServeHTTP(edgeRecorder, request())
		if edgeRecorder.Code != http.StatusForbidden {
			t.Fatalf(
				"api-edge status=%d for blocked %s, want 403",
				edgeRecorder.Code,
				descriptor.CanonicalOperationID,
			)
		}
	}
}

func entityServePath(template string) string {
	path := make([]byte, 0, len(template))
	skipping := false
	for index := 0; index < len(template); index++ {
		switch template[index] {
		case '{':
			skipping = true
			path = append(path, []byte("guard-probe")...)
		case '}':
			skipping = false
		default:
			if !skipping {
				path = append(path, template[index])
			}
		}
	}
	return string(path)
}
