package orchestration

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

type canonicalRunInput struct {
	ClientRequestID string
	Text            string
	SkillID         string
	DomainID        string
	PersonaID       string
	SurfaceKind     string
	SurfaceID       string
	ContextSnapshot map[string]any
	Trigger         assistant.AssistantTurnTrigger
}

func (s *AssistantService) startCanonicalRunAndWait(
	ctx context.Context,
	userID string,
	sessionID string,
	input canonicalRunInput,
) (runruntime.Run, error) {
	if s == nil || s.runCommands == nil {
		return runruntime.Run{}, errors.New(
			"canonical AssistantRun command service is not configured",
		)
	}
	trigger, err := canonicalTriggerMap(input.Trigger)
	if err != nil {
		return runruntime.Run{}, err
	}
	personaID := strings.TrimSpace(input.PersonaID)
	if personaID == "" {
		personaID = strings.TrimSpace(userID)
	}
	run, err := s.runCommands.Start(ctx, runruntime.StartCommand{
		UserID:          strings.TrimSpace(userID),
		PersonaID:       personaID,
		SessionID:       strings.TrimSpace(sessionID),
		ClientRequestID: strings.TrimSpace(input.ClientRequestID),
		TraceID:         strings.TrimSpace(input.ClientRequestID),
		RequestContext: runruntime.RequestContext{
			SurfaceKind: strings.TrimSpace(input.SurfaceKind),
			SurfaceID:   strings.TrimSpace(input.SurfaceID),
			PersonaID:   personaID,
		},
		IntentKind:        "answer",
		InputText:         strings.TrimSpace(input.Text),
		RequestedSkillID:  strings.TrimSpace(input.SkillID),
		RequestedDomainID: strings.TrimSpace(input.DomainID),
		Trigger:           trigger,
		ContextSnapshot:   cloneObject(input.ContextSnapshot),
		ReasoningProfile:  generated.AssistantReasoningProfileBalanced,
	})
	if err != nil {
		return runruntime.Run{}, err
	}
	ticker := time.NewTicker(200 * time.Millisecond)
	defer ticker.Stop()
	for {
		if terminalCanonicalRun(run.State) {
			return run, nil
		}
		select {
		case <-ctx.Done():
			return runruntime.Run{}, ctx.Err()
		case <-ticker.C:
			run, err = s.runCommands.Get(ctx, userID, run.RunID)
			if err != nil {
				return runruntime.Run{}, err
			}
		}
	}
}

func canonicalTriggerMap(
	trigger assistant.AssistantTurnTrigger,
) (map[string]any, error) {
	result := map[string]any{"type": strings.TrimSpace(trigger.Type)}
	if messageID := strings.TrimSpace(trigger.MessageID); messageID != "" {
		// MessageID is intentionally excluded from the public AssistantTurn JSON
		// body. This internal projection freezes the trusted event coordinate on
		// AssistantRun without making it client-writable.
		result["messageId"] = messageID
	}
	if trigger.Envelope != nil {
		encoded, err := json.Marshal(trigger.Envelope)
		if err != nil {
			return nil, err
		}
		var envelope map[string]any
		if err := json.Unmarshal(encoded, &envelope); err != nil {
			return nil, err
		}
		result["envelope"] = envelope
	}
	return result, nil
}

func terminalCanonicalRun(state generated.AssistantRunState) bool {
	return state == generated.AssistantRunStateCompleted ||
		state == generated.AssistantRunStateFailed ||
		state == generated.AssistantRunStateCancelled ||
		state == generated.AssistantRunStateWaitingUser ||
		state == generated.AssistantRunStateWaitingApproval ||
		state == generated.AssistantRunStateWaitingExternal
}

func projectCanonicalRunAsTurnView(
	run runruntime.Run,
) assistant.AssistantTurn {
	projected := assistant.AssistantTurn{
		TurnID:          run.RunID,
		SessionID:       run.SessionID,
		UserID:          run.UserID,
		Status:          run.State.WireName(),
		SkillID:         run.RequestedSkillID,
		DomainID:        run.RequestedDomainID,
		Input:           assistant.AssistantTurnInput{Text: run.InputText},
		ClientRequestID: run.ClientRequestID,
		TraceID:         run.TraceID,
		CreatedAt:       run.CreatedAt,
		CompletedAt:     run.CompletedAt,
	}
	if len(run.TerminalSnapshot) > 0 {
		encoded, err := json.Marshal(run.TerminalSnapshot)
		if err == nil {
			var snapshot assistant.AssistantRunTerminalSnapshot
			if json.Unmarshal(encoded, &snapshot) == nil {
				projected.TerminalSnapshot = &snapshot
			}
		}
	}
	return projected
}
