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
	app "quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
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
	}
	loop := app.NewAgentLoop(
		replaySkillRuntime{toolSteps: replay.FakeToolScript},
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
	return app.ModelResponse{Text: "scripted model fallback", FinishReason: "stop"}, nil
}

type replaySkillRuntime struct {
	toolSteps []assistant.ReplayToolStep
}

func (r replaySkillRuntime) SelectSkill(_ context.Context, turn assistant.AssistantTurn) (app.SkillSelection, error) {
	toolPolicy := []string{}
	for _, step := range r.toolSteps {
		if strings.TrimSpace(step.ToolName) != "" {
			toolPolicy = append(toolPolicy, strings.TrimSpace(step.ToolName))
		}
	}
	return app.SkillSelection{
		SkillID:      turn.SkillID,
		DomainID:     turn.DomainID,
		DisplayName:  "Replay skill",
		ToolPolicy:   toolPolicy,
		PromptPolicy: "m6.replay",
	}, nil
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
		if req.ToolName == "app_action" {
			requested.Placement = "device_action"
			requested.RequiresConfirmation = true
			completed = requested
			completed.Status = "waiting_confirmation"
			completed.Result = map[string]any{
				"proposal": map[string]any{
					"toolName":             req.ToolName,
					"placement":            "device_action",
					"input":                input,
					"requiresConfirmation": true,
				},
			}
		}
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
