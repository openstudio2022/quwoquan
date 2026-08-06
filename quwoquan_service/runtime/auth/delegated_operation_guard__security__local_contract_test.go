package auth

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
)

func TestDelegatedCommandOperationGuardExecutesOnce(t *testing.T) {
	t.Parallel()
	now := time.Unix(2_000_000_000, 0).UTC()
	signer, verifier := delegatedGrantTestSignerVerifier(t, now, 7)
	store := &delegatedGrantMemoryJTIStore{}
	consumer, err := NewDelegatedCommandGrantConsumer(verifier, store)
	if err != nil {
		t.Fatalf("new consumer: %v", err)
	}
	guard, err := NewDelegatedOperationGuard(DelegatedOperationGuardConfig{
		Verifier:        verifier,
		CommandConsumer: consumer,
		Audience:        "assistant-service",
		DelegateService: "assistant-service",
	})
	if err != nil {
		t.Fatalf("new operation guard: %v", err)
	}
	descriptor := delegatedCommandDescriptor()
	body := []byte(`{"outcome":"succeeded"}`)
	claims := delegatedOperationClaims(now, descriptor, body)
	token, err := signer.SignCommand(DelegatedCommandGrant{Claims: claims})
	if err != nil {
		t.Fatalf("sign command grant: %v", err)
	}
	executed := 0
	handler := guard.EnforceRuntimeOperationContract(
		[]OperationSecurityDescriptor{descriptor},
	)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		executed++
		principal, ok := PrincipalFromContext(r.Context())
		if !ok ||
			principal.TokenType != TokenTypeDelegatedCommand ||
			principal.Actor.AccountID != claims.AccountID ||
			principal.Actor.PersonaID != claims.PersonaID {
			t.Fatalf("unexpected delegated principal: %#v", principal)
		}
		w.WriteHeader(http.StatusNoContent)
	}))

	first := delegatedCommandRequest(body, token, claims)
	firstResponse := httptest.NewRecorder()
	handler.ServeHTTP(firstResponse, first)
	if firstResponse.Code != http.StatusNoContent || executed != 1 {
		t.Fatalf(
			"first status=%d executed=%d",
			firstResponse.Code,
			executed,
		)
	}

	replay := delegatedCommandRequest(body, token, claims)
	replayResponse := httptest.NewRecorder()
	handler.ServeHTTP(replayResponse, replay)
	if replayResponse.Code != http.StatusForbidden || executed != 1 {
		t.Fatalf(
			"replay status=%d executed=%d",
			replayResponse.Code,
			executed,
		)
	}
}

func TestDelegatedCommandOperationGuardRejectsDigestAndOperationDrift(
	t *testing.T,
) {
	t.Parallel()
	now := time.Unix(2_000_000_000, 0).UTC()
	signer, verifier := delegatedGrantTestSignerVerifier(t, now, 7)
	consumer, err := NewDelegatedCommandGrantConsumer(
		verifier,
		&delegatedGrantMemoryJTIStore{},
	)
	if err != nil {
		t.Fatalf("new consumer: %v", err)
	}
	guard, err := NewDelegatedOperationGuard(DelegatedOperationGuardConfig{
		Verifier:        verifier,
		CommandConsumer: consumer,
		Audience:        "assistant-service",
		DelegateService: "assistant-service",
	})
	if err != nil {
		t.Fatalf("new operation guard: %v", err)
	}
	descriptor := delegatedCommandDescriptor()
	body := []byte(`{"outcome":"succeeded"}`)
	claims := delegatedOperationClaims(now, descriptor, body)
	token, err := signer.SignCommand(DelegatedCommandGrant{Claims: claims})
	if err != nil {
		t.Fatalf("sign command grant: %v", err)
	}
	executed := 0
	handler := guard.EnforceRuntimeOperationContract(
		[]OperationSecurityDescriptor{descriptor},
	)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		executed++
	}))

	digestDrift := delegatedCommandRequest(
		[]byte(`{"outcome":"failed"}`),
		token,
		claims,
	)
	digestResponse := httptest.NewRecorder()
	handler.ServeHTTP(digestResponse, digestDrift)
	if digestResponse.Code != http.StatusForbidden {
		t.Fatalf("digest drift status=%d", digestResponse.Code)
	}

	claims.OperationID = "assistant.assistant_run.ApproveToolUse"
	claims.JWTID = "jti-other-operation"
	operationToken, err := signer.SignCommand(
		DelegatedCommandGrant{Claims: claims},
	)
	if err != nil {
		t.Fatalf("sign operation-drift grant: %v", err)
	}
	operationDrift := delegatedCommandRequest(body, operationToken, claims)
	operationResponse := httptest.NewRecorder()
	handler.ServeHTTP(operationResponse, operationDrift)
	if operationResponse.Code != http.StatusForbidden {
		t.Fatalf("operation drift status=%d", operationResponse.Code)
	}
	if executed != 0 {
		t.Fatalf("rejected grants executed %d command(s)", executed)
	}
}

func TestLegacyServicePersonaCredentialCannotWrite(t *testing.T) {
	t.Parallel()
	descriptor := delegatedCommandDescriptor()
	handler := EnforceRuntimeOperationContract(
		[]OperationSecurityDescriptor{descriptor},
	)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("legacy service persona credential reached write handler")
	}))
	request := httptest.NewRequest(
		http.MethodPost,
		descriptor.PathTemplate,
		bytes.NewReader([]byte(`{}`)),
	)
	request.Header.Set("Idempotency-Key", "receipt-1")
	request = request.WithContext(WithPrincipal(
		request.Context(),
		Principal{
			Claims: Claims{
				TokenType: TokenTypeAccess,
				Subject:   "service:assistant-service",
				Persona:   "persona-1",
				Scope:     "assistant.run.device_action_receipt.write",
				Roles:     []string{"service"},
			},
			Actor: operation.ActorContext{
				AccountID: "service:assistant-service",
				PersonaID: "persona-1",
			},
		},
	))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("legacy persona write status=%d", response.Code)
	}
}

func TestDelegatedHTTPResourceBindsQueryTarget(t *testing.T) {
	t.Parallel()
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/run-1?cursor=page-2&limit=20",
		nil,
	)
	resource := HTTPDelegatedResourceConstraint(request)
	if resource.Type != "http_request" ||
		resource.ID !=
			"GET /assistant/runs/run-1?cursor=page-2&limit=20" {
		t.Fatalf("unexpected delegated resource: %#v", resource)
	}
}

func delegatedCommandDescriptor() OperationSecurityDescriptor {
	return OperationSecurityDescriptor{
		CanonicalOperationID: "assistant.assistant_run.SubmitDeviceActionReceipt",
		ContractGraphSHA256:  testContractGraphSHA256,
		Method:               http.MethodPost,
		PathTemplate:         "/assistant/runs/{runId}/tool-invocations/{toolInvocationId}/receipts",
		OperationKind:        "command",
		MutationTarget:       "AssistantRun",
		InvariantTarget:      "AssistantRun",
		AuthMode:             "required",
		ActorRequirement:     "persona",
		Principal:            "persona",
		Scopes:               []string{"assistant.run.device_action_receipt.write"},
		OwnershipPolicy:      "requester_self",
		TimeoutMilliseconds:  1500,
		Idempotency:          "required",
		CommercialStatus:     "ready",
	}
}

func delegatedOperationClaims(
	now time.Time,
	descriptor OperationSecurityDescriptor,
	body []byte,
) DelegatedGrantClaims {
	return DelegatedGrantClaims{
		GrantType:        DelegatedGrantTypeCommand,
		Issuer:           "account-authority",
		Audience:         "assistant-service",
		AccountID:        "account-1",
		PersonaID:        "persona-1",
		AuthEpoch:        7,
		DelegateService:  "assistant-service",
		RunID:            "run-1",
		ToolInvocationID: "tool-1",
		OperationID:      descriptor.CanonicalOperationID,
		Resource: DelegatedResourceConstraint{
			Type: "http_request",
			ID: "POST /assistant/runs/run-1/tool-invocations/" +
				"tool-1/receipts",
		},
		RequestDigest:  DelegatedRequestDigest(body),
		Surface:        "assistant_run",
		Scope:          "assistant.run.device_action_receipt.write",
		IdempotencyKey: "receipt-1",
		JWTID:          "jti-receipt-1",
		ApprovalRef:    "approval-1",
		IssuedAt:       now.Add(-time.Second).Unix(),
		ExpiresAt:      now.Add(59 * time.Second).Unix(),
	}
}

func delegatedCommandRequest(
	body []byte,
	token string,
	claims DelegatedGrantClaims,
) *http.Request {
	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/runs/run-1/tool-invocations/tool-1/receipts",
		bytes.NewReader(body),
	)
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Idempotency-Key", claims.IdempotencyKey)
	request.Header.Set(delegatedRunIDHeader, claims.RunID)
	request.Header.Set(
		delegatedToolInvocationIDHeader,
		claims.ToolInvocationID,
	)
	request.Header.Set(delegatedSurfaceHeader, claims.Surface)
	request.Header.Set(delegatedApprovalRefHeader, claims.ApprovalRef)
	return request
}
