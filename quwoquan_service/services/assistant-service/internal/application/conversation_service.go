package application

import (
	"context"
	"sort"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	rtid "quwoquan_service/runtime/id"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func (s *AssistantService) CreateConversation(_ context.Context, userID string, input assistant.CreateConversationInput) (assistant.AssistantConversation, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.AssistantConversation{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	conversationID, err := rtid.Generate(rtid.PrefixAssistantConversation)
	if err != nil {
		return assistant.AssistantConversation{}, rterr.NewUnavailable(rterr.ModuleAssistant, "生成对话 ID 失败", err.Error())
	}
	now := s.now()
	conversation := assistant.AssistantConversation{
		ConversationID: conversationID,
		UserID:         userID,
		State:          "active",
		Summary:        strings.TrimSpace(input.Summary),
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.conversations[conversationID] = conversation
	return conversation, nil
}

func (s *AssistantService) GetConversation(_ context.Context, userID, conversationID string) (assistant.AssistantConversation, error) {
	userID = strings.TrimSpace(userID)
	conversationID = strings.TrimSpace(conversationID)
	s.mu.RLock()
	defer s.mu.RUnlock()
	conversation, ok := s.conversations[conversationID]
	if !ok || conversation.UserID != userID {
		return assistant.AssistantConversation{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "对话不存在", "assistant conversation not found")
	}
	return conversation, nil
}

func (s *AssistantService) CreateTurn(_ context.Context, userID, conversationID string, input assistant.CreateTurnInput) (assistant.AssistantTurn, error) {
	userID = strings.TrimSpace(userID)
	conversationID = strings.TrimSpace(conversationID)
	if strings.TrimSpace(input.Input.Text) == "" {
		return assistant.AssistantTurn{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "turn input 不能为空", "missing turn input text")
	}
	turnID, err := rtid.Generate(rtid.PrefixAssistantTurn)
	if err != nil {
		return assistant.AssistantTurn{}, rterr.NewUnavailable(rterr.ModuleAssistant, "生成轮次 ID 失败", err.Error())
	}
	now := s.now()
	turnType := strings.TrimSpace(input.TurnType)
	if turnType == "" {
		turnType = "user"
	}
	trigger := input.Trigger
	trigger.Type = strings.TrimSpace(trigger.Type)
	if trigger.Type == "" {
		trigger.Type = "user_message"
	}
	traceID := turnID
	turn := assistant.AssistantTurn{
		TurnID:         turnID,
		ConversationID: conversationID,
		UserID:         userID,
		TurnType:       turnType,
		Status:         "running",
		SkillID:        strings.TrimSpace(input.SkillID),
		DomainID:       strings.TrimSpace(input.DomainID),
		Input: assistant.AssistantTurnInput{
			Text: strings.TrimSpace(input.Input.Text),
		},
		Trigger:   trigger,
		TraceID:   traceID,
		CreatedAt: now,
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	conversation, ok := s.conversations[conversationID]
	if !ok || conversation.UserID != userID {
		return assistant.AssistantTurn{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "对话不存在", "assistant conversation not found")
	}
	conversation.ActiveTurnID = turnID
	conversation.LastTurnID = turnID
	conversation.UpdatedAt = now
	s.conversations[conversationID] = conversation
	s.turns[turnID] = turn
	return turn, nil
}

func (s *AssistantService) GetTurn(_ context.Context, userID, turnID string) (assistant.AssistantTurn, error) {
	userID = strings.TrimSpace(userID)
	turnID = strings.TrimSpace(turnID)
	s.mu.RLock()
	defer s.mu.RUnlock()
	turn, ok := s.turns[turnID]
	if !ok || turn.UserID != userID {
		return assistant.AssistantTurn{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "轮次不存在", "assistant turn not found")
	}
	return turn, nil
}

func (s *AssistantService) BuildFakeTurnStream(ctx context.Context, userID, turnID string) ([]streaming.Envelope, error) {
	return s.buildTurnStream(ctx, userID, turnID, nil)
}

func (s *AssistantService) StreamTurn(ctx context.Context, userID, turnID string, emit func(streaming.Envelope) error) error {
	_, err := s.buildTurnStream(ctx, userID, turnID, emit)
	return err
}

func (s *AssistantService) buildTurnStream(ctx context.Context, userID, turnID string, emit func(streaming.Envelope) error) ([]streaming.Envelope, error) {
	turn, err := s.GetTurn(ctx, userID, turnID)
	if err != nil {
		return nil, err
	}
	turn.ContextTurns = s.conversationContextTurns(userID, turn)
	now := s.now()
	loop := s.agentLoop
	if loop == nil {
		loop = NewAgentLoop(nil, ReactRuntime{}, s.now)
	}
	out, failure, err := loop.RunTurnWithSink(ctx, turn, emit)
	if err != nil {
		return nil, err
	}
	completedAt := now
	s.mu.Lock()
	stored := s.turns[turn.TurnID]
	if failure != nil {
		stored.Status = "failed"
		stored.Failure = failure
	} else {
		stored.Status = "completed"
		stored.AnswerText = finalAnswerTextFromEvents(out)
	}
	if stored.SkillID == "" {
		stored.SkillID = skillIDFromEvents(out)
	}
	if stored.DomainID == "" {
		stored.DomainID = domainIDFromEvents(out)
	}
	stored.StreamState = assistant.AssistantTurnStreamState{
		LastSeq:     uint64(len(out)),
		Completed:   failure == nil,
		ResumeToken: streaming.NewResumeToken(turn.TurnID, uint64(len(out))),
	}
	stored.CompletedAt = &completedAt
	s.turns[turn.TurnID] = stored
	if conversation := s.conversations[turn.ConversationID]; conversation.ConversationID != "" {
		conversation.ActiveTurnID = ""
		conversation.LastTurnID = turn.TurnID
		conversation.UpdatedAt = completedAt
		s.conversations[turn.ConversationID] = conversation
	}
	s.mu.Unlock()
	return out, nil
}

func (s *AssistantService) conversationContextTurns(userID string, turn assistant.AssistantTurn) []assistant.AssistantConversationContextTurn {
	s.mu.RLock()
	defer s.mu.RUnlock()
	candidates := []assistant.AssistantTurn{}
	for _, item := range s.turns {
		if item.UserID != userID || item.ConversationID != turn.ConversationID || item.TurnID == turn.TurnID {
			continue
		}
		if item.Status != "completed" {
			continue
		}
		if strings.TrimSpace(item.Input.Text) == "" {
			continue
		}
		candidates = append(candidates, item)
	}
	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].CreatedAt.Before(candidates[j].CreatedAt)
	})
	if len(candidates) > 6 {
		candidates = candidates[len(candidates)-6:]
	}
	out := []assistant.AssistantConversationContextTurn{}
	for _, item := range candidates {
		out = append(out, assistant.AssistantConversationContextTurn{
			Role:     "user",
			Text:     item.Input.Text,
			SkillID:  item.SkillID,
			DomainID: item.DomainID,
		})
		answer := strings.TrimSpace(item.AnswerText)
		if answer != "" {
			out = append(out, assistant.AssistantConversationContextTurn{
				Role:     "assistant",
				Text:     answer,
				SkillID:  item.SkillID,
				DomainID: item.DomainID,
			})
		}
	}
	return out
}

func finalAnswerTextFromEvents(events []streaming.Envelope) string {
	for i := len(events) - 1; i >= 0; i-- {
		event := events[i]
		if event.EventType != "final_answer" && event.EventType != "assistant.answer.final" {
			continue
		}
		if text := strings.TrimSpace(stringValue(event.Payload["text"])); text != "" {
			return text
		}
		if text := strings.TrimSpace(stringValue(event.Payload["userMarkdown"])); text != "" {
			return text
		}
	}
	return ""
}

func skillIDFromEvents(events []streaming.Envelope) string {
	for _, event := range events {
		if event.EventType != "understanding_updated" && event.EventType != "plan_updated" {
			continue
		}
		if skillID := strings.TrimSpace(stringValue(event.Payload["skillId"])); skillID != "" {
			return skillID
		}
	}
	return ""
}

func domainIDFromEvents(events []streaming.Envelope) string {
	for _, event := range events {
		if event.EventType != "understanding_updated" {
			continue
		}
		if domainID := strings.TrimSpace(stringValue(event.Payload["domainId"])); domainID != "" {
			return domainID
		}
	}
	return ""
}
