package projection

import (
	"time"

	"quwoquan_service/services/assistant-service/internal/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type RunResponseProjector struct {
	Now func() time.Time
}

func (p RunResponseProjector) Project(state orchestration.RunState, finalText string, failure error) assistant.AssistantRunResponse {
	status := "completed"
	if failure != nil {
		status = "failed"
	}
	return assistant.AssistantRunResponse{
		ConversationID: state.Turn.ConversationID,
		TurnID:         state.Turn.TurnID,
		Status:         status,
		FinalText:      finalText,
		Summary:        state.Journey.Summary,
		Journey:        state.Journey,
		RunArtifacts: assistant.RunArtifacts{
			DisplayMarkdown:  finalText,
			DisplayPlainText: finalText,
			Journey:          state.Journey,
			ProcessTimeline:  state.ProcessTimeline,
			Diagnostics: map[string]any{
				"phaseCount": len(state.Phases),
			},
		},
		Observability: state.Observability,
		CompletedAt:   p.now(),
	}
}

func (p RunResponseProjector) now() time.Time {
	if p.Now != nil {
		return p.Now().UTC()
	}
	return time.Now().UTC()
}
