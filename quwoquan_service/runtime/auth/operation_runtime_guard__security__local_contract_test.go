package auth

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005.t2

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
)

// blockedPersonaDescriptor is one commercial-blocked persona operation, i.e. the
// exact shape whose treatment differs between the public and runtime boundary.
func blockedPersonaDescriptor() OperationSecurityDescriptor {
	return OperationSecurityDescriptor{
		CanonicalOperationID: "assistant.assistant_run.StreamAssistantRunEvents",
		ContractGraphSHA256:  testContractGraphSHA256,
		Method:               http.MethodGet,
		PathTemplate:         "/assistant/runs/{runId}/events",
		OperationKind:        "query",
		AuthMode:             "required",
		ActorRequirement:     "persona",
		Principal:            "persona",
		OwnershipPolicy:      "requester_self",
		TimeoutMilliseconds:  50,
		CommercialStatus:     "blocked",
	}
}

func personaRequest(t *testing.T) *http.Request {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/run-1/events",
		nil,
	)
	return request.WithContext(WithPrincipal(
		request.Context(),
		Principal{Actor: operation.ActorContext{
			AccountID: "account-1",
			PersonaID: "persona-1",
		}},
	))
}

// The public boundary owns commercial fail-closed. A blocked operation must
// never reach an owner handler through api-edge, even with a valid principal.
func TestPublicBoundaryStillDeniesBlockedOperation(t *testing.T) {
	t.Parallel()

	guard := RequireGeneratedOperationAuthorization(
		[]OperationSecurityDescriptor{blockedPersonaDescriptor()},
	)
	handler := guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("blocked operation reached handler at the public boundary")
	}))

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, personaRequest(t))
	if response.Code != http.StatusForbidden {
		t.Fatalf("public boundary status=%d want=%d", response.Code, http.StatusForbidden)
	}
}

// The runtime boundary must let the same blocked operation through, otherwise a
// blocked object can never produce the evidence that unblocks it, and it must
// still apply the declared reliability.timeout_ms.
func TestRuntimeBoundaryAdmitsBlockedOperationWithContractDeadline(t *testing.T) {
	t.Parallel()

	served := 0
	deadlineBudget := time.Duration(0)
	guard := EnforceRuntimeOperationContract(
		[]OperationSecurityDescriptor{blockedPersonaDescriptor()},
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		served++
		deadline, ok := r.Context().Deadline()
		if !ok {
			t.Fatal("runtime boundary did not apply the contract deadline")
		}
		deadlineBudget = time.Until(deadline)
		descriptor, ok := OperationDescriptorFromContext(r.Context())
		if !ok || descriptor.CanonicalOperationID !=
			blockedPersonaDescriptor().CanonicalOperationID {
			t.Fatalf("runtime boundary did not publish the descriptor: %#v", descriptor)
		}
		w.WriteHeader(http.StatusNoContent)
	}))

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, personaRequest(t))
	if response.Code != http.StatusNoContent {
		t.Fatalf("runtime boundary status=%d want=%d", response.Code, http.StatusNoContent)
	}
	if served != 1 {
		t.Fatalf("runtime boundary served %d time(s), want 1", served)
	}
	if deadlineBudget <= 0 || deadlineBudget > 50*time.Millisecond {
		t.Fatalf("deadline budget=%s want (0, 50ms]", deadlineBudget)
	}
}

// Commercial status is the only clause the runtime boundary drops. Missing
// principal, denied auth mode and missing Idempotency-Key stay fail-closed.
func TestRuntimeBoundaryStillEnforcesRequestLevelContract(t *testing.T) {
	t.Parallel()

	commandDescriptor := OperationSecurityDescriptor{
		CanonicalOperationID: "assistant.assistant_run.CancelAssistantRun",
		ContractGraphSHA256:  testContractGraphSHA256,
		Method:               http.MethodPost,
		PathTemplate:         "/assistant/runs/{runId}/cancel",
		OperationKind:        "command",
		MutationTarget:       "AssistantRun",
		InvariantTarget:      "AssistantRun",
		AuthMode:             "required",
		ActorRequirement:     "persona",
		Principal:            "persona",
		OwnershipPolicy:      "requester_self",
		TimeoutMilliseconds:  1500,
		Idempotency:          "required",
		CommercialStatus:     "ready",
	}
	deniedDescriptor := blockedPersonaDescriptor()
	deniedDescriptor.CanonicalOperationID = "assistant.assistant_run.GetAssistantRun"
	deniedDescriptor.PathTemplate = "/assistant/runs/{runId}"
	deniedDescriptor.AuthMode = "deny"

	guard := EnforceRuntimeOperationContract(
		[]OperationSecurityDescriptor{commandDescriptor, deniedDescriptor},
	)
	handler := guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("request-level contract violation reached handler")
	}))

	for _, testCase := range []struct {
		name       string
		request    func() *http.Request
		wantStatus int
	}{
		{
			name: "missing principal",
			request: func() *http.Request {
				return httptest.NewRequest(
					http.MethodPost,
					"/assistant/runs/run-1/cancel",
					nil,
				)
			},
			wantStatus: http.StatusUnauthorized,
		},
		{
			name: "missing idempotency key",
			request: func() *http.Request {
				request := httptest.NewRequest(
					http.MethodPost,
					"/assistant/runs/run-1/cancel",
					nil,
				)
				return request.WithContext(WithPrincipal(
					request.Context(),
					Principal{Actor: operation.ActorContext{
						AccountID: "account-1",
						PersonaID: "persona-1",
					}},
				))
			},
			wantStatus: http.StatusBadRequest,
		},
		{
			name: "auth mode deny",
			request: func() *http.Request {
				request := httptest.NewRequest(
					http.MethodGet,
					"/assistant/runs/run-1",
					nil,
				)
				return request.WithContext(WithPrincipal(
					request.Context(),
					Principal{Actor: operation.ActorContext{
						AccountID: "account-1",
						PersonaID: "persona-1",
					}},
				))
			},
			wantStatus: http.StatusForbidden,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, testCase.request())
			if response.Code != testCase.wantStatus {
				t.Fatalf("status=%d want=%d", response.Code, testCase.wantStatus)
			}
		})
	}
}

// Probes and still-migrating object routes are not this middleware's business:
// the routing authority stays the service mux, and only api-edge is default
// deny for unknown paths.
func TestRuntimeBoundaryPassesUnmatchedPathsThrough(t *testing.T) {
	t.Parallel()

	served := 0
	guard := EnforceRuntimeOperationContract(
		[]OperationSecurityDescriptor{blockedPersonaDescriptor()},
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		served++
		if _, ok := r.Context().Deadline(); ok {
			t.Fatal("unmatched path must not inherit an operation deadline")
		}
		w.WriteHeader(http.StatusOK)
	}))

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if response.Code != http.StatusOK || served != 1 {
		t.Fatalf("unmatched status=%d served=%d", response.Code, served)
	}
}

func TestContractHTTPServerTimeoutsStayAboveWidestOperationBudget(t *testing.T) {
	t.Parallel()

	stream := blockedPersonaDescriptor()
	stream.TimeoutMilliseconds = 190000
	short := blockedPersonaDescriptor()
	short.CanonicalOperationID = "assistant.assistant_run.GetAssistantRun"
	short.PathTemplate = "/assistant/runs/{runId}"
	short.TimeoutMilliseconds = 1500

	descriptors := []OperationSecurityDescriptor{short, stream}
	if widest := MaxOperationTimeout(descriptors); widest != 190*time.Second {
		t.Fatalf("widest budget=%s want=190s", widest)
	}
	timeouts := ContractHTTPServerTimeouts(descriptors)
	if timeouts.Write <= 190*time.Second {
		t.Fatalf(
			"write timeout=%s must stay above the declared 190s budget",
			timeouts.Write,
		)
	}
	if timeouts.ReadHeader <= 0 || timeouts.Idle <= 0 {
		t.Fatalf("timeouts=%#v must be positive", timeouts)
	}
}

// A streaming descriptor's TimeoutMilliseconds is a derived connection lifetime,
// not a response budget. Letting it set the server ceiling would relax the
// transport backstop for every unary operation sharing the listener, so the two
// kinds of budget must not be pooled.
func TestContractHTTPServerTimeoutsIgnoreStreamingConnectionLifetimes(t *testing.T) {
	t.Parallel()

	unary := blockedPersonaDescriptor()
	unary.TimeoutMilliseconds = 3000
	stream := blockedPersonaDescriptor()
	stream.CanonicalOperationID = "assistant.assistant_run.StreamAssistantRunEvents"
	stream.PathTemplate = "/assistant/runs/{runId}/events"
	stream.StreamBudget = &OperationStreamBudget{
		HandshakeMilliseconds:   5000,
		IdleMilliseconds:        60000,
		MaxDurationMilliseconds: 600000,
	}
	stream.TimeoutMilliseconds = stream.StreamBudget.MaxDurationMilliseconds

	descriptors := []OperationSecurityDescriptor{unary, stream}
	if widest := MaxOperationTimeout(descriptors); widest != 3*time.Second {
		t.Fatalf("widest unary budget=%s want=3s", widest)
	}
	timeouts := ContractHTTPServerTimeouts(descriptors)
	if timeouts.Write >= stream.StreamBudget.MaxDuration() {
		t.Fatalf(
			"write timeout=%s absorbed the streaming connection lifetime",
			timeouts.Write,
		)
	}
	if timeouts.Write <= 3*time.Second {
		t.Fatalf(
			"write timeout=%s must stay above the widest unary budget",
			timeouts.Write,
		)
	}
}

func TestMaxOperationTimeoutRejectsBudgetlessDescriptorSet(t *testing.T) {
	t.Parallel()

	defer func() {
		if recover() == nil {
			t.Fatal("budgetless descriptor set must fail closed")
		}
	}()
	budgetless := blockedPersonaDescriptor()
	budgetless.TimeoutMilliseconds = 0
	MaxOperationTimeout([]OperationSecurityDescriptor{budgetless})
}

// Guards the deadline actually cancels work rather than only being present.
func TestRuntimeBoundaryDeadlineCancelsSlowHandler(t *testing.T) {
	t.Parallel()

	descriptor := blockedPersonaDescriptor()
	descriptor.TimeoutMilliseconds = 1
	guard := EnforceRuntimeOperationContract(
		[]OperationSecurityDescriptor{descriptor},
	)
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-r.Context().Done():
			if r.Context().Err() != context.DeadlineExceeded {
				t.Fatalf("context error=%v want deadline exceeded", r.Context().Err())
			}
			w.WriteHeader(http.StatusNoContent)
		case <-time.After(time.Second):
			t.Fatal("runtime boundary deadline never fired")
		}
	}))

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, personaRequest(t))
	if response.Code != http.StatusNoContent {
		t.Fatalf("status=%d want=%d", response.Code, http.StatusNoContent)
	}
}
