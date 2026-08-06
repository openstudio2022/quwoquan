package assistant_run

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tooling"
	gatheringinfrastructure "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/gathering"
)

func TestGatheringSharedDispatcherRegistersClosedSetAndFailsClosed(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	dispatcher, err := tooling.NewGatheringDispatcher(
		catalog,
		tooling.GatheringDispatcherDependencies{
			Availability: map[string]tooling.GatheringToolAvailability{
				tooling.GatheringReadPublicTool: {
					Blocked: true,
					Reason:  "circle_operation_blocked",
				},
				tooling.GatheringReadPrivateTool: {
					Enabled: false,
					Reason:  "private_reader_disabled",
				},
			},
		},
	)
	if err != nil {
		t.Fatalf("create gathering dispatcher: %v", err)
	}
	handlers := dispatcher.Handlers()
	if len(handlers) != 7 {
		t.Fatalf("registered gathering handlers=%d, want 7", len(handlers))
	}

	registry := gatheringOnlyRegistry(t, handlers)
	if _, err := registry.Execute(context.Background(), tool.Request{
		ToolName: "gathering.unknown",
	}); err == nil {
		t.Fatal("unknown gathering tool must fail closed")
	}
	if _, err := registry.Execute(context.Background(), tool.Request{
		ToolName: tooling.GatheringReadPublicTool,
		Input:    map[string]any{"gatheringId": "gathering-1"},
	}); !errors.Is(err, tooling.ErrGatheringToolBlocked) {
		t.Fatalf("blocked gathering tool error=%v", err)
	}
	if _, err := registry.Execute(context.Background(), tool.Request{
		ToolName: tooling.GatheringReadPrivateTool,
		Input:    map[string]any{"gatheringId": "gathering-1"},
	}); !errors.Is(err, tooling.ErrGatheringToolDisabled) {
		t.Fatalf("disabled gathering tool error=%v", err)
	}
}

func TestGatheringDispatcherReturnsSchemaOutputAndTypedApproveToolIntent(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	now := time.Date(2026, 8, 6, 6, 0, 0, 0, time.UTC)
	dispatcher, err := tooling.NewGatheringDispatcher(
		catalog,
		tooling.GatheringDispatcherDependencies{
			HostAuthorities: gatheringHostAuthorityResolver{now: now},
			ApprovalIntents: gatheringApprovalIntentIssuer{now: now},
			ProviderState:   tooling.GatheringOptionalProviderState{},
			Now:             func() time.Time { return now },
		},
	)
	if err != nil {
		t.Fatalf("create gathering dispatcher: %v", err)
	}
	registry := gatheringOnlyRegistry(t, dispatcher.Handlers())
	result, err := registry.Execute(context.Background(), tool.Request{
		ToolUseID:      "invocation-1",
		IdempotencyKey: "idempotency-1",
		ToolName:       tooling.GatheringProposeCreateDraftTool,
		Input:          gatheringInputMap(t, gatheringCreateInput()),
		RunID:          "run-1",
		AccountID:      "account-1",
		PersonaID:      "persona-1",
		SurfaceKind:    "personal",
		SurfaceID:      "conversation-1",
	})
	if err != nil {
		t.Fatalf("execute gathering proposal handler: %v", err)
	}
	if result.ApprovalIntent == nil ||
		result.ApprovalIntent.Kind != "ApproveTool" ||
		result.ApprovalIntent.ApproveTool == nil {
		t.Fatalf("typed approval intent=%+v", result.ApprovalIntent)
	}
	proposal, ok := result.TypedProposal.(tooling.GatheringCreateDraftProposal)
	if !ok ||
		proposal.Envelope.Approval != result.ApprovalIntent ||
		proposal.Command.Purpose.Title != gatheringCreateInput().Commitments.Title ||
		len(proposal.Envelope.Degradations) != 3 {
		t.Fatalf("typed gathering proposal=%+v", result.TypedProposal)
	}
	if result.Output["approvalIntentKind"] != "ApproveTool" ||
		result.Output["domainOperationId"] != "circle.gathering.CreateGatheringDraft" {
		t.Fatalf("proposal output=%v", result.Output)
	}
	if _, exposed := result.Output["approval"]; exposed {
		t.Fatal("approval credential must stay outside schema-validated model output")
	}
}

func TestGatheringPlanDispatcherBuildsApprovalWithoutHostAuthority(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	now := time.Date(2026, 8, 6, 6, 0, 0, 0, time.UTC)
	dispatcher, err := tooling.NewGatheringDispatcher(
		catalog,
		tooling.GatheringDispatcherDependencies{
			ApprovalIntents: gatheringApprovalIntentIssuer{now: now},
			Now:             func() time.Time { return now },
		},
	)
	if err != nil {
		t.Fatalf("create gathering dispatcher: %v", err)
	}
	registry := gatheringOnlyRegistry(t, dispatcher.Handlers())
	result, err := registry.Execute(context.Background(), tool.Request{
		ToolUseID:      "invocation-1",
		IdempotencyKey: "idempotency-1",
		ToolName:       tooling.GatheringProposePlanTool,
		Input:          gatheringInputMap(t, gatheringPlanCommand()),
		RunID:          "run-1",
		AccountID:      "account-1",
		PersonaID:      "persona-1",
		SurfaceKind:    "group",
		SurfaceID:      "conversation-1",
	})
	if err != nil {
		t.Fatalf("execute gathering plan proposal handler: %v", err)
	}
	proposal, ok := result.TypedProposal.(tooling.GatheringPlanProposal)
	if !ok ||
		proposal.Envelope.Approval != result.ApprovalIntent ||
		proposal.Envelope.Binding.OperationID !=
			"circle.gathering_plan.ProposeGatheringPlan" ||
		proposal.Command.PlanID != "plan-1" {
		t.Fatalf("typed plan proposal=%+v", result.TypedProposal)
	}
	if result.Output["domainOperationId"] !=
		"circle.gathering_plan.ProposeGatheringPlan" ||
		result.Output["approvalIntentKind"] != "ApproveTool" {
		t.Fatalf("plan proposal output=%v", result.Output)
	}
}

func TestGatheringProductionJTIStoreConsumesCommandGrantOnce(t *testing.T) {
	store, err := gatheringinfrastructure.NewRedisDelegatedGrantJTIStore(
		rtredis.NewMemoryClient(),
	)
	if err != nil {
		t.Fatalf("create gathering JTI store: %v", err)
	}
	expiresAt := time.Now().UTC().Add(time.Minute)
	consumed, err := store.Consume(t.Context(), "command-jti-1", expiresAt)
	if err != nil || !consumed {
		t.Fatalf("first JTI consumption consumed=%v err=%v", consumed, err)
	}
	consumed, err = store.Consume(t.Context(), "command-jti-1", expiresAt)
	if err != nil {
		t.Fatalf("replayed JTI store operation: %v", err)
	}
	if consumed {
		t.Fatal("replayed command JTI must fail closed")
	}
}

func gatheringOnlyRegistry(
	t *testing.T,
	handlers map[string]tool.Handler,
) tool.Registry {
	t.Helper()
	registry := tool.NewRegistry()
	registered := 0
	for _, metadata := range tool.CanonicalMetadata() {
		handler, found := handlers[metadata.ToolName]
		if !found {
			continue
		}
		registry.Register(metadata, handler)
		registered++
	}
	if registered != 7 {
		t.Fatalf("canonical gathering metadata registered=%d, want 7", registered)
	}
	return registry
}

func gatheringInputMap(t *testing.T, value any) map[string]any {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("encode gathering input: %v", err)
	}
	output := map[string]any{}
	if err := json.Unmarshal(encoded, &output); err != nil {
		t.Fatalf("decode gathering input: %v", err)
	}
	return output
}

type gatheringHostAuthorityResolver struct {
	now time.Time
}

func (resolver gatheringHostAuthorityResolver) ResolveGatheringHostAuthority(
	_ context.Context,
	_ tooling.GatheringExecutionContext,
	request tooling.GatheringHostAuthorityRequest,
) (tooling.VerifiedGatheringHostAuthority, error) {
	authority := gatheringHostAuthority(resolver.now)
	authority.GatheringID = request.GatheringID
	if request.HostSubjectKind != "" {
		authority.HostSubjectKind = request.HostSubjectKind
	}
	if request.HostSubjectID != "" {
		authority.HostSubjectID = request.HostSubjectID
	}
	return authority, nil
}

type gatheringApprovalIntentIssuer struct {
	now time.Time
}

func (issuer gatheringApprovalIntentIssuer) IssueGatheringApprovalIntent(
	context.Context,
	tooling.GatheringExecutionContext,
	tooling.GatheringToolDefinition,
) (tooling.GatheringApprovalIntentContext, error) {
	return gatheringIntent(issuer.now), nil
}
