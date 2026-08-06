package local_contract

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
)

func assistantPersonaRequest(
	t *testing.T,
	method string,
	path string,
) *http.Request {
	t.Helper()
	request := httptest.NewRequest(method, path, nil)
	request.Header.Set("Idempotency-Key", "operation-guard-probe")
	return request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-guard",
			PersonaID: "persona-guard",
		}},
	))
}

func servePath(template string) string {
	segments := strings.Split(template, "/")
	for index, segment := range segments {
		if strings.HasPrefix(segment, "{") {
			segments[index] = "guard-probe"
		}
	}
	return strings.Join(segments, "/")
}

func TestGeneratedAssistantOperationContractHandlerFailsClosedWithoutPrincipal(
	t *testing.T,
) {
	t.Parallel()
	nextCalls := 0
	handler := assistanthttp.GeneratedOperationContractHandler(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			nextCalls++
			w.WriteHeader(http.StatusNoContent)
		}),
	)

	for _, testCase := range []struct {
		method string
		path   string
	}{
		// Privileged service/operator routes were already guarded.
		{method: http.MethodGet, path: "/assistant/ops/learning-summary"},
		// Persona routes were not: before the runtime boundary existed they
		// reached their owner handler with no verified principal and no budget.
		{method: http.MethodGet, path: "/assistant/sessions"},
		{method: http.MethodGet, path: "/assistant/tasks"},
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
		t.Fatalf("unauthenticated operation reached owner handler %d time(s)", nextCalls)
	}
}

// Every assistant persona route must now carry its declared
// reliability.timeout_ms into the owner handler.
func TestGeneratedAssistantOperationContractHandlerAppliesDeclaredDeadline(
	t *testing.T,
) {
	t.Parallel()
	observed := 0
	handler := assistanthttp.GeneratedOperationContractHandler(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			observed++
			if _, ok := r.Context().Deadline(); !ok {
				t.Fatal("assistant route reached the handler without a contract deadline")
			}
			w.WriteHeader(http.StatusNoContent)
		}),
	)

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, assistantPersonaRequest(
		t,
		http.MethodGet,
		"/assistant/sessions",
	))
	if recorder.Code != http.StatusNoContent || observed != 1 {
		t.Fatalf("guarded persona route status=%d observed=%d", recorder.Code, observed)
	}
}

// Commercial fail-closed belongs to api-edge. Applied to the real generated
// table: every blocked assistant operation must still be reachable inside the
// owner process, otherwise it can never produce the evidence that unblocks it.
// The boundary semantics themselves are covered unconditionally in
// runtime/auth/operation_runtime_guard__security__local_contract_test.go.
func TestGeneratedAssistantOperationContractHandlerAdmitsBlockedOperations(
	t *testing.T,
) {
	t.Parallel()
	served := map[string]int{}
	handler := assistanthttp.GeneratedOperationContractHandler(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			descriptor, ok := rtauth.OperationDescriptorFromContext(r.Context())
			if !ok {
				t.Fatal("runtime boundary did not publish the operation descriptor")
			}
			served[descriptor.CanonicalOperationID]++
			w.WriteHeader(http.StatusNoContent)
		}),
	)

	blocked := 0
	for _, descriptor := range assistanthttp.AssistantOperationDescriptors() {
		if descriptor.CommercialStatus == "ready" ||
			descriptor.AuthMode == "deny" ||
			descriptor.Principal != "persona" {
			continue
		}
		blocked++
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, assistantPersonaRequest(
			t,
			descriptor.Method,
			servePath(descriptor.PathTemplate),
		))
		if recorder.Code != http.StatusNoContent {
			t.Fatalf(
				"blocked operation %s status=%d must stay callable in-process",
				descriptor.CanonicalOperationID,
				recorder.Code,
			)
		}
		if served[descriptor.CanonicalOperationID] != 1 {
			t.Fatalf(
				"blocked operation %s did not reach its owner handler",
				descriptor.CanonicalOperationID,
			)
		}
	}
	t.Logf("blocked assistant persona operations admitted in-process: %d", blocked)
}

// api-edge stays the commercial gate. If someone swaps the public boundary for
// the runtime one, this assertion fails.
func TestPublicBoundaryStillDeniesBlockedAssistantOperations(t *testing.T) {
	t.Parallel()
	edge := rtauth.RequireGeneratedOperationAuthorization(
		assistanthttp.AssistantOperationDescriptors(),
	)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("blocked assistant operation reached a handler through api-edge")
	}))

	for _, descriptor := range assistanthttp.AssistantOperationDescriptors() {
		if descriptor.CommercialStatus == "ready" ||
			descriptor.Principal != "persona" {
			continue
		}
		recorder := httptest.NewRecorder()
		edge.ServeHTTP(recorder, assistantPersonaRequest(
			t,
			descriptor.Method,
			servePath(descriptor.PathTemplate),
		))
		if recorder.Code != http.StatusForbidden {
			t.Fatalf(
				"api-edge status=%d for blocked %s, want 403",
				recorder.Code,
				descriptor.CanonicalOperationID,
			)
		}
	}
}

// Probes and unregistered internal paths must not be turned into 404 by a
// middleware that is not the routing authority.
func TestGeneratedAssistantOperationContractHandlerLeavesUnmatchedPathsIntact(
	t *testing.T,
) {
	t.Parallel()
	handler := assistanthttp.GeneratedOperationContractHandler(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	request := httptest.NewRequest(http.MethodGet, "/assistant/not-registered", nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusNoContent {
		t.Fatalf("unmatched path status=%d want=%d", recorder.Code, http.StatusNoContent)
	}
}
