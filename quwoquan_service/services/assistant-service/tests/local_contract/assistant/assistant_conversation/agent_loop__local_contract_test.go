package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type migratedAgentLoopFinalModel struct{}

type migratedAgentLoopSkillRuntime struct{}

func (migratedAgentLoopSkillRuntime) SelectSkill(
	_ context.Context,
	_ assistant.AssistantTurn,
) (application.SkillSelection, error) {
	return application.SkillSelection{
		SkillID:     "general_qa",
		DomainID:    "assistant",
		DisplayName: "通用问答",
	}, nil
}

func (migratedAgentLoopFinalModel) Complete(_ context.Context, request application.ModelRequest) (application.ModelResponse, error) {
	_ = request
	return application.ModelResponse{
		Text:            "已通过真实 application port 完成回答。",
		StructuredDelta: map[string]any{"nextAction": "answer"},
	}, nil
}

func TestAgentLoopRunTurnPublishesACompletedAnswer(t *testing.T) {
	loop := application.NewAgentLoop(
		migratedAgentLoopSkillRuntime{},
		application.ReactRuntime{Model: migratedAgentLoopFinalModel{}},
		func() time.Time { return time.Date(2026, 7, 22, 0, 0, 0, 0, time.UTC) },
	)

	events, failure, err := loop.RunTurn(t.Context(), assistant.AssistantTurn{
		TurnID:         "turn-local-contract-1",
		ConversationID: "conversation-local-contract-1",
		UserID:         "user-local-contract-1",
		Input:          assistant.AssistantTurnInput{Text: "请给我一个建议"},
		TraceID:        "trace-local-contract-1",
		FrozenPolicySelection: testFrozenPolicySelection(
			"assistant-default",
			"general_qa",
			"assistant",
		),
	})
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() err=%v failure=%+v", err, failure)
	}
	if len(events) == 0 || events[len(events)-1].EventType != string(application.AssistantStreamEventCompleted) {
		t.Fatalf("expected completed stream event, got %#v", events)
	}
}
