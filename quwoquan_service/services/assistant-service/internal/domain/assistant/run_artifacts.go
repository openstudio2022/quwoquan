package assistant

import (
	"time"

	rtfailures "quwoquan_service/runtime/failures"
)

type AssistantTraceEvent struct {
	TraceEventID   string              `json:"traceEventId"`
	ConversationID string              `json:"conversationId"`
	TurnID         string              `json:"turnId"`
	TraceID        string              `json:"traceId,omitempty"`
	PhaseID        string              `json:"phaseId,omitempty"`
	EventType      string              `json:"eventType"`
	Seq            uint64              `json:"seq"`
	Status         string              `json:"status,omitempty"`
	Summary        string              `json:"summary,omitempty"`
	Payload        map[string]any      `json:"payload,omitempty"`
	Failure        *rtfailures.Failure `json:"runtimeFailure,omitempty"`
	CreatedAt      time.Time           `json:"createdAt"`
}

type AssistantJourneyStage struct {
	StageID string `json:"stageId"`
	Status  string `json:"status"`
	Order   int    `json:"order"`
	Summary string `json:"summary,omitempty"`
}

type AssistantJourneyEntry struct {
	EntryID  string         `json:"entryId"`
	StageID  string         `json:"stageId"`
	Kind     string         `json:"kind"`
	Status   string         `json:"status"`
	Order    int            `json:"order"`
	Headline string         `json:"headline,omitempty"`
	Detail   string         `json:"detail,omitempty"`
	Payload  map[string]any `json:"payload,omitempty"`
}

type AssistantJourney struct {
	Stages  []AssistantJourneyStage `json:"stages"`
	Entries []AssistantJourneyEntry `json:"entries"`
	Summary string                  `json:"summary,omitempty"`
}

type ProcessTimelineFrame struct {
	FrameID  string         `json:"frameId"`
	StepID   string         `json:"stepId"`
	Status   string         `json:"status"`
	Order    int            `json:"order"`
	Headline string         `json:"headline,omitempty"`
	Detail   string         `json:"detail,omitempty"`
	Payload  map[string]any `json:"payload,omitempty"`
}

type RunArtifacts struct {
	DisplayMarkdown  string                 `json:"displayMarkdown,omitempty"`
	DisplayPlainText string                 `json:"displayPlainText,omitempty"`
	Journey          AssistantJourney       `json:"journey"`
	ProcessTimeline  []ProcessTimelineFrame `json:"processTimeline"`
	Diagnostics      map[string]any         `json:"diagnostics,omitempty"`
}

type AssistantRunObservabilityPayload struct {
	TraceID          string         `json:"traceId,omitempty"`
	ModelProvider    string         `json:"modelProvider,omitempty"`
	SkillID          string         `json:"skillId,omitempty"`
	DomainID         string         `json:"domainId,omitempty"`
	PhaseDurationsMs map[string]int `json:"phaseDurationsMs,omitempty"`
	TokenUsage       map[string]any `json:"tokenUsage,omitempty"`
	QualitySignals   map[string]any `json:"qualitySignals,omitempty"`
}

type AssistantRunResponse struct {
	ConversationID string                           `json:"conversationId"`
	TurnID         string                           `json:"turnId"`
	Status         string                           `json:"status"`
	FinalText      string                           `json:"finalText,omitempty"`
	Summary        string                           `json:"summary,omitempty"`
	Journey        AssistantJourney                 `json:"journey"`
	RunArtifacts   RunArtifacts                     `json:"runArtifacts"`
	Observability  AssistantRunObservabilityPayload `json:"observability"`
	Failure        *rtfailures.Failure              `json:"runtimeFailure,omitempty"`
	CompletedAt    time.Time                        `json:"completedAt"`
}

type ReplayCase struct {
	ReplayCaseID         string                `json:"replayCaseId"`
	Title                string                `json:"title,omitempty"`
	Request              ReplayRequest         `json:"request"`
	FakeModelScript      []ReplayModelStep     `json:"fakeModelScript"`
	FakeToolScript       []ReplayToolStep      `json:"fakeToolScript"`
	FakeDeviceContext    map[string]any        `json:"fakeDeviceContext,omitempty"`
	ExpectedStreamEvents []map[string]any      `json:"expectedStreamEvents"`
	ExpectedTraceEvents  []AssistantTraceEvent `json:"expectedTraceEvents"`
	ExpectedRunResponse  AssistantRunResponse  `json:"expectedRunResponse"`
}

type ReplayRequest struct {
	ConversationID string         `json:"conversationId"`
	TurnID         string         `json:"turnId"`
	UserID         string         `json:"userId,omitempty"`
	InputText      string         `json:"inputText,omitempty"`
	ClientContext  map[string]any `json:"clientContext,omitempty"`
}

type ReplayModelStep struct {
	Stage           string         `json:"stage"`
	Text            string         `json:"text,omitempty"`
	StructuredDelta map[string]any `json:"structuredDelta,omitempty"`
	Usage           map[string]any `json:"usage,omitempty"`
	FinishReason    string         `json:"finishReason,omitempty"`
}

type ReplayToolStep struct {
	ToolName string         `json:"toolName"`
	Input    map[string]any `json:"input,omitempty"`
	Result   map[string]any `json:"result,omitempty"`
	Failure  map[string]any `json:"failure,omitempty"`
}
