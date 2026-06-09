package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type ChatGroundingClient interface {
	ListMessages(ctx context.Context, conversationID string, beforeSeq int64, limit int) ([]ChatGroundingMessage, error)
	ListMembers(ctx context.Context, conversationID string, limit int) ([]ChatGroundingMember, error)
	SendMessage(ctx context.Context, req ChatGroundingSendMessageRequest) error
}

type ChatGroundingMessage struct {
	MessageID  string
	Seq        int64
	SenderID   string
	SenderName string
	Type       string
	Content    string
	Mentions   []string
	Timestamp  time.Time
}

type ChatGroundingMember struct {
	UserID           string
	DisplayName      string
	MemberType       string
	AssistantSkillID string
}

type ChatGroundingSendMessageRequest struct {
	ConversationID string
	SenderID       string
	Type           string
	Content        string
	ClientMsgID    string
}

type AssistantMentionedEvent struct {
	ConversationID    string
	MessageID         string
	Seq               int64
	SenderID          string
	Content           string
	AssistantMemberID string
	AssistantSkillID  string
}

func WithChatGroundingClient(client ChatGroundingClient) AssistantServiceOption {
	return func(s *AssistantService) { s.chatGrounding = client }
}

func (s *AssistantService) HandleAssistantMentioned(ctx context.Context, evt AssistantMentionedEvent) error {
	evt.ConversationID = strings.TrimSpace(evt.ConversationID)
	evt.AssistantMemberID = strings.TrimSpace(evt.AssistantMemberID)
	evt.SenderID = strings.TrimSpace(evt.SenderID)
	evt.Content = strings.TrimSpace(evt.Content)
	if evt.ConversationID == "" || evt.AssistantMemberID == "" || evt.SenderID == "" || evt.Content == "" {
		return fmt.Errorf("assistant mention missing required fields")
	}
	if s.chatGrounding == nil {
		return fmt.Errorf("assistant chat grounding client not configured")
	}
	messages, err := s.chatGrounding.ListMessages(ctx, evt.ConversationID, evt.Seq, 20)
	if err != nil {
		return fmt.Errorf("list chat messages: %w", err)
	}
	members, err := s.chatGrounding.ListMembers(ctx, evt.ConversationID, 100)
	if err != nil {
		return fmt.Errorf("list chat members: %w", err)
	}
	summary := buildConversationGroundingPrompt(evt, messages, members)
	conversation, err := s.CreateConversation(ctx, evt.SenderID, assistant.CreateConversationInput{
		Summary: "群聊 @小趣：" + evt.ConversationID,
	})
	if err != nil {
		return err
	}
	turn, err := s.CreateTurn(ctx, evt.SenderID, conversation.ConversationID, assistant.CreateTurnInput{
		TurnType: "proactive",
		SkillID:  strings.TrimSpace(evt.AssistantSkillID),
		Input: assistant.AssistantTurnInput{
			Text: summary,
		},
		Trigger: assistant.AssistantTurnTrigger{Type: "chat_assistant_mentioned"},
	})
	if err != nil {
		return err
	}
	if _, err := s.BuildFakeTurnStream(ctx, evt.SenderID, turn.TurnID); err != nil {
		return err
	}
	stored, err := s.GetTurn(ctx, evt.SenderID, turn.TurnID)
	if err != nil {
		return err
	}
	answer := strings.TrimSpace(stored.AnswerText)
	if answer == "" {
		answer = "我已看到这段群聊，会基于最近话题继续协助。"
	}
	return s.chatGrounding.SendMessage(ctx, ChatGroundingSendMessageRequest{
		ConversationID: evt.ConversationID,
		SenderID:       evt.AssistantMemberID,
		Type:           "text",
		Content:        answer,
		ClientMsgID:    "assistant-" + turn.TurnID,
	})
}

func buildConversationGroundingPrompt(evt AssistantMentionedEvent, messages []ChatGroundingMessage, members []ChatGroundingMember) string {
	var b strings.Builder
	b.WriteString("用户在群聊中 @小趣，请基于最近话题回答。\n")
	b.WriteString("触发消息：")
	b.WriteString(evt.Content)
	b.WriteString("\n群成员：")
	for i, member := range members {
		if i > 0 {
			b.WriteString("、")
		}
		name := strings.TrimSpace(member.DisplayName)
		if name == "" {
			name = member.UserID
		}
		b.WriteString(name)
		if member.MemberType == "assistant" {
			b.WriteString("(小趣)")
		}
	}
	b.WriteString("\n最近消息：")
	for _, msg := range messages {
		content := strings.TrimSpace(msg.Content)
		if content == "" {
			continue
		}
		name := strings.TrimSpace(msg.SenderName)
		if name == "" {
			name = msg.SenderID
		}
		b.WriteString("\n- ")
		b.WriteString(name)
		b.WriteString(": ")
		b.WriteString(content)
	}
	return b.String()
}
