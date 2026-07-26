package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type ChatGroundingClient interface {
	ResolveAssistantDeliveryMembership(
		ctx context.Context,
		conversationID string,
		creatorPersonaID string,
		assistantMemberID string,
		assistantSkillID string,
	) (bool, error)
	ListMessages(
		ctx context.Context,
		conversationID string,
		creatorPersonaID string,
		assistantSkillID string,
		beforeSeq int64,
		limit int,
	) ([]ChatGroundingMessage, error)
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

type ChatGroundingSendMessageRequest struct {
	ConversationID   string
	CreatorPersonaID string
	AssistantSkillID string
	Type             string
	Content          string
	ClientMsgID      string
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
	evt.MessageID = strings.TrimSpace(evt.MessageID)
	evt.AssistantMemberID = strings.TrimSpace(evt.AssistantMemberID)
	evt.SenderID = strings.TrimSpace(evt.SenderID)
	evt.Content = strings.TrimSpace(evt.Content)
	if evt.ConversationID == "" ||
		evt.AssistantMemberID == "" ||
		evt.SenderID == "" ||
		evt.Content == "" ||
		(evt.MessageID == "" && evt.Seq <= 0) {
		return fmt.Errorf("assistant mention missing required fields")
	}
	if s.chatGrounding == nil {
		return fmt.Errorf("assistant chat grounding client not configured")
	}
	membershipCurrent, err := s.chatGrounding.
		ResolveAssistantDeliveryMembership(
			ctx,
			evt.ConversationID,
			evt.SenderID,
			evt.AssistantMemberID,
			evt.AssistantSkillID,
		)
	if err != nil {
		return fmt.Errorf("resolve chat assistant membership: %w", err)
	}
	if !membershipCurrent {
		// 成员治理归 chat 域。事件领取后若小趣已被移除或技能身份已变更，
		// 该历史 mention 已无权触发回复，返回 nil 让 durable consumer
		// ack-and-drop，禁止进入 DLQ 后重放越权回复。
		return nil
	}
	messages, err := s.chatGrounding.ListMessages(
		ctx,
		evt.ConversationID,
		evt.SenderID,
		evt.AssistantSkillID,
		evt.Seq,
		20,
	)
	if err != nil {
		return fmt.Errorf("list chat messages: %w", err)
	}
	summary := buildConversationGroundingPrompt(evt, messages)
	mentionIdentity := assistantMentionClientRequestIdentity(evt)
	conversation, err := s.CreateConversation(ctx, evt.SenderID, assistant.CreateConversationInput{
		Summary:         "群聊 @小趣：" + evt.ConversationID,
		ClientRequestID: mentionIdentity + ":conversation",
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
		Trigger:         assistant.AssistantTurnTrigger{Type: "chat_assistant_mentioned"},
		ClientRequestID: mentionIdentity + ":turn",
	})
	if err != nil {
		return err
	}
	if _, err := s.ExecuteTurn(ctx, evt.SenderID, turn.TurnID); err != nil {
		return err
	}
	stored, err := s.GetTurn(ctx, evt.SenderID, turn.TurnID)
	if err != nil {
		return err
	}
	answer := ""
	if stored.TerminalSnapshot != nil {
		answer = strings.TrimSpace(stored.TerminalSnapshot.AnswerText)
	}
	if answer == "" {
		return fmt.Errorf(
			"assistant mention run %s finished without a terminal answer",
			turn.TurnID,
		)
	}
	return s.chatGrounding.SendMessage(ctx, ChatGroundingSendMessageRequest{
		ConversationID:   evt.ConversationID,
		CreatorPersonaID: evt.SenderID,
		AssistantSkillID: evt.AssistantSkillID,
		Type:             "text",
		Content:          answer,
		ClientMsgID:      "assistant-" + turn.TurnID,
	})
}

func assistantMentionClientRequestIdentity(evt AssistantMentionedEvent) string {
	eventID := strings.TrimSpace(evt.MessageID)
	if eventID == "" {
		eventID = fmt.Sprintf("seq-%d", evt.Seq)
	}
	return strings.Join(
		[]string{
			"assistant-mention",
			strings.TrimSpace(evt.ConversationID),
			eventID,
			strings.TrimSpace(evt.AssistantMemberID),
		},
		":",
	)
}

func buildConversationGroundingPrompt(
	evt AssistantMentionedEvent,
	messages []ChatGroundingMessage,
) string {
	var b strings.Builder
	b.WriteString("用户在群聊中 @小趣，请基于最近话题回答。\n")
	b.WriteString("触发消息：")
	b.WriteString(evt.Content)
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
