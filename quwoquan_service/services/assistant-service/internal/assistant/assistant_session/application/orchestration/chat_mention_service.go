package orchestration

import (
	"context"
	"fmt"
	"strings"

	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/channel"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

type AssistantMentionedEvent struct {
	ChatConversationID string
	MessageID          string
	Seq                int64
	SenderID           string
	Content            string
	AssistantMemberID  string
	AssistantSkillID   string
}

func WithChatGroundingClient(client ports.ChatGroundingClient) AssistantServiceOption {
	return func(s *AssistantService) { s.chatGrounding = client }
}

func (s *AssistantService) HandleAssistantMentioned(ctx context.Context, evt AssistantMentionedEvent) error {
	evt.ChatConversationID = strings.TrimSpace(evt.ChatConversationID)
	evt.MessageID = strings.TrimSpace(evt.MessageID)
	evt.AssistantMemberID = strings.TrimSpace(evt.AssistantMemberID)
	evt.SenderID = strings.TrimSpace(evt.SenderID)
	evt.Content = strings.TrimSpace(evt.Content)
	if evt.ChatConversationID == "" ||
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
			evt.ChatConversationID,
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
		evt.ChatConversationID,
		evt.SenderID,
		evt.AssistantSkillID,
		evt.Seq,
		channelpkg.GroupMention().ContextWindow().MessageLimit,
	)
	if err != nil {
		return fmt.Errorf("list chat messages: %w", err)
	}
	summary := buildChatConversationGroundingPrompt(evt, messages)
	mentionIdentity := assistantMentionClientRequestIdentity(evt)
	session, err := s.CreateSession(ctx, evt.SenderID, assistant.CreateSessionInput{
		Summary:         "群聊 @小趣：" + evt.ChatConversationID,
		ClientRequestID: mentionIdentity + ":session",
	})
	if err != nil {
		return err
	}
	run, err := s.startCanonicalRunAndWait(ctx, evt.SenderID, session.SessionID, canonicalRunInput{
		SkillID: strings.TrimSpace(evt.AssistantSkillID),
		Text:    summary,
		Trigger: assistant.AssistantTurnTrigger{
			Type:      "chat_assistant_mentioned",
			MessageID: evt.MessageID,
		},
		ClientRequestID: mentionIdentity + ":run",
	})
	if err != nil {
		return err
	}
	answer := ""
	if raw, ok := run.TerminalSnapshot["answerText"].(string); ok {
		answer = strings.TrimSpace(raw)
	}
	if answer == "" {
		return fmt.Errorf(
			"assistant mention run %s finished without a terminal answer",
			run.RunID,
		)
	}
	return s.chatGrounding.SendMessage(ctx, ports.ChatGroundingSendMessageRequest{
		ChatConversationID: evt.ChatConversationID,
		CreatorPersonaID:   evt.SenderID,
		AssistantSkillID:   evt.AssistantSkillID,
		Type:               "text",
		Content:            answer,
		ClientMsgID:        "assistant-" + run.RunID,
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
			strings.TrimSpace(evt.ChatConversationID),
			eventID,
			strings.TrimSpace(evt.AssistantMemberID),
		},
		":",
	)
}

func buildChatConversationGroundingPrompt(
	evt AssistantMentionedEvent,
	messages []ports.ChatGroundingMessage,
) string {
	var b strings.Builder
	b.WriteString("用户在群聊中 @小趣，请基于最近话题回答。\n")
	b.WriteString("触发消息：")
	b.WriteString(evt.Content)
	b.WriteString("\n最近消息：")
	objectRefs := make([]ports.ChatGroundingObjectRef, 0, len(messages))
	seenObjects := map[string]struct{}{}
	for _, msg := range messages {
		if msg.ObjectRef != nil {
			key := msg.ObjectRef.ObjectTypeRef + ":" + msg.ObjectRef.ObjectID
			if _, exists := seenObjects[key]; !exists {
				seenObjects[key] = struct{}{}
				objectRefs = append(objectRefs, *msg.ObjectRef)
			}
		}
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
	if len(objectRefs) > 0 {
		b.WriteString("\n会话内经成员权限过滤的对象引用：")
		for _, ref := range objectRefs {
			b.WriteString("\n- ")
			b.WriteString(ref.ObjectTypeRef)
			b.WriteString(":")
			b.WriteString(ref.ObjectID)
			b.WriteString(" route=")
			b.WriteString(ref.RouteID)
		}
	}
	return b.String()
}
