package assistant_run

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
	"time"

	gatheringplanclient "quwoquan_service/generated/serviceclients/circlegatheringplan"
	tooling "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tooling"

	"gopkg.in/yaml.v3"
)

type gatheringJSONSchema struct {
	Type                 string                         `yaml:"type"`
	AdditionalProperties *bool                          `yaml:"additionalProperties"`
	Properties           map[string]gatheringJSONSchema `yaml:"properties"`
	Items                *gatheringJSONSchema           `yaml:"items"`
	Required             []string                       `yaml:"required"`
}

type gatheringCatalogTool struct {
	tooling.GatheringToolDefinition `yaml:",inline"`
	InputSchema                     gatheringJSONSchema `yaml:"inputSchema"`
	OutputSchema                    gatheringJSONSchema `yaml:"outputSchema"`
}

func TestGatheringToolCatalogIsTypedClosedAndPolicyComplete(t *testing.T) {
	document := readGatheringCatalog(t)
	encoded, err := json.Marshal(document.Tools)
	if err != nil {
		t.Fatalf("encode typed catalog projection: %v", err)
	}
	catalog, err := tooling.ParseGatheringBindingCatalog(encoded)
	if err != nil {
		t.Fatalf("parse gathering binding catalog: %v", err)
	}

	expected := []string{
		tooling.GatheringSearchPublicTool,
		tooling.GatheringReadPublicTool,
		tooling.GatheringReadPrivateTool,
		tooling.GatheringProposeCreateDraftTool,
		tooling.GatheringProposeUpdateTool,
		tooling.GatheringProposePlanTool,
		tooling.GatheringWatchAvailabilityTool,
	}
	for _, toolName := range expected {
		definition, found := catalog.Definition(toolName)
		if !found {
			t.Fatalf("gathering definition %q missing", toolName)
		}
		if definition.RiskTier == "" ||
			definition.OwnerService == "" ||
			definition.OwnerOperationID == "" ||
			!strings.HasPrefix(definition.ContractDigest, "sha256:") ||
			definition.RequiredAuth.GrantKind == "" ||
			definition.RequiredCapability == "" ||
			definition.ApprovalPolicy.Mode == "" ||
			definition.Idempotency == "" ||
			definition.Redaction.Policy == "" ||
			definition.Audit.EventName == "" {
			t.Fatalf("gathering definition %q has incomplete policy: %+v", toolName, definition)
		}
	}
	circleOperations := readCircleGatheringOperations(t)
	for _, toolName := range expected {
		definition, _ := catalog.Definition(toolName)
		if definition.OwnerService != "circle-service" {
			continue
		}
		operation, found := circleOperations[definition.OwnerOperationID]
		if !found ||
			operation.RequestEntity != definition.OwnerRequestEntity ||
			operation.ResponseEntity != definition.OwnerResponseEntity {
			t.Fatalf(
				"tool %s owner binding=%+v canonical=%+v found=%v",
				toolName,
				definition,
				operation,
				found,
			)
		}
	}

	for _, raw := range document.Tools {
		if !strings.HasPrefix(raw.ToolName, "gathering.") {
			continue
		}
		assertGatheringSchemaClosed(t, raw.ToolName+".input", raw.InputSchema)
		assertGatheringSchemaClosed(t, raw.ToolName+".output", raw.OutputSchema)
	}

	plan, _ := catalog.Definition(tooling.GatheringProposePlanTool)
	if plan.OwnerService != "circle-service" ||
		plan.OwnerOperationID !=
			"circle.gathering_plan.ProposeGatheringPlan" ||
		plan.RequiredAuth.GrantKind !=
			"delegated_command_after_approval" ||
		plan.ExecutionPolicy.Mode != "proposal_only" {
		t.Fatalf("plan must bind the Circle proposal operation: %+v", plan)
	}
}

func TestGatheringProposalMapperRejectsHostForgeryAndBindingDrift(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringProposeCreateDraftTool)
	now := time.Date(2026, 8, 6, 6, 0, 0, 0, time.UTC)
	execution := gatheringExecution(tooling.GatheringConversationDirect)
	input := gatheringCreateInput()
	authority := gatheringHostAuthority(now)
	intent := gatheringIntent(now)

	forged := input
	forged.HostSubjectID = "host-forged"
	if _, err := tooling.MapGatheringCreateDraftProposal(
		execution,
		definition,
		forged,
		authority,
		intent,
		gatheringProvidersAvailable(),
		now,
	); !errors.Is(err, tooling.ErrGatheringHostUnauthorized) {
		t.Fatalf("host impersonation error=%v", err)
	}

	proposal, err := tooling.MapGatheringCreateDraftProposal(
		execution,
		definition,
		input,
		authority,
		intent,
		gatheringProvidersAvailable(),
		now,
	)
	if err != nil {
		t.Fatalf("map create proposal: %v", err)
	}
	expectedTarget := proposal.Envelope.Binding.Target
	expectedDigest := proposal.Envelope.RequestDigest
	for name, mutate := range map[string]func(*tooling.DomainOperationBinding){
		"operation": func(binding *tooling.DomainOperationBinding) {
			binding.OperationID = "circle.gathering.CancelGathering"
		},
		"target": func(binding *tooling.DomainOperationBinding) {
			binding.Target.ID = "other-proposal"
		},
		"digest": func(binding *tooling.DomainOperationBinding) {
			binding.RequestDigest = "sha256:" + strings.Repeat("f", 64)
		},
	} {
		t.Run(name, func(t *testing.T) {
			binding := proposal.Envelope.Binding
			mutate(&binding)
			if err := binding.ValidateAgainst(
				definition,
				expectedDigest,
				expectedTarget,
			); !errors.Is(err, tooling.ErrGatheringBindingInvalid) {
				t.Fatalf("binding drift error=%v", err)
			}
		})
	}
}

func TestGatheringCoordinatorDegradesProvidersAndUsesSameToolAcrossChats(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringProposeCreateDraftTool)
	now := time.Date(2026, 8, 6, 6, 0, 0, 0, time.UTC)
	input := gatheringCreateInput()
	authority := gatheringHostAuthority(now)
	intent := gatheringIntent(now)
	unavailable := tooling.GatheringOptionalProviderState{}

	direct, err := tooling.MapGatheringCreateDraftProposal(
		gatheringExecution(tooling.GatheringConversationDirect),
		definition,
		input,
		authority,
		intent,
		unavailable,
		now,
	)
	if err != nil {
		t.Fatalf("direct-chat proposal with unavailable providers: %v", err)
	}
	group, err := tooling.MapGatheringCreateDraftProposal(
		gatheringExecution(tooling.GatheringConversationGroup),
		definition,
		input,
		authority,
		intent,
		unavailable,
		now,
	)
	if err != nil {
		t.Fatalf("group-chat proposal with unavailable providers: %v", err)
	}
	if direct.Envelope.RequestDigest != group.Envelope.RequestDigest ||
		direct.Envelope.Binding != group.Envelope.Binding {
		t.Fatal("direct and group conversations must use the same typed proposal contract")
	}
	if !reflect.DeepEqual(
		direct.Envelope.Degradations,
		[]tooling.GatheringProviderDegradation{
			tooling.GatheringMapUnavailable,
			tooling.GatheringWeatherUnavailable,
			tooling.GatheringCalendarUnavailable,
		},
	) {
		t.Fatalf("provider degradations=%v", direct.Envelope.Degradations)
	}
	if direct.Envelope.Approval == nil ||
		direct.Envelope.Approval.Kind != "ApproveTool" {
		t.Fatal("write proposal must produce an ApproveTool intent")
	}

	if !reflect.DeepEqual(
		tooling.GatheringCoordinatorSequence(),
		[]tooling.GatheringCoordinatorStep{
			tooling.GatheringCoordinatorPrefillSources,
			tooling.GatheringCoordinatorAskCommitments,
			tooling.GatheringCoordinatorDraftProposal,
			tooling.GatheringCoordinatorAwaitApproval,
			tooling.GatheringCoordinatorBindOperation,
		},
	) {
		t.Fatalf("coordinator sequence=%v", tooling.GatheringCoordinatorSequence())
	}
	if !reflect.DeepEqual(
		tooling.GatheringCoordinatorReferencedCapabilities(),
		[]string{
			"location.poi.search",
			"location.route.read",
			"weather.forecast.read",
			"calendar.event.create",
			"calendar.event.update",
			"calendar.event.delete",
		},
	) {
		t.Fatal("coordinator must reference existing capability keys without cloning tools")
	}
}

func TestGatheringProposalCarriesOnlyResolvedPublicProviderEvidence(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringProposeCreateDraftTool)
	now := time.Date(2026, 8, 6, 6, 1, 0, 0, time.UTC)
	proposal, err := tooling.MapGatheringCreateDraftProposal(
		gatheringExecution(tooling.GatheringConversationDirect),
		definition,
		gatheringCreateInput(),
		gatheringHostAuthority(now),
		gatheringIntent(now),
		tooling.GatheringOptionalProviderState{
			WeatherAvailable: true,
			Evidence: []tooling.GatheringProviderBindingEvidence{
				{
					CapabilityKey: "weather.forecast.read",
					BindingKind:   "public_provider",
					BindingRef:    "environment_binding:assistant.weather.forecast",
				},
				{
					CapabilityKey: "location.poi.search",
					BindingKind:   "public_provider",
					BindingRef:    "environment_binding:integration.location.poi",
				},
			},
		},
		now,
	)
	if err != nil {
		t.Fatalf("map proposal with weather provider evidence: %v", err)
	}
	if !reflect.DeepEqual(
		proposal.Envelope.Degradations,
		[]tooling.GatheringProviderDegradation{
			tooling.GatheringMapUnavailable,
			tooling.GatheringCalendarUnavailable,
		},
	) {
		t.Fatalf("provider degradations=%v", proposal.Envelope.Degradations)
	}
	if !reflect.DeepEqual(
		proposal.Envelope.ProviderEvidence,
		[]tooling.GatheringProviderBindingEvidence{{
			CapabilityKey: "weather.forecast.read",
			BindingKind:   "public_provider",
			BindingRef:    "environment_binding:assistant.weather.forecast",
		}},
	) {
		t.Fatalf(
			"provider evidence=%+v",
			proposal.Envelope.ProviderEvidence,
		)
	}
}

func TestGatheringPlanProducesCanonicalProposalWithoutAutomaticCommit(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	definition, _ := catalog.Definition(tooling.GatheringProposePlanTool)
	now := time.Date(2026, 8, 6, 6, 0, 0, 0, time.UTC)
	command := gatheringPlanCommand()
	proposal, err := tooling.MapGatheringPlanProposal(
		gatheringExecution(tooling.GatheringConversationGroup),
		definition,
		command,
		gatheringIntent(now),
	)
	if err != nil {
		t.Fatalf("map canonical plan proposal: %v", err)
	}
	if proposal.Envelope.Binding.OperationID !=
		"circle.gathering_plan.ProposeGatheringPlan" ||
		proposal.Envelope.Binding.Target.Type != "circle.gathering_plan" ||
		proposal.Envelope.Binding.Target.ID != command.PlanID ||
		proposal.Envelope.Approval == nil ||
		proposal.Envelope.Approval.Kind != "ApproveTool" {
		t.Fatalf("plan proposal=%+v", proposal)
	}

	for _, operationID := range []string{
		"circle.gathering.ReviewGatheringApplication",
		"circle.gathering.InviteToGathering",
		"circle.gathering.RemoveGatheringParticipant",
		"circle.gathering.ChangeGatheringCapacity",
		"circle.gathering.UpdateGathering",
		"circle.gathering.CancelGathering",
		"circle.gathering.CompleteGathering",
		"circle.gathering.AcknowledgeGatheringRevision",
		"circle.gathering_plan.CreateGatheringPlan",
		"circle.gathering_plan.CommitGatheringPlanProposal",
	} {
		if err := tooling.RejectAutomaticGatheringHostOperation(operationID); !errors.Is(
			err,
			tooling.ErrGatheringAutomaticAction,
		) {
			t.Fatalf("automatic owner operation %s error=%v", operationID, err)
		}
	}
	if err := tooling.RejectAutomaticGatheringHostOperation(
		"circle.gathering.WatchGatheringAvailability",
	); err != nil {
		t.Fatalf("confirmed low-risk watch should remain executable: %v", err)
	}
	if err := tooling.RejectAutomaticGatheringHostOperation(
		"circle.gathering_plan.ProposeGatheringPlan",
	); err != nil {
		t.Fatalf("confirmed plan proposal should be executable: %v", err)
	}
}

func TestGatheringUpdateAndWatchAreConfirmationProposalsOnly(t *testing.T) {
	catalog := gatheringBindingCatalog(t)
	now := time.Date(2026, 8, 6, 6, 0, 0, 0, time.UTC)
	execution := gatheringExecution(tooling.GatheringConversationDirect)
	authority := gatheringHostAuthority(now)
	authority.GatheringID = "gathering-1"
	intent := gatheringIntent(now)
	createInput := gatheringCreateInput()

	updateDefinition, _ := catalog.Definition(tooling.GatheringProposeUpdateTool)
	update, err := tooling.MapGatheringUpdateProposal(
		execution,
		updateDefinition,
		tooling.GatheringUpdateProposalInput{
			GatheringID:               "gathering-1",
			ExpectedGatheringVersion:  3,
			HostSubjectKind:           createInput.HostSubjectKind,
			HostSubjectID:             createInput.HostSubjectID,
			Commitments:               createInput.Commitments,
			AcknowledgementDeadlineAt: "2026-08-07T18:00:00+08:00",
		},
		authority,
		intent,
		gatheringProvidersAvailable(),
		now,
	)
	if err != nil {
		t.Fatalf("map update proposal: %v", err)
	}
	if update.Envelope.Approval == nil ||
		update.Envelope.Approval.Kind != "ApproveTool" ||
		update.Envelope.Binding.OperationID != "circle.gathering.UpdateGathering" {
		t.Fatalf("update proposal=%+v", update.Envelope)
	}

	watchDefinition, _ := catalog.Definition(tooling.GatheringWatchAvailabilityTool)
	watch, err := tooling.MapGatheringAvailabilityWatchProposal(
		execution,
		watchDefinition,
		tooling.GatheringAvailabilityWatchCommand{
			GatheringID:              "gathering-1",
			ExpectedGatheringVersion: 3,
			ExpectedWatchVersion:     0,
		},
		intent,
	)
	if err != nil {
		t.Fatalf("map watch proposal: %v", err)
	}
	if watch.Envelope.Approval == nil ||
		watch.Envelope.Approval.Kind != "ApproveTool" ||
		watch.Envelope.Binding.OperationID != "circle.gathering.WatchGatheringAvailability" {
		t.Fatalf("watch proposal=%+v", watch.Envelope)
	}
}

func assertGatheringSchemaClosed(
	t *testing.T,
	path string,
	schema gatheringJSONSchema,
) {
	t.Helper()
	if schema.Type == "object" {
		if schema.AdditionalProperties == nil || *schema.AdditionalProperties {
			t.Fatalf("%s must be a closed object", path)
		}
		for name, property := range schema.Properties {
			assertGatheringSchemaClosed(t, path+"."+name, property)
		}
	}
	if schema.Items != nil {
		assertGatheringSchemaClosed(t, path+"[]", *schema.Items)
	}
}

func gatheringBindingCatalog(t *testing.T) tooling.GatheringBindingCatalog {
	t.Helper()
	document := readGatheringCatalog(t)
	encoded, err := json.Marshal(document.Tools)
	if err != nil {
		t.Fatalf("encode gathering definitions: %v", err)
	}
	catalog, err := tooling.ParseGatheringBindingCatalog(encoded)
	if err != nil {
		t.Fatalf("parse gathering catalog: %v", err)
	}
	return catalog
}

func readGatheringCatalog(t *testing.T) struct {
	Tools []gatheringCatalogTool `yaml:"tools"`
} {
	t.Helper()
	_, testFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve gathering test path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(testFile), "../../../.."))
	payload, err := os.ReadFile(filepath.Join(
		serviceRoot,
		"contracts/_shared/assistant_tool_metadata/catalog.yaml",
	))
	if err != nil {
		t.Fatalf("read gathering catalog: %v", err)
	}
	var document struct {
		Tools []gatheringCatalogTool `yaml:"tools"`
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatalf("decode gathering catalog: %v", err)
	}
	return document
}

type circleGatheringOperation struct {
	Operation      string `yaml:"operation"`
	RequestEntity  string `yaml:"request_entity"`
	ResponseEntity string `yaml:"response_entity"`
}

func readCircleGatheringOperations(
	t *testing.T,
) map[string]circleGatheringOperation {
	t.Helper()
	_, testFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve gathering test path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(testFile), "../../../.."))
	operations := make(map[string]circleGatheringOperation)
	for objectName, operationPrefix := range map[string]string{
		"gathering":      "circle.gathering.",
		"gathering_plan": "circle.gathering_plan.",
	} {
		payload, err := os.ReadFile(filepath.Join(
			serviceRoot,
			"../circle-service/contracts/circle_management",
			objectName,
			"operations.yaml",
		))
		if err != nil {
			t.Fatalf("read Circle %s operations: %v", objectName, err)
		}
		var document struct {
			APIRoutes []circleGatheringOperation `yaml:"api_routes"`
		}
		if err := yaml.Unmarshal(payload, &document); err != nil {
			t.Fatalf("decode Circle %s operations: %v", objectName, err)
		}
		for _, operation := range document.APIRoutes {
			operations[operationPrefix+operation.Operation] = operation
		}
	}
	return operations
}

func gatheringExecution(
	kind tooling.GatheringConversationKind,
) tooling.GatheringExecutionContext {
	return tooling.GatheringExecutionContext{
		AccountID:        "account-1",
		PersonaID:        "persona-1",
		RunID:            "run-1",
		ToolInvocationID: "invocation-1",
		Surface:          tooling.GatheringConversationSurface,
		IdempotencyKey:   "idempotency-1",
		ApprovalRef:      "approval-1",
		Conversation: tooling.GatheringConversationContext{
			Kind:           kind,
			ConversationID: "conversation-1",
		},
	}
}

func gatheringHostAuthority(now time.Time) tooling.VerifiedGatheringHostAuthority {
	return tooling.VerifiedGatheringHostAuthority{
		AccountID:            "account-1",
		PersonaID:            "persona-1",
		HostSubjectKind:      "persona",
		HostSubjectID:        "host-1",
		AuthorityEvidenceRef: "authority-evidence-1",
		AuthorityVersion:     3,
		AuthorityExpiresAt:   now.Add(time.Hour),
	}
}

func gatheringIntent(now time.Time) tooling.GatheringApprovalIntentContext {
	return tooling.GatheringApprovalIntentContext{
		IntentID:       "intent-1",
		JTI:            "intent-jti-1",
		ApprovalPermit: "signed-approval-permit",
		IssuedAt:       now,
		ExpiresAt:      now.Add(time.Minute),
	}
}

func gatheringProvidersAvailable() tooling.GatheringOptionalProviderState {
	return tooling.GatheringOptionalProviderState{
		MapAvailable:      true,
		WeatherAvailable:  true,
		CalendarAvailable: true,
	}
}

func gatheringPlanCommand() gatheringplanclient.ProposeGatheringPlanCommand {
	return gatheringplanclient.ProposeGatheringPlanCommand{
		PlanID:              "plan-1",
		ExpectedPlanVersion: 2,
		BaseRevisionID:      "revision-1",
		BaseRevisionNumber:  1,
		BaseRevisionDigest:  "sha256:" + strings.Repeat("a", 64),
		Items: []gatheringplanclient.PlanItem{{
			ItemID: "item-1",
			Kind:   gatheringplanclient.PlanItemKindNote,
			Order:  1,
			Note: &gatheringplanclient.PlanNoteItem{
				Content: "确认集合时间",
			},
			SourceRefs: []gatheringplanclient.GatheringPlanSourceRef{},
		}},
		AcknowledgementPolicy: gatheringplanclient.PlanAcknowledgementPolicy{
			Mode: gatheringplanclient.PlanAcknowledgementModeNone,
		},
		AffectedParticipationRefs: []gatheringplanclient.GatheringPlanParticipationRef{},
	}
}

func gatheringCreateInput() tooling.GatheringCreateDraftProposalInput {
	return tooling.GatheringCreateDraftProposalInput{
		HostSubjectKind:     "persona",
		HostSubjectID:       "host-1",
		CreatorParticipates: true,
		Commitments: tooling.GatheringCommitments{
			Title:           "周末徒步",
			Summary:         "从内容页发起的聚会",
			TopicRefs:       []string{"hiking"},
			RequirementRefs: []string{"comfortable-shoes"},
			SourceRefs: []tooling.GatheringSourceRef{{
				ObjectRef: tooling.CanonicalObjectRef{
					ObjectTypeRef: "content.post",
					ObjectID:      "post-1",
				},
				RouteID:      "content.post.detail",
				SourceDigest: "sha256:" + strings.Repeat("0", 64),
			}},
			CostNotice:           "free",
			CostDescription:      "",
			Timezone:             "Asia/Shanghai",
			StartAt:              "2026-08-08T09:00:00+08:00",
			EndAt:                "2026-08-08T12:00:00+08:00",
			AdmissionClosesAt:    "2026-08-07T18:00:00+08:00",
			PlaceMode:            "physical",
			CoarsePlaceLabel:     "西湖区",
			ExactMeetingPoint:    "",
			OnlineLocationRef:    "",
			AudiencePolicy:       "public",
			AdmissionPolicy:      "approval_required",
			MaxParticipants:      8,
			TimeDisclosure:       "public",
			PlaceDisclosure:      "participants_only",
			RosterDisclosure:     "participants_only",
			ApplicationQuestions: []tooling.GatheringApplicationQuestion{},
			RiskControlPolicyRef: "gathering.standard",
			PolicyDecisionRef:    "",
			PolicyDigest:         "",
			ObligationDigest:     "",
		},
	}
}
