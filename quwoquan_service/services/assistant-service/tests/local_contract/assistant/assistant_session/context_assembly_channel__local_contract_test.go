// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md
package local_contract

import (
	"context"
	"maps"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	prompting "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/prompting"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
	"strconv"
	"strings"
	"testing"
	"time"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/channel"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/contextassembly"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	sessionmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type contextAssemblyRecordingModel struct {
	calls               int
	askSlotID           string
	assemblies          []*contextassembly.AssemblyResult
	sessionPreferences  [][]preferencemodel.AssistantPreferenceSnapshot
	longTermPreferences [][]preferencemodel.AssistantPreferenceSnapshot
	contextSummaries    []*assistant.AssistantRunContextSummary
	contextTurns        [][]assistant.AssistantRunContextTurn
}

func (*contextAssemblyRecordingModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return durableTestModelCapabilities()
}

type sharedContextResolverFunc func(
	skillcontext.ResolveRequest,
) (skillcontext.ResolvedContext, error)

func (resolver sharedContextResolverFunc) Resolve(
	_ context.Context,
	request skillcontext.ResolveRequest,
) (skillcontext.ResolvedContext, error) {
	return resolver(request)
}

func (model *contextAssemblyRecordingModel) Complete(
	_ context.Context,
	req orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	model.calls++
	model.assemblies = append(model.assemblies, req.ContextAssembly)
	model.sessionPreferences = append(model.sessionPreferences, req.SessionPreferences)
	model.longTermPreferences = append(model.longTermPreferences, req.LongTermPreferences)
	model.contextSummaries = append(model.contextSummaries, req.ContextSummary)
	model.contextTurns = append(
		model.contextTurns,
		append([]assistant.AssistantRunContextTurn(nil), req.ContextTurns...),
	)
	if req.Stage == "reasoning" {
		if model.askSlotID != "" {
			return orchestration.ModelResponse{
				Text: "需要确认旅行目标。",
				StructuredDelta: map[string]any{
					"nextAction": "ask_user",
					"askUser": map[string]any{
						"slotId":   model.askSlotID,
						"prompt":   "你想去哪里旅行？",
						"required": true,
					},
				},
			}, nil
		}
		return orchestration.ModelResponse{
			Text:            `{"nextAction":"answer"}`,
			StructuredDelta: map[string]any{"nextAction": "answer"},
		}, nil
	}
	return orchestration.ModelResponse{
		Text:            "已根据你确认的行程上下文整理建议。",
		StructuredDelta: map[string]any{"userMarkdown": "已根据你确认的行程上下文整理建议。"},
	}, nil
}

func contextAssemblyLoop(
	t *testing.T,
	model orchestration.ModelProvider,
) *orchestration.AgentLoop {
	t.Helper()
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{
			Model: model,
			Tools: canonicalTestToolCoordinator(nil),
		},
		nil,
	)
	loop.Catalog = skillfixture.Loader{}
	loop.PromptAssets = promptassets.MustResolver(t)
	return loop
}

func contextAssemblyTurn(text string) assistant.AssistantTurn {
	return assistant.AssistantTurn{
		SessionID: "session-context-assembly",
		TurnID:    "turn-context-assembly",
		TraceID:   "trace-context-assembly",
		SkillID:   "travel_companion",
		DomainID:  "travel",
		Input:     assistant.AssistantTurnInput{Text: text},
		FrozenPolicySelection: testFrozenPolicySelection(
			"assistant-default",
			"fallback_general_search",
			"assistant",
		),
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestContextAssemblyLetsPlannerClarifyWorkflowSpecificSlot(t *testing.T) {
	model := &contextAssemblyRecordingModel{askSlotID: "destination"}
	loop := contextAssemblyLoop(t, model)
	events, failure, err := loop.RunTurn(
		t.Context(),
		contextAssemblyTurn("帮我规划一次旅行"),
	)
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() failure=%+v err=%v", failure, err)
	}
	if model.calls != 1 {
		t.Fatalf("model calls=%d want planner-driven clarification", model.calls)
	}
	payload := completedPayload(t, events)
	if payload["messageKind"] != "ask_user" ||
		payload["finalAnswerMode"] != "clarify" {
		t.Fatalf("completed payload=%#v want context clarification", payload)
	}
	ask, ok := payload["askUser"].(map[string]any)
	if !ok || ask["slotId"] != "destination" {
		t.Fatalf("askUser=%#v want destination fill task", payload["askUser"])
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestContextAssemblyRecallsAuthorizedIntersectionIntoSlots(t *testing.T) {
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	turn := contextAssemblyTurn("帮我把这次旅行安排好")
	turn.IntersectionEvidence = []assistant.AuthorizedIntersectionEvidence{{
		IntersectionID: "intersection-travel",
		EvidenceID:     "evidence-travel",
		SourceRef:      "gathering:gathering-1",
		ObjectTypeRef:  "place",
		ObjectID:       "place-hangzhou",
		PrimaryText:    "目的地是杭州，明天出发",
		Dimension:      "location",
		VerifiedAt:     time.Date(2026, 7, 28, 10, 0, 0, 0, time.UTC),
	}}
	events, failure, err := loop.RunTurn(t.Context(), turn)
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() failure=%+v err=%v", failure, err)
	}
	if completedPayload(t, events)["finalAnswerMode"] != "full" {
		t.Fatalf("completed payload=%#v want full answer", completedPayload(t, events))
	}
	if len(model.assemblies) == 0 || model.assemblies[0] == nil {
		t.Fatal("model did not receive ContextAssemblyResult")
	}
	assembly := model.assemblies[0]
	if !assembly.CanEnterDomain || len(assembly.FillTasks) != 0 {
		t.Fatalf("assembly=%#v want domain-ready context", assembly)
	}
	destination := assembly.SlotState.Slots["destination"]
	if destination.Value != "杭州" ||
		destination.Source != "intersection" ||
		destination.Status.WireName() != "inferred" {
		t.Fatalf("destination slot=%#v want inferred intersection preference", destination)
	}
	if len(destination.EvidenceIDs) != 1 ||
		destination.EvidenceIDs[0] != "evidence-travel" {
		t.Fatalf("destination evidence=%v", destination.EvidenceIDs)
	}
	if len(assembly.GroundingEvidence) != 1 ||
		assembly.GroundingEvidence[0].EvidenceID != "evidence-travel" ||
		len(assembly.GroundingEvidence[0].SlotIDs) == 0 {
		t.Fatalf("grounding evidence=%#v", assembly.GroundingEvidence)
	}
	for _, hint := range assembly.RecallHints {
		if hint.Text == turn.Input.Text {
			t.Fatalf("recall echoed current input instead of retrieving context: %#v", hint)
		}
	}
}

func contextAssemblyRequiredSlot(
	slotID string,
	valueType string,
	parserRefs []string,
	aliases []string,
	targetSlot string,
	prompt string,
) skillpkg.SlotDefinition {
	return skillpkg.SlotDefinition{
		SlotID:         slotID,
		Required:       true,
		ValueType:      valueType,
		ParserRefs:     parserRefs,
		Aliases:        aliases,
		SourcePriority: []string{skillpkg.SlotSourceUserQuery, skillpkg.SlotSourceDevice, skillpkg.SlotSourceSessionUser},
		Clarification: skillpkg.SlotClarification{
			Policy:      skillpkg.SlotClarificationClarify,
			TargetSlot:  targetSlot,
			Prompt:      prompt,
			RetryPolicy: "single_retry",
		},
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestContextAssemblyDistinguishesStaleAndConflictedSlots(t *testing.T) {
	orchestrator := contextassembly.NewContextOrchestrator()
	stale, err := orchestrator.Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn: assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: "查一下天气"},
			},
			DomainID: "weather",
			Device: contextassembly.DeviceContextResponse{
				Status: "stale",
				Facts:  map[string]any{"cityLabel": "杭州"},
			},
			SlotSchema: skillpkg.SlotSchema{Slots: []skillpkg.SlotDefinition{
				contextAssemblyRequiredSlot(
					"location",
					skillpkg.SlotValueTypeLocation,
					[]string{skillpkg.SlotParserLocationBeforeAlias},
					[]string{"天气"},
					"gps_or_city_location",
					"你想查询哪座城市的天气？",
				),
			}},
			Channel: channelpkg.Personal(),
		},
	)
	if err != nil {
		t.Fatalf("Assemble(stale): %v", err)
	}
	if stale.SlotState.Slots["location"].Status.WireName() != "stale" ||
		len(stale.FillTasks) != 1 {
		t.Fatalf("stale assembly=%#v", stale)
	}

	conflicted, err := orchestrator.Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn: assistant.AssistantTurn{
				TurnID: "turn-conflicted-slots",
				Input:  assistant.AssistantTurnInput{Text: "帮我安排一下"},
				ContextTurns: []assistant.AssistantRunContextTurn{
					{Role: "user", Text: "目的地是杭州，明天出发"},
					{Role: "user", Text: "目的地是苏州，明天出发"},
				},
			},
			DomainID: "travel",
			SlotSchema: skillpkg.SlotSchema{Slots: []skillpkg.SlotDefinition{
				contextAssemblyRequiredSlot(
					"destination",
					skillpkg.SlotValueTypeLocation,
					[]string{skillpkg.SlotParserLocationAfterAlias},
					[]string{"目的地", "去"},
					"gps_or_city_location",
					"你想去哪里旅行？",
				),
				contextAssemblyRequiredSlot(
					"travel_date",
					skillpkg.SlotValueTypeDate,
					[]string{skillpkg.SlotParserTemporalExpression},
					nil,
					"realtime_evidence",
					"你计划哪天出发？",
				),
			}, CarryOver: true},
			Channel: channelpkg.Personal(),
		},
	)
	if err != nil {
		t.Fatalf("Assemble(conflicted): %v", err)
	}
	destination := conflicted.SlotState.Slots["destination"]
	if destination.Status.WireName() != "conflicted" ||
		len(destination.Candidates) != 2 ||
		len(conflicted.FillTasks) != 1 {
		t.Fatalf("conflicted destination=%#v fillTasks=%#v", destination, conflicted.FillTasks)
	}
}

type channelPreferenceReader struct{}

func (channelPreferenceReader) ResolveActiveSnapshots(
	_ context.Context,
	_, _ string,
) ([]preferencemodel.AssistantPreferenceSnapshot, []preferencemodel.AssistantPreferenceSnapshot, error) {
	return []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "session-tone",
			Scope:        preferencemodel.ScopeSession,
			Kind:         preferencemodel.KindTone,
			Value:        "warm",
			Version:      1,
		}}, []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "private-language",
			Scope:        preferencemodel.ScopeLongTerm,
			Kind:         preferencemodel.KindLanguage,
			Value:        "zh_cn",
			Version:      1,
		}}, nil
}

type confirmedMemoryPreferenceReader struct{}

func (confirmedMemoryPreferenceReader) ResolveActiveSnapshots(
	_ context.Context,
	_, _ string,
) ([]preferencemodel.AssistantPreferenceSnapshot, []preferencemodel.AssistantPreferenceSnapshot, error) {
	confirmedAt := time.Date(2026, 7, 28, 9, 0, 0, 0, time.UTC)
	return nil, []preferencemodel.AssistantPreferenceSnapshot{{
		PreferenceID:    "memory-diet",
		Scope:           preferencemodel.ScopeLongTerm,
		Kind:            preferencemodel.KindDietaryRestrictions,
		Value:           "对花生过敏，不吃含花生的食物",
		SourceType:      preferencemodel.SourceSessionConfirmed,
		SourceSessionID: "asn_memory_source",
		ConfirmedAt:     &confirmedAt,
		Version:         1,
	}}, nil
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-001
func TestConfirmedConfirmedMemoryEntersPrivateModelContext(t *testing.T) {
	_, longTermPreferences, err := (confirmedMemoryPreferenceReader{}).ResolveActiveSnapshots(
		t.Context(),
		"persona-memory",
		"session-memory",
	)
	if err != nil {
		t.Fatalf("ResolveActiveSnapshots(): %v", err)
	}
	turn := assistant.AssistantTurn{
		TurnID:              "execution:memory-context-run",
		SessionID:           "session-memory",
		UserID:              "persona-memory",
		Status:              "running",
		Input:               assistant.AssistantTurnInput{Text: "给我推荐晚餐"},
		LongTermPreferences: longTermPreferences,
		CreatedAt:           time.Now().UTC(),
	}
	if len(turn.LongTermPreferences) != 1 {
		t.Fatalf("turn long-term memories=%#v", turn.LongTermPreferences)
	}
	if len(turn.LongTermPreferences) != 1 ||
		turn.LongTermPreferences[0].Kind != preferencemodel.KindDietaryRestrictions {
		t.Fatalf("run long-term memories=%#v", turn.LongTermPreferences)
	}
	if prompt := prompting.FormatConfirmedPreferencesForPrompt(turn.LongTermPreferences); !strings.Contains(
		prompt,
		"对花生过敏",
	) || !strings.Contains(prompt, "scope=long_term") {
		t.Fatalf("confirmed memory prompt=%q", prompt)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestLongSessionUsesTraceableSummaryWithoutPerTurnTruncation(t *testing.T) {
	store := persistence.NewMemorySessionStore()
	now := time.Date(2026, 7, 1, 8, 0, 0, 0, time.UTC)
	if _, _, err := store.InsertSession(t.Context(), sessionmodel.AssistantSession{
		SessionID: "asn_summary_context",
		UserID:    "persona-summary",
		State:     "active",
		CreatedAt: now,
		UpdatedAt: now,
	}); err != nil {
		t.Fatalf("InsertSession(): %v", err)
	}
	summary := sessionmodel.AssistantSessionContextSummary{
		SummaryID:   "summary-traceable",
		Text:        "原始目标：目的地是杭州，明天出发，预算5000元",
		FromTurnID:  "run-history-0",
		ToTurnID:    "run-history-4",
		TurnCount:   5,
		CurrentGoal: "原始目标：安排一次家庭旅行",
		ConfirmedSlots: map[string]string{
			"destination": "杭州",
			"travel_date": "明天",
		},
	}
	commit, err := store.CommitSessionSummary(t.Context(), sessionports.SessionSummaryCommit{
		CompletionEventID:      "completion:run-history-4",
		SessionID:              "asn_summary_context",
		ExpectedVersion:        0,
		ExpectedSourceSequence: 0,
		NextSourceSequence:     5,
		Summary:                summary,
		UpdatedAt:              now,
	})
	if err != nil || !commit.Applied {
		t.Fatalf("persist canonical session summary: result=%+v err=%v", commit, err)
	}
	persisted, found, err := store.GetSession(t.Context(), "asn_summary_context")
	if err != nil || !found || persisted.ContextSummary == nil {
		t.Fatalf("load canonical session summary: found=%v err=%v", found, err)
	}
	longTail := strings.Repeat("长", 320) + "保留尾部目标"
	turn := assistant.AssistantTurn{
		TurnID:    "execution:summary-current-run",
		SessionID: persisted.SessionID,
		UserID:    persisted.UserID,
		Status:    "running",
		Input:     assistant.AssistantTurnInput{Text: "继续上面的计划"},
		ContextSummary: &assistant.AssistantRunContextSummary{
			SummaryID:      persisted.ContextSummary.SummaryID,
			Text:           persisted.ContextSummary.Text,
			FromTurnID:     persisted.ContextSummary.FromTurnID,
			ToTurnID:       persisted.ContextSummary.ToTurnID,
			TurnCount:      persisted.ContextSummary.TurnCount,
			CurrentGoal:    persisted.ContextSummary.CurrentGoal,
			ConfirmedFacts: append([]string(nil), persisted.ContextSummary.ConfirmedFacts...),
			PendingItems:   append([]string(nil), persisted.ContextSummary.PendingItems...),
			ConfirmedSlots: maps.Clone(persisted.ContextSummary.ConfirmedSlots),
		},
		ContextTurns: []assistant.AssistantRunContextTurn{
			{Role: "user", Text: longTail},
		},
		CreatedAt: now,
	}
	if turn.ContextSummary == nil || turn.ContextSummary.ToTurnID != "run-history-4" {
		t.Fatalf("run summary=%#v", turn.ContextSummary)
	}
	if len(turn.ContextTurns) != 1 ||
		!strings.Contains(turn.ContextTurns[0].Text, "保留尾部目标") ||
		len([]rune(turn.ContextTurns[0].Text)) <= 320 {
		t.Fatalf("recent context was truncated: %#v", turn.ContextTurns)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestSessionSummaryCASRejectsConcurrentAndDuplicateSource(t *testing.T) {
	store := persistence.NewMemorySessionStore()
	now := time.Date(2026, 7, 1, 8, 0, 0, 0, time.UTC)
	if _, _, err := store.InsertSession(t.Context(), sessionmodel.AssistantSession{
		SessionID: "asn_summary_cas",
		UserID:    "persona-summary",
		State:     "active",
		CreatedAt: now,
		UpdatedAt: now,
	}); err != nil {
		t.Fatalf("InsertSession(): %v", err)
	}
	results := make(chan bool, 2)
	for index := 0; index < 2; index++ {
		index := index
		go func() {
			commit, _ := store.CommitSessionSummary(t.Context(), sessionports.SessionSummaryCommit{
				CompletionEventID:      "completion:turn-" + strconv.Itoa(index),
				SessionID:              "asn_summary_cas",
				ExpectedVersion:        0,
				ExpectedSourceSequence: 0,
				NextSourceSequence:     1,
				Summary: sessionmodel.AssistantSessionContextSummary{
					SummaryID:      "summary-cas",
					Text:           "candidate " + strconv.Itoa(index),
					FromTurnID:     "turn-1",
					ToTurnID:       "turn-1",
					TurnCount:      1,
					ConfirmedSlots: map[string]string{},
				},
				UpdatedAt: now,
			})
			results <- commit.Applied
		}()
	}
	successes := 0
	for index := 0; index < 2; index++ {
		if <-results {
			successes++
		}
	}
	if successes != 1 {
		t.Fatalf("concurrent CAS successes=%d, want 1", successes)
	}
	replayed, err := store.CommitSessionSummary(t.Context(), sessionports.SessionSummaryCommit{
		CompletionEventID:      "completion:turn-duplicate",
		SessionID:              "asn_summary_cas",
		ExpectedVersion:        0,
		ExpectedSourceSequence: 0,
		NextSourceSequence:     1,
		Summary: sessionmodel.AssistantSessionContextSummary{
			SummaryID:      "summary-cas",
			Text:           "duplicate",
			FromTurnID:     "turn-1",
			ToTurnID:       "turn-1",
			TurnCount:      1,
			ConfirmedSlots: map[string]string{},
		},
		UpdatedAt: now,
	})
	if err != nil || !replayed.Conflict {
		t.Fatalf("duplicate source CAS replayed=%v err=%v", replayed, err)
	}
	persisted, found, err := store.GetSession(t.Context(), "asn_summary_cas")
	if err != nil || !found ||
		persisted.SummaryVersion != 1 ||
		persisted.SummarySourceSequence != 1 {
		t.Fatalf("CAS persisted=%+v found=%v err=%v", persisted, found, err)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-002
func TestGroupMentionChannelExcludesPrivateLongTermMemory(t *testing.T) {
	sessionPreferences, longTermPreferences, err := (channelPreferenceReader{}).ResolveActiveSnapshots(
		t.Context(),
		"persona-channel",
		"group-channel-session",
	)
	if err != nil {
		t.Fatalf("ResolveActiveSnapshots(): %v", err)
	}
	group := assistant.AssistantTurn{
		TurnID:             "execution:group-channel-run",
		SessionID:          "group-channel-session",
		UserID:             "persona-channel",
		TurnType:           "proactive",
		Status:             "running",
		Input:              assistant.AssistantTurnInput{Text: "群里有人问杭州天气"},
		Trigger:            assistant.AssistantTurnTrigger{Type: "chat_assistant_mentioned", MessageID: "message-channel"},
		SessionPreferences: sessionPreferences,
		CreatedAt:          time.Now().UTC(),
	}
	if len(longTermPreferences) != 1 {
		t.Fatalf("reader fixture lost private memory: %#v", longTermPreferences)
	}
	if len(group.LongTermPreferences) != 0 {
		t.Fatalf("group turn leaked private memory: %#v", group.LongTermPreferences)
	}
	prompt := prompting.FormatModelPreferencesForPrompt(
		group.SessionPreferences,
		group.LongTermPreferences,
	)
	if strings.Contains(prompt, "使用简体中文回答") {
		t.Fatalf("group prompt leaked private long-term memory: %q", prompt)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
func TestSharedSurfacePhysicallyRemovesPersonalPreferencesBeforeModelUse(t *testing.T) {
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	turn := contextAssemblyTurn("帮群里规划杭州行程")
	turn.UserID = "account-channel"
	turn.RequestContext = assistant.AssistantRunRequestContext{
		SurfaceKind: "conversation",
		SurfaceID:   "conversation-channel",
		PersonaID:   "persona-channel",
	}
	turn.SessionPreferences = []preferencemodel.AssistantPreferenceSnapshot{{
		PreferenceID: "session-private", Value: "只推荐高价酒店",
	}}
	turn.LongTermPreferences = []preferencemodel.AssistantPreferenceSnapshot{{
		PreferenceID: "memory-private", Value: "家庭住址是私密信息",
	}}
	_, failure, err := loop.RunTurn(t.Context(), turn)
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() failure=%+v err=%v", failure, err)
	}
	if len(model.sessionPreferences) == 0 || len(model.longTermPreferences) == 0 {
		t.Fatal("model was not invoked")
	}
	for index := range model.sessionPreferences {
		if len(model.sessionPreferences[index]) != 0 || len(model.longTermPreferences[index]) != 0 {
			t.Fatalf(
				"shared model call %d leaked session=%#v longTerm=%#v",
				index,
				model.sessionPreferences[index],
				model.longTermPreferences[index],
			)
		}
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
func TestSharedSurfaceAllowsInternalDomainContextWithoutBecomingPublic(t *testing.T) {
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	now := time.Now().UTC()
	sourceDigest := canonicalContextFixtureDigest(struct {
		ConversationID string `json:"conversationId"`
		MessageCount   int64  `json:"messageCount"`
	}{ConversationID: "conversation-channel", MessageCount: 2})
	descriptor, err := readermodel.NewDescriptor(readermodel.Descriptor{
		DescriptorID:        "chat.conversation_context",
		ResolverRef:         "conversation.current_context",
		OwnerService:        "assistant-service",
		OwnerOperationRefs:  []string{"assistant.assistant_run.GetAssistantRun"},
		InputSchemaRef:      "assistant.GetAssistantRunQuery",
		OutputSchemaRef:     "assistant.ContextSegment",
		ObjectTypeRefs:      []string{"chat.Conversation"},
		AcceptedSourceKinds: []string{"conversation"},
		Authority:           assistantgenerated.AssistantContextAuthorityDomainCanonical,
		Sensitivity:         assistantgenerated.AssistantContextSensitivityInternal,
		SurfaceKinds: []readermodel.SurfaceKind{
			readermodel.SurfacePersonal,
			readermodel.SurfaceShared,
		},
		ArtifactPolicy: readermodel.ArtifactInlineOrStored,
		CitationPolicy: readermodel.CitationEntityReference,
	})
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog([]readermodel.Descriptor{descriptor})
	if err != nil {
		t.Fatal(err)
	}
	registry, err := skillcontext.NewResolverRegistry(
		catalog,
		skillcontext.RegisteredResolver{
			ResolverRef: descriptor.ResolverRef,
			Resolver: sharedContextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
				return skillcontext.ResolvedContext{
					Kind:        "conversation",
					SourceRef:   "chat.Conversation:conversation-channel@" + sourceDigest,
					Authority:   assistantgenerated.AssistantContextAuthorityDomainCanonical,
					Sensitivity: assistantgenerated.AssistantContextSensitivityInternal,
					CapturedAt:  now,
					TokenCost:   32,
					Value: map[string]any{
						"conversationId": "conversation-channel",
						"sourceDigest":   sourceDigest,
					},
				}, nil
			}),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	loop.SkillContexts = skillcontext.NewAssembler(
		registry,
		skillcontext.ConsentReaderFunc(func(
			context.Context,
			string,
			string,
			[]string,
		) (bool, error) {
			return true, nil
		}),
	)
	turn := contextAssemblyTurn("帮群里调整这次旅行")
	turn.UserID = "account-channel"
	turn.RequestContext = assistant.AssistantRunRequestContext{
		SurfaceKind: "conversation",
		SurfaceID:   "conversation-channel",
		PersonaID:   "persona-channel",
	}

	_, failure, err := loop.RunTurn(t.Context(), turn)
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() failure=%+v err=%v", failure, err)
	}
	if len(model.assemblies) == 0 || model.assemblies[0] == nil {
		t.Fatal("model did not receive shared context assembly")
	}
	snapshot := model.assemblies[0].SkillContextSnapshot
	if snapshot == nil || len(snapshot.Segments) != 1 ||
		snapshot.Segments[0].Sensitivity != assistantgenerated.AssistantContextSensitivityInternal ||
		snapshot.Segments[0].Value["conversationId"] != "conversation-channel" {
		t.Fatalf("shared internal conversation context was rejected or widened: %#v", snapshot)
	}
	prompt, err := contextassembly.FormatForPrompt(model.assemblies[0])
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		"context[conversation_context]",
		`"conversationId":"conversation-channel"`,
		"authority=domain_canonical",
	} {
		if !strings.Contains(prompt, want) {
			t.Fatalf("model prompt missing %q: %s", want, prompt)
		}
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestSkillContextPromptFailsClosedWhenCanonicalValueCannotBeEncoded(t *testing.T) {
	_, err := contextassembly.FormatForPrompt(&contextassembly.AssemblyResult{
		SkillContextSnapshot: &skillcontext.Snapshot{
			SnapshotID: "context-invalid",
			Segments: []skillcontext.Segment{{
				SegmentID: "segment-invalid",
				SlotID:    "gathering_context",
				Value: map[string]any{
					"invalid": func() {},
				},
			}},
		},
	})
	if err == nil || !strings.Contains(err.Error(), "segment-invalid") {
		t.Fatalf("FormatForPrompt() error=%v, want segment-scoped encoding failure", err)
	}
}
