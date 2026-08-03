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
	SenderAccountID    string
	SenderID           string
	Content            string
	AssistantMemberID  string
}

func WithChatGroundingClient(client ports.ChatGroundingClient) AssistantServiceOption {
	return func(s *AssistantService) { s.chatGrounding = client }
}

func (s *AssistantService) HandleAssistantMentioned(ctx context.Context, evt AssistantMentionedEvent) error {
	evt.ChatConversationID = strings.TrimSpace(evt.ChatConversationID)
	evt.MessageID = strings.TrimSpace(evt.MessageID)
	evt.AssistantMemberID = strings.TrimSpace(evt.AssistantMemberID)
	evt.SenderAccountID = strings.TrimSpace(evt.SenderAccountID)
	evt.SenderID = strings.TrimSpace(evt.SenderID)
	evt.Content = strings.TrimSpace(evt.Content)
	if evt.ChatConversationID == "" ||
		evt.AssistantMemberID == "" ||
		evt.SenderAccountID == "" ||
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
		)
	if err != nil {
		return fmt.Errorf("resolve chat assistant membership: %w", err)
	}
	if !membershipCurrent {
		// 成员治理归 chat 域。事件领取后若小趣已被移除，
		// 该历史 mention 已无权触发回复，返回 nil 让 durable consumer
		// ack-and-drop，禁止进入 DLQ 后重放越权回复。
		return nil
	}
	messages, err := s.chatGrounding.ListMessages(
		ctx,
		evt.ChatConversationID,
		evt.SenderID,
		evt.Seq,
		channelpkg.GroupMention().ContextWindow().MessageLimit,
	)
	if err != nil {
		return fmt.Errorf("list chat messages: %w", err)
	}
	contextSnapshot, err := buildChatConversationContextSnapshot(evt, messages)
	if err != nil {
		return err
	}
	mentionIdentity := assistantMentionClientRequestIdentity(evt)
	session, err := s.CreateSession(ctx, evt.SenderAccountID, assistant.CreateSessionInput{
		Summary:         "群聊 @小趣：" + evt.ChatConversationID,
		ClientRequestID: mentionIdentity + ":session",
	})
	if err != nil {
		return err
	}
	run, err := s.startCanonicalRunAndWait(ctx, evt.SenderAccountID, session.SessionID, canonicalRunInput{
		Text:            evt.Content,
		PersonaID:       evt.SenderID,
		SurfaceKind:     "conversation",
		SurfaceID:       evt.ChatConversationID,
		ContextSnapshot: contextSnapshot,
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

func buildChatConversationContextSnapshot(
	evt AssistantMentionedEvent,
	messages []ports.ChatGroundingMessage,
) (map[string]any, error) {
	if len(messages) > channelpkg.GroupMention().ContextWindow().MessageLimit {
		return nil, fmt.Errorf("chat grounding window exceeds channel policy")
	}
	items := make([]any, 0, len(messages))
	for _, msg := range messages {
		if strings.TrimSpace(msg.MessageID) == "" || msg.Seq <= 0 ||
			strings.TrimSpace(msg.SenderID) == "" || strings.TrimSpace(msg.Type) == "" {
			return nil, fmt.Errorf("chat grounding message identity is invalid")
		}
		item := map[string]any{
			"messageId":       strings.TrimSpace(msg.MessageID),
			"seq":             msg.Seq,
			"senderPersonaId": strings.TrimSpace(msg.SenderID),
			"type":            strings.TrimSpace(msg.Type),
			"content":         strings.TrimSpace(msg.Content),
			"mentions":        append([]string(nil), msg.Mentions...),
		}
		if name := strings.TrimSpace(msg.SenderName); name != "" {
			item["senderDisplayName"] = name
		}
		if msg.ObjectRef != nil {
			if strings.TrimSpace(msg.ObjectRef.ObjectTypeRef) == "" ||
				strings.TrimSpace(msg.ObjectRef.ObjectID) == "" ||
				strings.TrimSpace(msg.ObjectRef.RouteID) == "" {
				return nil, fmt.Errorf("chat grounding object reference is invalid")
			}
			item["objectRef"] = map[string]any{
				"objectTypeRef": strings.TrimSpace(msg.ObjectRef.ObjectTypeRef),
				"objectId":      strings.TrimSpace(msg.ObjectRef.ObjectID),
				"routeId":       strings.TrimSpace(msg.ObjectRef.RouteID),
			}
		}
		items = append(items, item)
	}
	return map[string]any{
		"pageType": "conversation",
		"pageObjects": []any{map[string]any{
			"objectTypeRef": "chat.Conversation",
			"objectId":      evt.ChatConversationID,
		}},
		"conversationContext": map[string]any{
			"conversationId":   evt.ChatConversationID,
			"triggerMessageId": evt.MessageID,
			"triggerSeq":       evt.Seq,
			"messages":         items,
		},
	}, nil
}
