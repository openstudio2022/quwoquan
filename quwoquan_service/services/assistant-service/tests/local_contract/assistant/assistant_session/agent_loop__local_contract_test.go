package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type assistantSessionAgentLoopFinalModel struct{}

type assistantSessionAgentLoopCountingModel struct{ calls int }

type assistantSessionAgentLoopSkillRuntime struct{}

func (assistantSessionAgentLoopSkillRuntime) SelectSkill(
	_ context.Context,
	_ assistant.AssistantTurn,
) (orchestration.SkillSelection, error) {
	return orchestration.SkillSelection{
		SkillID:     "general_qa",
		DomainID:    "assistant",
		DisplayName: "通用问答",
	}, nil
}

func (assistantSessionAgentLoopFinalModel) Complete(_ context.Context, request orchestration.ModelRequest) (orchestration.ModelResponse, error) {
	_ = request
	return orchestration.ModelResponse{
		Text:            "已通过真实 application port 完成回答。",
		StructuredDelta: map[string]any{"nextAction": "answer"},
	}, nil
}

func (model *assistantSessionAgentLoopCountingModel) Complete(
	context.Context,
	orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	model.calls++
	return orchestration.ModelResponse{
		Text:            "must not run",
		StructuredDelta: map[string]any{"nextAction": "answer"},
	}, nil
}

func TestAgentLoopRunTurnPublishesACompletedAnswer(t *testing.T) {
	loop := orchestration.NewAgentLoop(
		assistantSessionAgentLoopSkillRuntime{},
		orchestration.ReactRuntime{Model: assistantSessionAgentLoopFinalModel{}},
		func() time.Time { return time.Date(2026, 7, 22, 0, 0, 0, 0, time.UTC) },
	)
	loop.Catalog = skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{{
		SkillID:      "general_qa",
		DisplayName:  "通用问答",
		DomainID:     "assistant",
		ProblemClass: "general",
	}}}

	events, failure, err := loop.RunTurn(t.Context(), assistant.AssistantTurn{
		TurnID:    "turn-local-contract-1",
		SessionID: "session-local-contract-1",
		UserID:    "user-local-contract-1",
		Input:     assistant.AssistantTurnInput{Text: "请给我一个建议"},
		TraceID:   "trace-local-contract-1",
		FrozenPolicySelection: testFrozenPolicySelection(
			"assistant-default",
			"general_qa",
			"assistant",
		),
	})
	if err != nil || failure != nil {
		t.Fatalf("RunTurn() err=%v failure=%+v", err, failure)
	}
	if len(events) == 0 || events[len(events)-1].EventType != string(assistantstreaming.AssistantStreamEventCompleted) {
		t.Fatalf("expected completed stream event, got %#v", events)
	}
}

func TestAgentLoopRechecksZeroToolSkillAccessAtPlanningBoundary(t *testing.T) {
	model := &assistantSessionAgentLoopCountingModel{}
	loop := orchestration.NewAgentLoop(
		assistantSessionAgentLoopSkillRuntime{},
		orchestration.ReactRuntime{Model: model},
		nil,
	)
	loop.Catalog = skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{{
		SkillID: "general_qa", DisplayName: "通用问答", DomainID: "assistant",
		ProblemClass: "general",
	}}}
	revoked := errors.New("shared Skill placement revoked")
	accessChecks := 0
	loop.SkillAccess = orchestration.SkillExecutionAccessPolicyFunc(func(
		context.Context,
		assistant.AssistantTurn,
		string,
	) error {
		accessChecks++
		if accessChecks == 1 {
			return nil
		}
		return revoked
	})
	_, failure, err := loop.RunTurn(t.Context(), assistant.AssistantTurn{
		TurnID: "turn-zero-tool-revoked", SessionID: "session-zero-tool-revoked",
		UserID: "user-zero-tool-revoked", Input: assistant.AssistantTurnInput{Text: "继续"},
		TraceID: "trace-zero-tool-revoked",
		FrozenPolicySelection: testFrozenPolicySelection(
			"assistant-default",
			"general_qa",
			"assistant",
		),
	})
	if err != nil || failure == nil || model.calls != 0 || accessChecks != 2 {
		t.Fatalf(
			"err=%v failure=%+v modelCalls=%d accessChecks=%d",
			err,
			failure,
			model.calls,
			accessChecks,
		)
	}
}
