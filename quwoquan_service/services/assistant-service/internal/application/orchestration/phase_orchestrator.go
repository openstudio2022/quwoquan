package orchestration

import (
	"context"
	"fmt"
	"time"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type PhaseOrchestrator struct {
	Now func() time.Time
}

func NewPhaseOrchestrator(now func() time.Time) PhaseOrchestrator {
	return PhaseOrchestrator{Now: now}
}

func (o PhaseOrchestrator) Phases() []string {
	return append([]string{}, DefaultPhaseOrder...)
}

func (o PhaseOrchestrator) Run(ctx context.Context, turn assistant.AssistantTurn) (RunState, error) {
	now := o.now()
	state := RunState{
		Turn: turn,
		Journey: assistant.AssistantJourney{
			Stages:  make([]assistant.AssistantJourneyStage, 0, len(DefaultPhaseOrder)),
			Entries: []assistant.AssistantJourneyEntry{},
			Summary: "cloud assistant phase journey",
		},
		ProcessTimeline: []assistant.ProcessTimelineFrame{},
		Observability: assistant.AssistantRunObservabilityPayload{
			TraceID:          turn.TraceID,
			ModelProvider:    "fake",
			SkillID:          turn.SkillID,
			DomainID:         turn.DomainID,
			PhaseDurationsMs: map[string]int{},
			QualitySignals: map[string]any{
				"phaseOrchestrator": "m5_equivalent",
			},
		},
	}
	for index, phaseID := range DefaultPhaseOrder {
		if err := ctx.Err(); err != nil {
			return RunState{}, err
		}
		startedAt := now.Add(time.Duration(index*10) * time.Millisecond)
		endedAt := startedAt.Add(5 * time.Millisecond)
		phase := PhaseState{
			PhaseID:   phaseID,
			Status:    "completed",
			Summary:   fmt.Sprintf("%s completed", phaseID),
			StartedAt: startedAt,
			EndedAt:   endedAt,
			Payload: map[string]any{
				"order": index + 1,
			},
		}
		state.Phases = append(state.Phases, phase)
		state.TraceEvents = append(state.TraceEvents, assistant.AssistantTraceEvent{
			TraceEventID:   fmt.Sprintf("%s:%s:%03d", turn.TurnID, phaseID, index+1),
			ConversationID: turn.ConversationID,
			TurnID:         turn.TurnID,
			TraceID:        turn.TraceID,
			PhaseID:        phaseID,
			EventType:      "phase_completed",
			Seq:            uint64(index + 1),
			Status:         "completed",
			Summary:        phase.Summary,
			Payload:        phase.Payload,
			CreatedAt:      endedAt,
		})
		state.Journey.Stages = append(state.Journey.Stages, assistant.AssistantJourneyStage{
			StageID: phaseID,
			Status:  "completed",
			Order:   index + 1,
			Summary: phase.Summary,
		})
		state.ProcessTimeline = append(state.ProcessTimeline, assistant.ProcessTimelineFrame{
			FrameID:  fmt.Sprintf("%s:%s", turn.TurnID, phaseID),
			StepID:   phaseID,
			Status:   "completed",
			Order:    index + 1,
			Headline: phase.Summary,
			Detail:   "cloud phase completed with typed state",
			Payload:  phase.Payload,
		})
		state.Observability.PhaseDurationsMs[phaseID] = int(endedAt.Sub(startedAt).Milliseconds())
	}
	return state, nil
}

func (o PhaseOrchestrator) now() time.Time {
	if o.Now != nil {
		return o.Now().UTC()
	}
	return time.Now().UTC()
}
