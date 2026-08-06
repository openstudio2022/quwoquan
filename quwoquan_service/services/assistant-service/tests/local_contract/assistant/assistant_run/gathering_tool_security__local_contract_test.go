package assistant_run

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	gatheringplanclient "quwoquan_service/generated/serviceclients/circlegatheringplan"
	runtimeauth "quwoquan_service/runtime/auth"
	tooling "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tooling"
)

func TestGatheringPrivateReadRequiresExactGrantAndRedactsSensitiveCollections(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringReadPrivateTool)
	signer, verifier, _, _ := gatheringGrantRuntime(t)
	execution := gatheringExecution(tooling.GatheringConversationDirect)
	execution.ApprovalRef = ""
	request := tooling.GatheringIDQuery{GatheringID: "gathering-1"}
	requestDigest, err := tooling.CanonicalGatheringRequestDigest(request)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	baseClaims := gatheringGrantClaims(
		execution,
		definition,
		toolingTarget("gathering-1"),
		requestDigest,
		now,
	)
	token := signGatheringQuery(t, signer, baseClaims)
	client := &fakeGeneratedGatheringClient{
		contractDigest: definition.ContractDigest,
		private: tooling.PrivateGatheringDetail{
			GatheringID:         "gathering-1",
			Title:               "私密聚会",
			Purpose:             "测试私密披露",
			StartAt:             "2026-08-08T09:00:00+08:00",
			EndAt:               "2026-08-08T12:00:00+08:00",
			ExactMeetingPoint:   "仅参与者可见",
			Capacity:            8,
			CurrentParticipants: 3,
			AdmissionMode:       "approval_required",
			Version:             4,
			ViewerAuthority:     tooling.GatheringViewerParticipation,
		},
	}
	executor := tooling.NewGatheringExecutor(catalog, verifier, nil, client)
	result, err := executor.ReadPrivate(t.Context(), execution, token, request)
	if err != nil {
		t.Fatalf("private read: %v", err)
	}
	if result.RedactionPolicy != tooling.GatheringPrivateRedactionPolicy {
		t.Fatalf("redaction policy=%q", result.RedactionPolicy)
	}
	if client.lastQueryCall == nil ||
		client.lastQueryCall.SerializedGrant != token ||
		client.lastQueryCall.Grant.Claims.OperationID != definition.OwnerOperationID ||
		client.lastQueryCall.Binding.RequestDigest != requestDigest {
		t.Fatalf("typed delegated query call=%+v", client.lastQueryCall)
	}
	encoded, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		"participantIdentities",
		"applicationAnswers",
		"inviteeIdentities",
		"moderationNotes",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("private read leaked %s: %s", forbidden, encoded)
		}
	}

	client.private.ViewerAuthority = ""
	if _, err := executor.ReadPrivate(
		t.Context(),
		execution,
		token,
		request,
	); !errors.Is(err, tooling.ErrGatheringHostUnauthorized) {
		t.Fatalf("private read without Participation/Host authority error=%v", err)
	}
}

func TestGatheringQueryGrantRejectsWrongOperationTargetDigestAndExpiry(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringReadPublicTool)
	signer, verifier, _, _ := gatheringGrantRuntime(t)
	execution := gatheringExecution(tooling.GatheringConversationGroup)
	execution.ApprovalRef = ""
	request := tooling.GatheringIDQuery{GatheringID: "gathering-1"}
	requestDigest, err := tooling.CanonicalGatheringRequestDigest(request)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	base := gatheringGrantClaims(
		execution,
		definition,
		toolingTarget(request.GatheringID),
		requestDigest,
		now,
	)
	executor := tooling.NewGatheringExecutor(
		catalog,
		verifier,
		nil,
		&fakeGeneratedGatheringClient{
			contractDigest: definition.ContractDigest,
			public:         tooling.PublicGatheringDetail{GatheringID: request.GatheringID},
		},
	)

	tests := []struct {
		name   string
		mutate func(*runtimeauth.DelegatedGrantClaims)
		want   error
	}{
		{
			name: "operation",
			mutate: func(claims *runtimeauth.DelegatedGrantClaims) {
				claims.OperationID = "circle.gathering.CancelGathering"
			},
			want: runtimeauth.ErrDelegatedGrantTargetMismatch,
		},
		{
			name: "target",
			mutate: func(claims *runtimeauth.DelegatedGrantClaims) {
				claims.Resource.ID = "gathering-other"
			},
			want: runtimeauth.ErrDelegatedGrantTargetMismatch,
		},
		{
			name: "digest",
			mutate: func(claims *runtimeauth.DelegatedGrantClaims) {
				claims.RequestDigest = "sha256:" + strings.Repeat("f", 64)
			},
			want: runtimeauth.ErrDelegatedGrantDigestMismatch,
		},
		{
			name: "expired",
			mutate: func(claims *runtimeauth.DelegatedGrantClaims) {
				claims.IssuedAt = now.Add(-2 * time.Minute).Unix()
				claims.ExpiresAt = now.Add(-time.Minute).Unix()
			},
			want: runtimeauth.ErrExpiredToken,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			claims := base
			test.mutate(&claims)
			token := signGatheringQuery(t, signer, claims)
			if _, err := executor.ReadPublic(
				t.Context(),
				execution,
				token,
				request,
			); !errors.Is(err, test.want) {
				t.Fatalf("error=%v, want %v", err, test.want)
			}
		})
	}

	canonicalToken := signGatheringQuery(t, signer, base)
	driftedClient := tooling.NewGatheringExecutor(
		catalog,
		verifier,
		nil,
		&fakeGeneratedGatheringClient{
			contractDigest: "sha256:" + strings.Repeat("e", 64),
			public:         tooling.PublicGatheringDetail{GatheringID: request.GatheringID},
		},
	)
	if _, err := driftedClient.ReadPublic(
		t.Context(),
		execution,
		canonicalToken,
		request,
	); !errors.Is(err, tooling.ErrGatheringBindingInvalid) {
		t.Fatalf("generated client contract drift error=%v", err)
	}
}

func TestGatheringConfirmedWatchConsumesGrantOnceAndNoClientFailsClosed(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringWatchAvailabilityTool)
	signer, verifier, consumer, store := gatheringGrantRuntime(t)
	execution := gatheringExecution(tooling.GatheringConversationGroup)
	request := tooling.GatheringAvailabilityWatchCommand{
		GatheringID:              "gathering-1",
		ExpectedGatheringVersion: 4,
		ExpectedWatchVersion:     0,
	}
	requestDigest, err := tooling.CanonicalGatheringRequestDigest(request)
	if err != nil {
		t.Fatal(err)
	}
	target := toolingTarget(request.GatheringID)
	binding, err := tooling.NewDomainOperationBinding(definition, requestDigest, target)
	if err != nil {
		t.Fatalf("build watch binding: %v", err)
	}
	now := time.Now().UTC()
	claims := gatheringGrantClaims(execution, definition, target, requestDigest, now)
	token := signGatheringCommand(t, signer, claims)
	client := &fakeGeneratedGatheringClient{
		contractDigest: definition.ContractDigest,
		watchResult: tooling.GatheringCommandResult{
			GatheringID:       request.GatheringID,
			AggregateVersion:  5,
			LifecycleStatus:   "published",
			RoomBindingStatus: "ready",
			IdempotentReplay:  false,
		},
	}
	executor := tooling.NewGatheringExecutor(catalog, verifier, consumer, client)
	if _, err := executor.ExecuteConfirmedAvailabilityWatch(
		t.Context(),
		execution,
		token,
		binding,
		request,
	); err != nil {
		t.Fatalf("first watch execution: %v", err)
	}
	if client.watchCalls != 1 {
		t.Fatalf("watch calls=%d", client.watchCalls)
	}
	if client.lastCommandCall == nil ||
		client.lastCommandCall.SerializedGrant != token ||
		client.lastCommandCall.Grant.Claims.JWTID != claims.JWTID ||
		client.lastCommandCall.Binding != binding {
		t.Fatalf("typed delegated command call=%+v", client.lastCommandCall)
	}
	if _, err := executor.ExecuteConfirmedAvailabilityWatch(
		t.Context(),
		execution,
		token,
		binding,
		request,
	); !errors.Is(err, runtimeauth.ErrDelegatedGrantReplay) {
		t.Fatalf("replayed watch error=%v", err)
	}
	if client.watchCalls != 1 {
		t.Fatalf("replay reached owner client, calls=%d", client.watchCalls)
	}

	unwired := tooling.NewGatheringExecutor(catalog, verifier, consumer, nil)
	freshClaims := claims
	freshClaims.JWTID = "command-jti-unwired"
	freshToken := signGatheringCommand(t, signer, freshClaims)
	if _, err := unwired.ExecuteConfirmedAvailabilityWatch(
		t.Context(),
		execution,
		freshToken,
		binding,
		request,
	); !errors.Is(err, tooling.ErrGatheringToolUnavailable) {
		t.Fatalf("unwired production client error=%v", err)
	}
	store.mu.Lock()
	unwiredConsumed := store.consumed["command-jti-unwired"]
	store.mu.Unlock()
	if unwiredConsumed {
		t.Fatal("unavailable client must fail before consuming the command grant")
	}
}

func TestGatheringPlanCommandGrantRejectsDriftExpiryAndReplay(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringProposePlanTool)
	signer, verifier, consumer, store := gatheringGrantRuntime(t)
	execution := gatheringExecution(tooling.GatheringConversationGroup)
	request := gatheringPlanCommand()
	packet, err := gatheringplanclient.EncodeProposeGatheringPlan(request)
	if err != nil {
		t.Fatal(err)
	}
	requestDigest := gatheringplanclient.CanonicalRequestDigest(
		packet.CanonicalRequest,
	)
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering_plan",
		ID:   request.PlanID,
	}
	binding, err := tooling.NewDomainOperationBinding(
		definition,
		requestDigest,
		target,
	)
	if err != nil {
		t.Fatalf("build plan binding: %v", err)
	}
	now := time.Now().UTC()
	base := gatheringGrantClaims(
		execution,
		definition,
		target,
		requestDigest,
		now,
	)
	client := &fakeGeneratedGatheringClient{
		contractDigest: definition.ContractDigest,
		planResult: gatheringplanclient.GatheringPlanCommandResult{
			PlanID:                request.PlanID,
			GatheringID:           "gathering-1",
			PlanVersion:           3,
			CurrentRevisionID:     request.BaseRevisionID,
			CurrentRevisionNumber: request.BaseRevisionNumber,
			CurrentRevisionDigest: request.BaseRevisionDigest,
			ProposalID:            "proposal-1",
			ProposalDigest:        "sha256:" + strings.Repeat("b", 64),
		},
	}
	executor := tooling.NewGatheringExecutor(
		catalog,
		verifier,
		consumer,
		client,
	)
	tests := []struct {
		name   string
		mutate func(*runtimeauth.DelegatedGrantClaims)
		want   error
	}{
		{
			name: "wrong target",
			mutate: func(claims *runtimeauth.DelegatedGrantClaims) {
				claims.Resource.ID = "plan-other"
			},
			want: runtimeauth.ErrDelegatedGrantTargetMismatch,
		},
		{
			name: "wrong digest",
			mutate: func(claims *runtimeauth.DelegatedGrantClaims) {
				claims.RequestDigest = "sha256:" + strings.Repeat("f", 64)
			},
			want: runtimeauth.ErrDelegatedGrantDigestMismatch,
		},
		{
			name: "expired",
			mutate: func(claims *runtimeauth.DelegatedGrantClaims) {
				claims.IssuedAt = now.Add(-2 * time.Minute).Unix()
				claims.ExpiresAt = now.Add(-time.Minute).Unix()
			},
			want: runtimeauth.ErrExpiredToken,
		},
	}
	for index, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			claims := base
			claims.JWTID = fmt.Sprintf("plan-negative-%d", index)
			test.mutate(&claims)
			token := signGatheringCommand(t, signer, claims)
			if _, err := executor.ExecuteConfirmedGatheringPlanProposal(
				t.Context(),
				execution,
				token,
				binding,
				request,
			); !errors.Is(err, test.want) {
				t.Fatalf("error=%v, want %v", err, test.want)
			}
		})
	}

	missingGrantClaims := base
	missingGrantClaims.JWTID = "plan-command-missing-consumer"
	missingGrantToken := signGatheringCommand(t, signer, missingGrantClaims)
	withoutGrantConsumer := tooling.NewGatheringExecutor(
		catalog,
		verifier,
		nil,
		client,
	)
	if _, err := withoutGrantConsumer.ExecuteConfirmedGatheringPlanProposal(
		t.Context(),
		execution,
		missingGrantToken,
		binding,
		request,
	); !errors.Is(err, tooling.ErrGatheringToolUnavailable) {
		t.Fatalf("missing plan command grant consumer error=%v", err)
	}

	unwiredClaims := base
	unwiredClaims.JWTID = "plan-command-unwired-client"
	unwiredToken := signGatheringCommand(t, signer, unwiredClaims)
	unwired := tooling.NewGatheringExecutor(
		catalog,
		verifier,
		consumer,
		nil,
	)
	if _, err := unwired.ExecuteConfirmedGatheringPlanProposal(
		t.Context(),
		execution,
		unwiredToken,
		binding,
		request,
	); !errors.Is(err, tooling.ErrGatheringToolUnavailable) {
		t.Fatalf("unwired plan client error=%v", err)
	}
	store.mu.Lock()
	unwiredConsumed := store.consumed[unwiredClaims.JWTID]
	store.mu.Unlock()
	if unwiredConsumed {
		t.Fatal("unavailable plan client must not consume the command grant")
	}

	valid := base
	valid.JWTID = "plan-command-single-use"
	token := signGatheringCommand(t, signer, valid)
	if _, err := executor.ExecuteConfirmedGatheringPlanProposal(
		t.Context(),
		execution,
		token,
		binding,
		request,
	); err != nil {
		t.Fatalf("first plan proposal execution: %v", err)
	}
	if _, err := executor.ExecuteConfirmedGatheringPlanProposal(
		t.Context(),
		execution,
		token,
		binding,
		request,
	); !errors.Is(err, runtimeauth.ErrDelegatedGrantReplay) {
		t.Fatalf("replayed plan proposal error=%v", err)
	}
	if client.planCalls != 1 {
		t.Fatalf("replay reached Circle plan client, calls=%d", client.planCalls)
	}
}

type fakeGeneratedGatheringClient struct {
	contractDigest  string
	page            tooling.PublicGatheringPage
	public          tooling.PublicGatheringDetail
	private         tooling.PrivateGatheringDetail
	watchResult     tooling.GatheringCommandResult
	planResult      gatheringplanclient.GatheringPlanCommandResult
	watchCalls      int
	planCalls       int
	lastQueryCall   *tooling.VerifiedGatheringQueryCall
	lastCommandCall *tooling.VerifiedGatheringCommandCall
}

func (f *fakeGeneratedGatheringClient) OperationContractDigest(string) string {
	return f.contractDigest
}

func (f *fakeGeneratedGatheringClient) SearchPublic(
	_ context.Context,
	call tooling.VerifiedGatheringQueryCall,
	_ tooling.GatheringSearchPublicRequest,
) (tooling.PublicGatheringPage, error) {
	f.lastQueryCall = &call
	return f.page, nil
}

func (f *fakeGeneratedGatheringClient) ReadPublic(
	_ context.Context,
	call tooling.VerifiedGatheringQueryCall,
	_ tooling.GatheringIDQuery,
) (tooling.PublicGatheringDetail, error) {
	f.lastQueryCall = &call
	return f.public, nil
}

func (f *fakeGeneratedGatheringClient) ReadPrivate(
	_ context.Context,
	call tooling.VerifiedGatheringQueryCall,
	_ tooling.GatheringIDQuery,
) (tooling.PrivateGatheringDetail, error) {
	f.lastQueryCall = &call
	return f.private, nil
}

func (f *fakeGeneratedGatheringClient) WatchAvailability(
	_ context.Context,
	call tooling.VerifiedGatheringCommandCall,
	_ tooling.GatheringAvailabilityWatchCommand,
	_ string,
) (tooling.GatheringCommandResult, error) {
	f.watchCalls++
	f.lastCommandCall = &call
	return f.watchResult, nil
}

func (f *fakeGeneratedGatheringClient) ProposeGatheringPlan(
	_ context.Context,
	call tooling.VerifiedGatheringCommandCall,
	_ gatheringplanclient.ProposeGatheringPlanCommand,
	_ string,
) (gatheringplanclient.GatheringPlanCommandResult, error) {
	f.planCalls++
	f.lastCommandCall = &call
	return f.planResult, nil
}

type gatheringAccountSecurityAuthority struct{}

func (gatheringAccountSecurityAuthority) ReadAccountSecurity(
	context.Context,
	string,
) (runtimeauth.AccountSecuritySnapshot, error) {
	return runtimeauth.AccountSecuritySnapshot{
		AccountState: "active",
		AuthEpoch:    1,
	}, nil
}

type gatheringGrantStore struct {
	mu       sync.Mutex
	consumed map[string]bool
}

func (s *gatheringGrantStore) Consume(
	_ context.Context,
	jti string,
	_ time.Time,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.consumed[jti] {
		return false, nil
	}
	s.consumed[jti] = true
	return true, nil
}

func gatheringGrantRuntime(t *testing.T) (
	*runtimeauth.DelegatedGrantSigner,
	*runtimeauth.DelegatedGrantVerifier,
	*runtimeauth.DelegatedCommandGrantConsumer,
	*gatheringGrantStore,
) {
	t.Helper()
	secret := []byte("gathering-local-contract-secret-32-bytes")
	signer, err := runtimeauth.NewHS256DelegatedGrantSigner(secret, "user-service")
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := runtimeauth.NewHS256DelegatedGrantVerifier(
		runtimeauth.DelegatedGrantVerifierConfig{
			Secret:                   secret,
			Issuer:                   "user-service",
			AccountSecurityAuthority: gatheringAccountSecurityAuthority{},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	store := &gatheringGrantStore{consumed: map[string]bool{}}
	consumer, err := runtimeauth.NewDelegatedCommandGrantConsumer(verifier, store)
	if err != nil {
		t.Fatal(err)
	}
	return signer, verifier, consumer, store
}

func gatheringGrantClaims(
	execution tooling.GatheringExecutionContext,
	definition tooling.GatheringToolDefinition,
	target runtimeauth.DelegatedResourceConstraint,
	requestDigest string,
	now time.Time,
) runtimeauth.DelegatedGrantClaims {
	return runtimeauth.DelegatedGrantClaims{
		Audience:         tooling.GatheringDelegateAudience,
		AccountID:        execution.AccountID,
		PersonaID:        execution.PersonaID,
		AuthEpoch:        1,
		DelegateService:  tooling.GatheringDelegateService,
		RunID:            execution.RunID,
		ToolInvocationID: execution.ToolInvocationID,
		OperationID:      definition.OwnerOperationID,
		Resource:         target,
		RequestDigest:    requestDigest,
		Surface:          execution.Surface,
		Scope:            strings.Join(definition.RequiredAuth.Scopes, " "),
		IdempotencyKey:   execution.IdempotencyKey,
		JWTID:            "grant-jti-1",
		ApprovalRef:      execution.ApprovalRef,
		IssuedAt:         now.Unix(),
		ExpiresAt:        now.Add(time.Minute).Unix(),
	}
}

func signGatheringQuery(
	t *testing.T,
	signer *runtimeauth.DelegatedGrantSigner,
	claims runtimeauth.DelegatedGrantClaims,
) string {
	t.Helper()
	token, err := signer.SignQuery(runtimeauth.DelegatedQueryGrant{Claims: claims})
	if err != nil {
		t.Fatalf("sign gathering query grant: %v", err)
	}
	return token
}

func signGatheringCommand(
	t *testing.T,
	signer *runtimeauth.DelegatedGrantSigner,
	claims runtimeauth.DelegatedGrantClaims,
) string {
	t.Helper()
	token, err := signer.SignCommand(runtimeauth.DelegatedCommandGrant{Claims: claims})
	if err != nil {
		t.Fatalf("sign gathering command grant: %v", err)
	}
	return token
}

func toolingTarget(gatheringID string) runtimeauth.DelegatedResourceConstraint {
	return runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering",
		ID:   gatheringID,
	}
}
