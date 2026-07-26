package simulator

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	app "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type Runner struct {
	Now func() time.Time
}

type Transcript struct {
	CaseID  string               `json:"caseId"`
	Events  []streaming.Envelope `json:"events"`
	Failure *rtfailures.Failure  `json:"runtimeFailure,omitempty"`
}

func LoadCase(path string) (assistant.ReplayCase, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return assistant.ReplayCase{}, err
	}
	var replay assistant.ReplayCase
	if err := json.Unmarshal(raw, &replay); err != nil {
		return assistant.ReplayCase{}, err
	}
	return replay, nil
}

func (r Runner) Run(ctx context.Context, replay assistant.ReplayCase) (Transcript, error) {
	now := r.now()
	turn := assistant.AssistantTurn{
		TurnID:         replay.Request.TurnID,
		ConversationID: replay.Request.ConversationID,
		UserID:         replay.Request.UserID,
		TurnType:       "replay",
		Status:         "running",
		SkillID:        "general_qa",
		DomainID:       "assistant",
		Input:          assistant.AssistantTurnInput{Text: replay.Request.InputText},
		Trigger:        assistant.AssistantTurnTrigger{Type: "replay"},
		TraceID:        "trace_" + replay.ReplayCaseID,
		CreatedAt:      now,
		FrozenPolicySelection: assistant.AssistantFrozenPolicySelection{
			PolicyID:        "assistant-replay",
			ReleaseVersion:  "replay-v1",
			Cohort:          "replay",
			RolloutRevision: 1,
			RuleID:          "replay",
			Template: assistant.AssistantFrozenPolicyTemplate{
				TemplateID:      "replay",
				SkillID:         "general_qa",
				DomainID:        "assistant",
				PromptPolicy:    "m6.replay",
				AllowedTools:    replayToolPolicy(replay.FakeToolScript),
				SearchIntensity: "balanced",
			},
		},
	}
	loop := app.NewAgentLoop(
		nil,
		app.ReactRuntime{
			Model: scriptedModelProvider{steps: replay.FakeModelScript},
			Tools: scriptedToolExecutor{
				now:   r.now,
				steps: replay.FakeToolScript,
			},
		},
		r.now,
	)
	events, failure, err := loop.RunTurn(ctx, turn)
	if err != nil {
		return Transcript{}, err
	}
	return Transcript{CaseID: replay.ReplayCaseID, Events: events, Failure: failure}, nil
}

func (r Runner) now() time.Time {
	if r.Now != nil {
		return r.Now().UTC()
	}
	return time.Now().UTC()
}

type scriptedModelProvider struct {
	steps []assistant.ReplayModelStep
}

func (p scriptedModelProvider) Complete(_ context.Context, req app.ModelRequest) (app.ModelResponse, error) {
	for _, step := range p.steps {
		if step.Stage == req.Stage {
			return app.ModelResponse{
				Text:            step.Text,
				StructuredDelta: step.StructuredDelta,
				Usage:           step.Usage,
				FinishReason:    step.FinishReason,
			}, nil
		}
	}
	if req.Stage == "reasoning" {
		for _, step := range p.steps {
			if step.Stage == "final" {
				return app.ModelResponse{
					Text:         step.Text,
					Usage:        step.Usage,
					FinishReason: "stop",
				}, nil
			}
		}
	}
	return app.ModelResponse{}, fmt.Errorf("replay script has no response for stage %q", req.Stage)
}

func replayToolPolicy(steps []assistant.ReplayToolStep) []string {
	toolPolicy := []string{}
	for _, step := range steps {
		if strings.TrimSpace(step.ToolName) != "" {
			toolPolicy = append(toolPolicy, strings.TrimSpace(step.ToolName))
		}
	}
	return toolPolicy
}

type scriptedToolExecutor struct {
	now   func() time.Time
	steps []assistant.ReplayToolStep
}

func (e scriptedToolExecutor) Execute(_ context.Context, req app.ToolRequest) (app.ToolExecution, error) {
	now := time.Now().UTC()
	if e.now != nil {
		now = e.now().UTC()
	}
	input := req.Input
	if input == nil {
		input = map[string]any{
			"query": req.Turn.Input.Text,
		}
	}
	requested := assistant.ToolUse{
		ToolUseID: "tu_" + strings.ReplaceAll(req.Turn.TurnID, "atn_", ""),
		TurnID:    req.Turn.TurnID,
		ToolName:  req.ToolName,
		Placement: "cloud",
		Input:     input,
		Status:    "requested",
		CreatedAt: now,
	}
	for _, step := range e.steps {
		if step.ToolName != req.ToolName {
			continue
		}
		completed := requested
		completedAt := now.Add(time.Millisecond)
		completed.CompletedAt = &completedAt
		if len(step.Failure) > 0 {
			failure := rtfailures.Failure{
				Code:   stringValue(step.Failure, "code", "ASSISTANT.MIDDLEWARE.tool_failed"),
				Origin: rtfailures.OriginRemoteDependency,
				Kind:   rtfailures.KindUnavailable,
				Nature: rtfailures.NatureTransient,
				Location: rtfailures.Location{
					BusinessObject: "tool_use",
					FunctionModule: "assistant_simulator",
				},
			}.Normalized()
			completed.Status = "failed"
			completed.Failure = &failure
			return app.ToolExecution{Requested: requested, Completed: completed, Failure: &failure}, nil
		}
		completed.Status = "completed"
		completed.Result = step.Result
		return app.ToolExecution{Requested: requested, Completed: completed}, nil
	}
	return app.ToolExecution{}, fmt.Errorf("scripted tool %q not found", req.ToolName)
}

func stringValue(values map[string]any, key string, fallback string) string {
	if value, ok := values[key].(string); ok && strings.TrimSpace(value) != "" {
		return value
	}
	return fallback
}
