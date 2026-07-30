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
	app "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

type Runner struct {
	Now          func() time.Time
	PromptAssets ports.PromptAssetResolver
}

type Transcript struct {
	CaseID               string               `json:"caseId"`
	SelectedSkillID      string               `json:"selectedSkillId,omitempty"`
	SelectedDomainID     string               `json:"selectedDomainId,omitempty"`
	ToolCalls            []ReplayToolCall     `json:"toolCalls"`
	ClarificationSlotIDs []string             `json:"clarificationSlotIds"`
	ReferenceURLs        []string             `json:"referenceUrls"`
	FinalAnswerMode      string               `json:"finalAnswerMode,omitempty"`
	Events               []streaming.Envelope `json:"events"`
	Failure              *rtfailures.Failure  `json:"runtimeFailure,omitempty"`
}

type ReplayToolCall struct {
	ToolName string         `json:"toolName"`
	Input    map[string]any `json:"input,omitempty"`
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
	skillID, domainID := replaySkillIdentity(replay)
	turn := assistant.AssistantTurn{
		TurnID:         replay.Request.TurnID,
		ConversationID: replay.Request.ConversationID,
		UserID:         replay.Request.UserID,
		TurnType:       "replay",
		Status:         "running",
		SkillID:        skillID,
		DomainID:       domainID,
		Input:          assistant.AssistantTurnInput{Text: replay.Request.InputText},
		Trigger:        assistant.AssistantTurnTrigger{Type: "replay"},
		TraceID:        "trace_" + replay.ReplayCaseID,
		RequestContext: assistant.AssistantRunRequestContext{
			SurfaceID: stringValue(replay.Request.ClientContext, "surfaceId", "assistant.personal"),
			PersonaID: replay.Request.UserID,
		},
		CreatedAt: now,
		FrozenPolicySelection: assistant.AssistantFrozenPolicySelection{
			PolicyID:        "assistant-replay",
			ReleaseDigest:   "ac203c9843b5bd8c883e07039ff82820c94422010be6108bb82403ca25376a22",
			Cohort:          "replay",
			RolloutRevision: 1,
			RuleID:          "replay",
			Template: assistant.AssistantFrozenPolicyTemplate{
				TemplateID:      "replay",
				SkillID:         skillID,
				DomainID:        domainID,
				PromptPolicy:    "replay",
				AllowedTools:    replayToolPolicy(replay.FakeToolScript),
				SearchIntensity: "medium",
			},
		},
	}
	toolExecutor := &scriptedToolExecutor{
		now:   r.now,
		steps: replay.FakeToolScript,
	}
	loop := app.NewAgentLoop(
		nil,
		app.ReactRuntime{
			Model: scriptedModelProvider{steps: replay.FakeModelScript},
			Tools: toolExecutor,
		},
		r.now,
	)
	loop.PromptAssets = r.PromptAssets
	events, failure, err := loop.RunTurn(ctx, turn)
	if err != nil {
		return Transcript{}, err
	}
	transcript := projectTranscript(replay.ReplayCaseID, events, toolExecutor.calls)
	transcript.Failure = failure
	return transcript, nil
}

func replaySkillIdentity(replay assistant.ReplayCase) (string, string) {
	skillID := strings.TrimSpace(replay.Expectations.SelectedSkillID)
	if skillID == "" {
		skillID = strings.TrimSpace(replay.ExpectedRunResponse.Observability.SkillID)
	}
	if skillID == "" {
		skillID = "general_qa"
	}
	domainID := strings.TrimSpace(replay.Expectations.SelectedDomainID)
	if domainID == "" {
		domainID = strings.TrimSpace(replay.ExpectedRunResponse.Observability.DomainID)
	}
	if domainID == "" {
		domainID = "assistant"
	}
	return skillID, domainID
}

func projectTranscript(
	caseID string,
	events []streaming.Envelope,
	toolCalls []ReplayToolCall,
) Transcript {
	transcript := Transcript{
		CaseID:               caseID,
		ToolCalls:            append([]ReplayToolCall(nil), toolCalls...),
		ClarificationSlotIDs: []string{},
		ReferenceURLs:        []string{},
		Events:               events,
	}
	referenceURLs := map[string]bool{}
	for _, event := range events {
		if process, ok := event.Payload["process"].(assistant.AssistantRunVisibleProcess); ok {
			if process.Stage == "classifying" && process.Status == "completed" {
				transcript.SelectedSkillID = strings.TrimSpace(process.SkillID)
				transcript.SelectedDomainID = strings.TrimSpace(process.DomainID)
			}
			for _, reference := range process.AcceptedReferences {
				url := strings.TrimSpace(reference.Destination.URL)
				if url != "" && !referenceURLs[url] {
					referenceURLs[url] = true
					transcript.ReferenceURLs = append(transcript.ReferenceURLs, url)
				}
			}
		}
		if event.EventType != string(assistantstreaming.AssistantStreamEventCompleted) {
			continue
		}
		transcript.FinalAnswerMode = strings.TrimSpace(
			stringValue(event.Payload, "finalAnswerMode", ""),
		)
		if askUser, ok := event.Payload["askUser"].(map[string]any); ok {
			slotID := strings.TrimSpace(stringValue(askUser, "slotId", ""))
			if slotID != "" {
				transcript.ClarificationSlotIDs = append(
					transcript.ClarificationSlotIDs,
					slotID,
				)
			}
		}
	}
	return transcript
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
	calls []ReplayToolCall
}

func (e *scriptedToolExecutor) Execute(_ context.Context, req app.ToolRequest) (app.ToolExecution, error) {
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
	e.calls = append(e.calls, ReplayToolCall{
		ToolName: strings.TrimSpace(req.ToolName),
		Input:    copyMap(input),
	})
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

func copyMap(source map[string]any) map[string]any {
	if source == nil {
		return nil
	}
	copied := make(map[string]any, len(source))
	for key, value := range source {
		copied[key] = value
	}
	return copied
}
