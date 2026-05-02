package orchestration

import (
	"time"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

const (
	PhaseBootstrap       = "bootstrap"
	PhaseUnderstand      = "understand"
	PhaseRetrievalDesign = "retrieval-design"
	PhaseExecution       = "execution"
	PhaseEvidenceDigest  = "evidence-digest"
	PhaseSynthesis       = "synthesis"
	PhaseFinalize        = "finalize"
)

var DefaultPhaseOrder = []string{
	PhaseBootstrap,
	PhaseUnderstand,
	PhaseRetrievalDesign,
	PhaseExecution,
	PhaseEvidenceDigest,
	PhaseSynthesis,
	PhaseFinalize,
}

type PhaseState struct {
	PhaseID   string         `json:"phaseId"`
	Status    string         `json:"status"`
	Summary   string         `json:"summary,omitempty"`
	StartedAt time.Time      `json:"startedAt"`
	EndedAt   time.Time      `json:"endedAt"`
	Payload   map[string]any `json:"payload,omitempty"`
}

type RunState struct {
	Turn            assistant.AssistantTurn
	Phases          []PhaseState
	TraceEvents     []assistant.AssistantTraceEvent
	Journey         assistant.AssistantJourney
	ProcessTimeline []assistant.ProcessTimelineFrame
	Observability   assistant.AssistantRunObservabilityPayload
}
