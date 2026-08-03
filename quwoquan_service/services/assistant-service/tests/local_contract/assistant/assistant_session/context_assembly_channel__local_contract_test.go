// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md
package local_contract

import (
	"context"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	prompting "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/prompting"
	"strconv"
	"strings"
	"testing"
	"time"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/channel"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/contextassembly"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type contextAssemblyRecordingModel struct {
	calls            int
	askSlotID        string
	assemblies       []*contextassembly.AssemblyResult
	sessionFacts     [][]preferencemodel.Snapshot
	longTermFacts    [][]preferencemodel.Snapshot
	contextSummaries []*assistant.AssistantSessionContextSummary
	contextTurns     [][]assistant.AssistantSessionContextTurn
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
	model.sessionFacts = append(model.sessionFacts, req.SessionPreferenceFacts)
	model.longTermFacts = append(model.longTermFacts, req.LongTermPreferenceFacts)
	model.contextSummaries = append(model.contextSummaries, req.ContextSummary)
	model.contextTurns = append(
		model.contextTurns,
		append([]assistant.AssistantSessionContextTurn(nil), req.ContextTurns...),
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
		orchestration.ReactRuntime{Model: model},
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
		SourceRef:      "shared_trip",
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
		t.Fatalf("destination slot=%#v want inferred intersection fact", destination)
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
			SlotSchema: skillpkg.SlotSchema{RequiredSlots: []string{"location"}},
			Channel:    channelpkg.Personal(),
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
				ContextTurns: []assistant.AssistantSessionContextTurn{
					{Role: "user", Text: "目的地是杭州，明天出发"},
					{Role: "user", Text: "目的地是苏州，明天出发"},
				},
			},
			DomainID: "travel",
			SlotSchema: skillpkg.SlotSchema{
				RequiredSlots: []string{"destination", "travel_date"},
				CarryOver:     true,
			},
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
) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error) {
	return []preferencemodel.Snapshot{{
			PreferenceID: "session-tone",
			Scope:        preferencemodel.ScopeSession,
			Kind:         preferencemodel.KindTone,
			Value:        "warm",
			Version:      1,
		}}, []preferencemodel.Snapshot{{
			PreferenceID: "private-language",
			Scope:        preferencemodel.ScopeLongTerm,
			Kind:         preferencemodel.KindLanguage,
			Value:        "zh_cn",
			Version:      1,
		}}, nil
}

type factualMemoryPreferenceReader struct{}

func (factualMemoryPreferenceReader) ResolveActiveSnapshots(
	_ context.Context,
	_, _ string,
) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error) {
	confirmedAt := time.Date(2026, 7, 28, 9, 0, 0, 0, time.UTC)
	return nil, []preferencemodel.Snapshot{{
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
func TestConfirmedFactualMemoryEntersPrivateModelContext(t *testing.T) {
	_, longTermFacts, err := (factualMemoryPreferenceReader{}).ResolveActiveSnapshots(
		t.Context(),
		"persona-memory",
		"session-memory",
	)
	if err != nil {
		t.Fatalf("ResolveActiveSnapshots(): %v", err)
	}
	turn := assistant.AssistantTurn{
		TurnID:                  "execution:memory-context-run",
		SessionID:               "session-memory",
		UserID:                  "persona-memory",
		Status:                  "running",
		Input:                   assistant.AssistantTurnInput{Text: "给我推荐晚餐"},
		LongTermPreferenceFacts: longTermFacts,
		CreatedAt:               time.Now().UTC(),
	}
	if len(turn.LongTermPreferenceFacts) != 1 {
		t.Fatalf("turn long-term memories=%#v", turn.LongTermPreferenceFacts)
	}
	if len(turn.LongTermPreferenceFacts) != 1 ||
		turn.LongTermPreferenceFacts[0].Kind != preferencemodel.KindDietaryRestrictions {
		t.Fatalf("run long-term memories=%#v", turn.LongTermPreferenceFacts)
	}
	if prompt := prompting.FormatFactualMemoriesForPrompt(turn.LongTermPreferenceFacts); !strings.Contains(
		prompt,
		"对花生过敏",
	) || !strings.Contains(prompt, "scope=long_term") {
		t.Fatalf("factual memory prompt=%q", prompt)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestLongSessionUsesTraceableSummaryWithoutPerTurnTruncation(t *testing.T) {
	store := persistence.NewMemorySessionStore()
	now := time.Date(2026, 7, 1, 8, 0, 0, 0, time.UTC)
	if _, _, err := store.InsertSession(t.Context(), assistant.AssistantSession{
		SessionID: "asn_summary_context",
		UserID:    "persona-summary",
		State:     "active",
		CreatedAt: now,
		UpdatedAt: now,
	}); err != nil {
		t.Fatalf("InsertSession(): %v", err)
	}
	summary := assistant.AssistantSessionContextSummary{
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
	swapped, err := store.CompareAndSwapSessionSummary(
		t.Context(),
		"asn_summary_context",
		0,
		0,
		5,
		summary,
		now,
	)
	if err != nil || !swapped {
		t.Fatalf("persist canonical session summary: swapped=%v err=%v", swapped, err)
	}
	persisted, found, err := store.GetSession(t.Context(), "asn_summary_context")
	if err != nil || !found || persisted.ContextSummary == nil {
		t.Fatalf("load canonical session summary: found=%v err=%v", found, err)
	}
	longTail := strings.Repeat("长", 320) + "保留尾部目标"
	turn := assistant.AssistantTurn{
		TurnID:         "execution:summary-current-run",
		SessionID:      persisted.SessionID,
		UserID:         persisted.UserID,
		Status:         "running",
		Input:          assistant.AssistantTurnInput{Text: "继续上面的计划"},
		ContextSummary: persisted.ContextSummary,
		ContextTurns: []assistant.AssistantSessionContextTurn{
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
	if _, _, err := store.InsertSession(t.Context(), assistant.AssistantSession{
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
			swapped, _ := store.CompareAndSwapSessionSummary(
				t.Context(),
				"asn_summary_cas",
				0,
				0,
				1,
				assistant.AssistantSessionContextSummary{
					SummaryID:      "summary-cas",
					Text:           "candidate " + strconv.Itoa(index),
					FromTurnID:     "turn-1",
					ToTurnID:       "turn-1",
					TurnCount:      1,
					ConfirmedSlots: map[string]string{},
				},
				now,
			)
			results <- swapped
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
	replayed, err := store.CompareAndSwapSessionSummary(
		t.Context(),
		"asn_summary_cas",
		0,
		0,
		1,
		assistant.AssistantSessionContextSummary{
			SummaryID:      "summary-cas",
			Text:           "duplicate",
			FromTurnID:     "turn-1",
			ToTurnID:       "turn-1",
			TurnCount:      1,
			ConfirmedSlots: map[string]string{},
		},
		now,
	)
	if err != nil || replayed {
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
	sessionFacts, longTermFacts, err := (channelPreferenceReader{}).ResolveActiveSnapshots(
		t.Context(),
		"persona-channel",
		"group-channel-session",
	)
	if err != nil {
		t.Fatalf("ResolveActiveSnapshots(): %v", err)
	}
	group := assistant.AssistantTurn{
		TurnID:                 "execution:group-channel-run",
		SessionID:              "group-channel-session",
		UserID:                 "persona-channel",
		TurnType:               "proactive",
		Status:                 "running",
		Input:                  assistant.AssistantTurnInput{Text: "群里有人问杭州天气"},
		Trigger:                assistant.AssistantTurnTrigger{Type: "chat_assistant_mentioned", MessageID: "message-channel"},
		SessionPreferenceFacts: sessionFacts,
		CreatedAt:              time.Now().UTC(),
	}
	if len(longTermFacts) != 1 {
		t.Fatalf("reader fixture lost private memory: %#v", longTermFacts)
	}
	if len(group.LongTermPreferenceFacts) != 0 {
		t.Fatalf("group turn leaked private memory: %#v", group.LongTermPreferenceFacts)
	}
	prompt := prompting.FormatModelPreferencesForPrompt(
		group.SessionPreferenceFacts,
		group.LongTermPreferenceFacts,
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
	turn.SessionPreferenceFacts = []preferencemodel.Snapshot{{
		PreferenceID: "session-private", Value: "只推荐高价酒店",
	}}
	turn.LongTermPreferenceFacts = []preferencemodel.Snapshot{{
		PreferenceID: "memory-private", Value: "家庭住址是私密信息",
	}}
	_, failure, err := loop.RunTurn(t.Context(), turn)
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() failure=%+v err=%v", failure, err)
	}
	if len(model.sessionFacts) == 0 || len(model.longTermFacts) == 0 {
		t.Fatal("model was not invoked")
	}
	for index := range model.sessionFacts {
		if len(model.sessionFacts[index]) != 0 || len(model.longTermFacts[index]) != 0 {
			t.Fatalf(
				"shared model call %d leaked session=%#v longTerm=%#v",
				index,
				model.sessionFacts[index],
				model.longTermFacts[index],
			)
		}
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
func TestSharedSurfaceAllowsInternalDomainContextWithoutBecomingPublic(t *testing.T) {
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	now := time.Now().UTC()
	registry, err := skillcontext.NewResolverRegistry(
		skillcontext.RegisteredResolver{
			ResolverRef: "trip.current_context",
			Resolver: sharedContextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
				return skillcontext.ResolvedContext{
					Kind:        "domain",
					SourceRef:   "travel.TripTimelineView:trip-1@sha256:shared",
					Authority:   assistantgenerated.AssistantContextAuthorityDomainCanonical,
					Sensitivity: assistantgenerated.AssistantContextSensitivityInternal,
					CapturedAt:  now,
					TokenCost:   32,
					Value: map[string]any{
						"tripId":       "trip-1",
						"sourceDigest": "sha256:shared",
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
	snapshot, ok := model.assemblies[0].ContextEnvelope["skillContextSnapshot"].(skillcontext.Snapshot)
	if !ok || len(snapshot.Segments) != 1 ||
		snapshot.Segments[0].Sensitivity != assistantgenerated.AssistantContextSensitivityInternal ||
		snapshot.Segments[0].Value["tripId"] != "trip-1" {
		t.Fatalf("shared internal Trip context was rejected or widened: %#v", snapshot)
	}
}
