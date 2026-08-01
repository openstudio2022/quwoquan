package orchestration

import (
	"context"
	"log/slog"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/streaming"
	"strings"

	"quwoquan_service/runtime/streaming"
	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/channel"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

// recordRunScorecard 在 run 终态时写入唯一 AssistantLearningFact。
// eventId 派生自 turnId，durable receipt 保证重复完成幂等；
// 落盘失败只结构化告警，不阻塞用户回答。
func (s *AssistantService) recordRunScorecard(ctx context.Context, turn assistant.AssistantTurn) {
	if s.learningFacts == nil {
		return
	}
	scoreValue := 1.0
	if turn.Status == "failed" {
		scoreValue = 0.0
	}
	score := ports.ServiceScorecardFactCommand{
		EventID:         "turn:" + turn.TurnID + ":completion",
		AssistantTurnID: turn.TurnID,
		DomainID:        turn.DomainID,
		MetricID:        "turn_completion",
		MetricValue:     scoreValue,
		MetricSource:    "service_auto",
		OccurredAt:      s.now(),
	}
	if err := s.learningFacts.AppendServiceScorecard(ctx, score); err != nil {
		slog.WarnContext(ctx, "assistant run scorecard record failed",
			slog.String("turnId", turn.TurnID), slog.String("error", err.Error()))
	}
}

// replayCompletedTurnStream 为已终态 turn 提供确定性的重放事件；
// 服务重启后 SSE 重连不再 404，而是收到终态摘要并立即完成。
func (s *AssistantService) replayCompletedTurnStream(
	turn assistant.AssistantTurn,
	emit func(streaming.Envelope) error,
) ([]streaming.Envelope, error) {
	payload := map[string]any{
		"sessionId":   turn.SessionID,
		"turnId":      turn.TurnID,
		"status":      turn.Status,
		"resumeToken": turn.StreamState.ResumeToken,
	}
	if turn.TerminalSnapshot != nil {
		payload["processes"] = turn.TerminalSnapshot.Processes
	}
	eventType := assistantstreaming.AssistantStreamEventCompleted
	switch turn.Status {
	case "failed":
		eventType = assistantstreaming.AssistantStreamEventFailed
	case "cancelled":
		eventType = assistantstreaming.AssistantStreamEventCancelled
	default:
		if turn.TerminalSnapshot != nil &&
			strings.TrimSpace(turn.TerminalSnapshot.AnswerText) != "" {
			payload["finalAnswer"] = turn.TerminalSnapshot.AnswerText
		}
	}
	seq := turn.StreamState.LastSeq
	if seq == 0 {
		seq = 1
	}
	envelope := streaming.Envelope{
		EventID:   turn.TurnID + ":replay",
		StreamID:  turn.TurnID,
		EventType: string(eventType),
		Seq:       seq,
		TraceID:   turn.TraceID,
		Payload:   payload,
		CreatedAt: s.now(),
	}
	if turn.TerminalSnapshot != nil && turn.TerminalSnapshot.Failure != nil {
		envelope.RuntimeFailure = runtimeFailureFromTerminal(
			*turn.TerminalSnapshot.Failure,
		)
	}
	if emit != nil {
		if err := emit(envelope); err != nil {
			return nil, err
		}
	}
	return []streaming.Envelope{envelope}, nil
}

func (s *AssistantService) sessionContext(
	ctx context.Context,
	userID string,
	turn assistant.AssistantTurn,
) (
	[]assistant.AssistantSessionContextTurn,
	*assistant.AssistantSessionContextSummary,
	error,
) {
	store, err := s.requireSessionRunStore()
	if err != nil {
		return nil, nil, err
	}
	policy := channelpkg.Resolve(turn.TurnType, turn.Trigger).ContextWindow()
	if policy.HistoryReadLimit <= 0 {
		return nil, nil, nil
	}
	if err := s.advanceSessionSummary(
		ctx,
		userID,
		turn.SessionID,
		policy.RecentTurnLimit,
	); err != nil {
		return nil, nil, err
	}
	session, found, err := store.GetSession(ctx, turn.SessionID)
	if err != nil {
		return nil, nil, assistantSessionStorageUnavailable(err.Error())
	}
	if !found || session.UserID != userID {
		return nil, nil, assistantSessionNotFound()
	}
	candidates, err := store.ListCompletedTurns(
		ctx,
		userID,
		turn.SessionID,
		policy.RecentTurnLimit,
	)
	if err != nil {
		return nil, nil, assistantRunStorageUnavailable(err.Error())
	}
	filtered := make([]assistant.AssistantTurn, 0, len(candidates))
	for _, candidate := range candidates {
		if candidate.TurnID == turn.TurnID {
			continue
		}
		filtered = append(filtered, candidate)
	}
	return sessionContextFromTurns(filtered), session.ContextSummary, nil
}

func (s *AssistantService) advanceSessionSummary(
	ctx context.Context,
	userID string,
	sessionID string,
	recentTurnLimit int,
) error {
	if recentTurnLimit <= 0 {
		recentTurnLimit = 1
	}
	store, err := s.requireSessionRunStore()
	if err != nil {
		return err
	}
	for attempt := 0; attempt < 8; attempt++ {
		session, found, getErr := store.GetSession(ctx, sessionID)
		if getErr != nil {
			return assistantSessionStorageUnavailable(getErr.Error())
		}
		if !found || session.UserID != userID {
			return assistantSessionNotFound()
		}
		pending, listErr := store.ListCompletedTurnsAfterSequence(
			ctx,
			userID,
			sessionID,
			session.SummarySourceSequence,
			200,
		)
		if listErr != nil {
			return assistantRunStorageUnavailable(listErr.Error())
		}
		if len(pending) <= recentTurnLimit {
			return nil
		}
		toCompact := pending[:len(pending)-recentTurnLimit]
		next := advanceSessionContextSummary(session.ContextSummary, toCompact)
		nextSourceSequence := toCompact[len(toCompact)-1].CompletionSequence
		swapped, swapErr := store.CompareAndSwapSessionSummary(
			ctx,
			sessionID,
			session.SummaryVersion,
			session.SummarySourceSequence,
			nextSourceSequence,
			next,
			s.now(),
		)
		if swapErr != nil {
			return assistantSessionStorageUnavailable(swapErr.Error())
		}
		if !swapped {
			continue
		}
		if len(pending) < 200 {
			return nil
		}
	}
	return assistantSessionStorageUnavailable(
		"session summary CAS retry budget exhausted",
	)
}
