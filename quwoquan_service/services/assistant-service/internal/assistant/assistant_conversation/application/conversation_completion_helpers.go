package application

import (
	"context"
	"log/slog"
	"strings"

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
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
	score := ServiceScorecardFactCommand{
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
		"conversationId": turn.ConversationID,
		"turnId":         turn.TurnID,
		"status":         turn.Status,
		"resumeToken":    turn.StreamState.ResumeToken,
	}
	if turn.TerminalSnapshot != nil {
		payload["processes"] = turn.TerminalSnapshot.Processes
	}
	eventType := AssistantStreamEventCompleted
	switch turn.Status {
	case "failed":
		eventType = AssistantStreamEventFailed
	case "cancelled":
		eventType = AssistantStreamEventCancelled
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

func (s *AssistantService) conversationContextTurns(ctx context.Context, userID string, turn assistant.AssistantTurn) ([]assistant.AssistantConversationContextTurn, error) {
	store, err := s.requireConversationRunStore()
	if err != nil {
		return nil, err
	}
	candidates, err := store.ListCompletedTurns(ctx, userID, turn.ConversationID, 6)
	if err != nil {
		return nil, assistantRunStorageUnavailable(err.Error())
	}
	out := []assistant.AssistantConversationContextTurn{}
	for _, item := range candidates {
		if item.TurnID == turn.TurnID || strings.TrimSpace(item.Input.Text) == "" {
			continue
		}
		out = append(out, assistant.AssistantConversationContextTurn{
			Role:     "user",
			Text:     item.Input.Text,
			SkillID:  item.SkillID,
			DomainID: item.DomainID,
		})
		answer := ""
		if item.TerminalSnapshot != nil {
			answer = strings.TrimSpace(item.TerminalSnapshot.AnswerText)
		}
		if answer != "" {
			out = append(out, assistant.AssistantConversationContextTurn{
				Role:     "assistant",
				Text:     answer,
				SkillID:  item.SkillID,
				DomainID: item.DomainID,
			})
		}
	}
	return out, nil
}
