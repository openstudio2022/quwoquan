// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md
package local_contract

import (
	"context"
	prompting "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/prompting"
	"strconv"
	"strings"
	"testing"
	"time"

	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/channel"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/contextassembly"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/domain/model"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
)

type contextAssemblyRecordingModel struct {
	calls            int
	assemblies       []*contextassembly.AssemblyResult
	longTermFacts    [][]preferencemodel.Snapshot
	contextSummaries []*assistant.AssistantConversationContextSummary
	contextTurns     [][]assistant.AssistantConversationContextTurn
}

func (model *contextAssemblyRecordingModel) Complete(
	_ context.Context,
	req orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	model.calls++
	model.assemblies = append(model.assemblies, req.ContextAssembly)
	model.longTermFacts = append(model.longTermFacts, req.LongTermPreferenceFacts)
	model.contextSummaries = append(model.contextSummaries, req.ContextSummary)
	model.contextTurns = append(
		model.contextTurns,
		append([]assistant.AssistantConversationContextTurn(nil), req.ContextTurns...),
	)
	if req.Stage == "reasoning" {
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
	loop.PromptAssets = promptassets.MustResolver(t)
	return loop
}

func contextAssemblyTurn(text string) assistant.AssistantTurn {
	return assistant.AssistantTurn{
		ConversationID: "conversation-context-assembly",
		TurnID:         "turn-context-assembly",
		TraceID:        "trace-context-assembly",
		Input:          assistant.AssistantTurnInput{Text: text},
		FrozenPolicySelection: testFrozenPolicySelection(
			"assistant-default",
			"travel_planning",
			"travel_planning",
		),
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestContextAssemblyAsksForMissingSlotBeforeModelCall(t *testing.T) {
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	events, failure, err := loop.RunTurn(
		t.Context(),
		contextAssemblyTurn("帮我规划一次旅行"),
	)
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() failure=%+v err=%v", failure, err)
	}
	if model.calls != 0 {
		t.Fatalf("model calls=%d want 0 before required context is filled", model.calls)
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
				ContextTurns: []assistant.AssistantConversationContextTurn{
					{Role: "user", Text: "目的地是杭州，明天出发"},
					{Role: "user", Text: "目的地是苏州，明天出发"},
				},
			},
			DomainID: "travel_planning",
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
		PreferenceID:         "memory-diet",
		Scope:                preferencemodel.ScopeLongTerm,
		Kind:                 preferencemodel.KindDietaryRestrictions,
		Value:                "对花生过敏，不吃含花生的食物",
		SourceType:           preferencemodel.SourceConversationConfirmed,
		SourceConversationID: "acv-memory-source",
		ConfirmedAt:          &confirmedAt,
		Version:              1,
	}}, nil
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-001
func TestConfirmedFactualMemoryEntersPrivateModelContext(t *testing.T) {
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		orchestration.WithPreferenceSnapshotReader(factualMemoryPreferenceReader{}),
		testFrozenPolicyOption(),
	)
	conversation, err := service.CreateConversation(
		t.Context(),
		"persona-memory",
		assistant.CreateConversationInput{ClientRequestID: "memory-context-conversation"},
	)
	if err != nil {
		t.Fatalf("CreateConversation(): %v", err)
	}
	turn, err := service.CreateTurn(
		t.Context(),
		"persona-memory",
		conversation.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "给我推荐晚餐"},
			ClientRequestID: "memory-context-turn",
			RequestContext:  testRunRequestContext("persona-memory"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn(): %v", err)
	}
	if len(turn.LongTermPreferenceFacts) != 1 {
		t.Fatalf("turn long-term memories=%#v", turn.LongTermPreferenceFacts)
	}
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	if _, failure, runErr := loop.RunTurn(t.Context(), turn); runErr != nil || failure != nil {
		t.Fatalf("RunTurn() failure=%+v err=%v", failure, runErr)
	}
	if len(model.longTermFacts) == 0 ||
		len(model.longTermFacts[0]) != 1 ||
		model.longTermFacts[0][0].Kind != preferencemodel.KindDietaryRestrictions {
		t.Fatalf("model long-term memories=%#v", model.longTermFacts)
	}
	if prompt := prompting.FormatFactualMemoriesForPrompt(model.longTermFacts[0]); !strings.Contains(
		prompt,
		"对花生过敏",
	) || !strings.Contains(prompt, "scope=long_term") {
		t.Fatalf("factual memory prompt=%q", prompt)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
func TestLongConversationUsesTraceableSummaryWithoutPerTurnTruncation(t *testing.T) {
	store := persistence.NewMemoryConversationRunStore()
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithConversationRunStore(store),
		orchestration.WithAgentLoop(loop),
		testFrozenPolicyOption(),
	)
	conversation, err := service.CreateConversation(
		t.Context(),
		"persona-summary",
		assistant.CreateConversationInput{ClientRequestID: "summary-conversation"},
	)
	if err != nil {
		t.Fatalf("CreateConversation(): %v", err)
	}
	baseTime := time.Date(2026, 7, 1, 8, 0, 0, 0, time.UTC)
	for index := 0; index < 10; index++ {
		text := "继续讨论旅行计划"
		if index == 0 {
			text = "原始目标：目的地是杭州，明天出发，预算5000元，安排一次家庭旅行"
		}
		if index == 7 {
			text = strings.Repeat("长", 320) + "保留尾部目标"
		}
		_, _, insertErr := store.InsertTurn(t.Context(), assistant.AssistantTurn{
			TurnID:         "turn-history-" + strconv.Itoa(index),
			ConversationID: conversation.ConversationID,
			UserID:         "persona-summary",
			Status:         "completed",
			SkillID:        "travel_planning",
			DomainID:       "travel_planning",
			Input:          assistant.AssistantTurnInput{Text: text},
			TerminalSnapshot: &assistant.AssistantRunTerminalSnapshot{
				AnswerText: "已记录该轮旅行讨论。",
			},
			ClientRequestID: "history-request-" + strconv.Itoa(index),
			CreatedAt:       baseTime.Add(time.Duration(index) * time.Minute),
		})
		if insertErr != nil {
			t.Fatalf("InsertTurn(%d): %v", index, insertErr)
		}
	}
	current, err := service.CreateTurn(
		t.Context(),
		"persona-summary",
		conversation.ConversationID,
		assistant.CreateTurnInput{
			SkillID:         "travel_planning",
			DomainID:        "travel_planning",
			Input:           assistant.AssistantTurnInput{Text: "继续上面的旅行计划"},
			ClientRequestID: "summary-current-turn",
			RequestContext:  testRunRequestContext("persona-summary"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn(): %v", err)
	}
	if _, err := service.ExecuteTurn(
		t.Context(),
		"persona-summary",
		current.TurnID,
	); err != nil {
		t.Fatalf("ExecuteTurn(): %v", err)
	}
	if len(model.contextSummaries) == 0 || model.contextSummaries[0] == nil {
		t.Fatal("model request did not receive rolling context summary")
	}
	summary := model.contextSummaries[0]
	if summary.FromTurnID != "turn-history-0" ||
		summary.ToTurnID != "turn-history-3" ||
		summary.TurnCount != 4 {
		t.Fatalf("summary trace=%#v", summary)
	}
	if !strings.Contains(summary.CurrentGoal, "原始目标") ||
		summary.ConfirmedSlots["destination"] != "杭州" ||
		summary.ConfirmedSlots["travel_date"] != "明天" {
		t.Fatalf("summary lost goal or slots: %#v", summary)
	}
	foundUntruncatedTail := false
	for _, contextTurn := range model.contextTurns[0] {
		if strings.Contains(contextTurn.Text, "保留尾部目标") &&
			len([]rune(contextTurn.Text)) > 320 {
			foundUntruncatedTail = true
		}
	}
	if !foundUntruncatedTail {
		t.Fatalf("recent context was truncated: %#v", model.contextTurns[0])
	}
	assembly := model.assemblies[0]
	if assembly == nil ||
		assembly.SlotState.Slots["destination"].Value != "杭州" {
		t.Fatalf("context assembly did not consume summary slots: %#v", assembly)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-002
func TestGroupMentionChannelExcludesPrivateLongTermMemory(t *testing.T) {
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		orchestration.WithPreferenceSnapshotReader(channelPreferenceReader{}),
		testFrozenPolicyOption(),
	)
	personalConversation, err := service.CreateConversation(
		t.Context(),
		"persona-channel",
		assistant.CreateConversationInput{ClientRequestID: "personal-channel-conversation"},
	)
	if err != nil {
		t.Fatalf("CreateConversation(personal): %v", err)
	}
	personal, err := service.CreateTurn(
		t.Context(),
		"persona-channel",
		personalConversation.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "你好"},
			ClientRequestID: "personal-channel-turn",
			RequestContext:  testRunRequestContext("persona-channel"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn(personal): %v", err)
	}
	if len(personal.LongTermPreferenceFacts) != 1 {
		t.Fatalf("personal long-term facts=%#v want private memory", personal.LongTermPreferenceFacts)
	}

	groupConversation, err := service.CreateConversation(
		t.Context(),
		"persona-channel",
		assistant.CreateConversationInput{ClientRequestID: "group-channel-conversation"},
	)
	if err != nil {
		t.Fatalf("CreateConversation(group): %v", err)
	}
	group, err := service.CreateTurn(
		t.Context(),
		"persona-channel",
		groupConversation.ConversationID,
		assistant.CreateTurnInput{
			TurnType: "proactive",
			Input:    assistant.AssistantTurnInput{Text: "群里有人问杭州天气"},
			Trigger: assistant.AssistantTurnTrigger{
				Type:      "chat_assistant_mentioned",
				MessageID: "message-channel",
			},
			ClientRequestID: "group-channel-turn",
			RequestContext:  testRunRequestContext("persona-channel"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn(group): %v", err)
	}
	if len(group.SessionPreferenceFacts) != 1 {
		t.Fatalf("group session facts=%#v want channel-local session preference", group.SessionPreferenceFacts)
	}
	if len(group.LongTermPreferenceFacts) != 0 {
		t.Fatalf("group long-term facts=%#v must exclude private memory", group.LongTermPreferenceFacts)
	}
	prompt := prompting.FormatModelPreferencesForPrompt(
		group.SessionPreferenceFacts,
		group.LongTermPreferenceFacts,
	)
	if strings.Contains(prompt, "使用简体中文回答") {
		t.Fatalf("group prompt leaked private long-term memory: %q", prompt)
	}
	model := &contextAssemblyRecordingModel{}
	loop := contextAssemblyLoop(t, model)
	if _, failure, runErr := loop.RunTurn(t.Context(), group); runErr != nil || failure != nil {
		t.Fatalf("RunTurn(group) failure=%+v err=%v", failure, runErr)
	}
	for _, facts := range model.longTermFacts {
		if len(facts) != 0 {
			t.Fatalf("group model request leaked long-term facts: %#v", facts)
		}
	}
	for _, assembly := range model.assemblies {
		if assembly == nil {
			continue
		}
		for _, hint := range assembly.RecallHints {
			if hint.Source == "longterm_memory" {
				t.Fatalf("group recall leaked private memory: %#v", hint)
			}
		}
	}
}
