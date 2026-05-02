package application

import (
	"context"
	"strings"
	"time"

	rtid "quwoquan_service/runtime/id"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"

	rterr "quwoquan_service/runtime/errors"
)

type AppMessageStore interface {
	CreateAppMessage(ctx context.Context, message assistant.AppMessage) (assistant.AppMessage, error)
	GetAppMessage(ctx context.Context, userID, messageID string) (assistant.AppMessage, error)
	ListAppMessages(ctx context.Context, userID string, limit int, cursor string) ([]assistant.AppMessage, error)
	AckAppMessage(ctx context.Context, userID, messageID string, ackedAt time.Time) (assistant.AppMessage, error)
	ReadAppMessage(ctx context.Context, userID, messageID string, readAt time.Time) (assistant.AppMessage, error)
	UnreadAppMessageCount(ctx context.Context, userID string) (int, error)
}

func WithAppMessageStore(store AppMessageStore) AssistantServiceOption {
	return func(s *AssistantService) { s.appMessages = store }
}

func (s *AssistantService) CreateAppMessage(ctx context.Context, input assistant.CreateAppMessageInput) (assistant.AppMessage, error) {
	if s.appMessages == nil {
		return assistant.AppMessage{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "app message store is not configured")
	}
	normalized, err := s.normalizeAppMessageInput(input)
	if err != nil {
		return assistant.AppMessage{}, err
	}
	return s.appMessages.CreateAppMessage(ctx, normalized)
}

func (s *AssistantService) ListAppMessages(ctx context.Context, userID string, limit int, cursor string) (assistant.AppMessageListView, error) {
	if s.appMessages == nil {
		return assistant.AppMessageListView{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "app message store is not configured")
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.AppMessageListView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	items, err := s.appMessages.ListAppMessages(ctx, userID, limit, strings.TrimSpace(cursor))
	if err != nil {
		return assistant.AppMessageListView{}, err
	}
	return assistant.AppMessageListView{Items: items}, nil
}

func (s *AssistantService) GetAppMessage(ctx context.Context, userID, messageID string) (assistant.AppMessage, error) {
	if s.appMessages == nil {
		return assistant.AppMessage{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "app message store is not configured")
	}
	return s.appMessages.GetAppMessage(ctx, strings.TrimSpace(userID), strings.TrimSpace(messageID))
}

func (s *AssistantService) AckAppMessage(ctx context.Context, userID, messageID string) (assistant.AppMessage, error) {
	if s.appMessages == nil {
		return assistant.AppMessage{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "app message store is not configured")
	}
	return s.appMessages.AckAppMessage(ctx, strings.TrimSpace(userID), strings.TrimSpace(messageID), s.now())
}

func (s *AssistantService) ReadAppMessage(ctx context.Context, userID, messageID string) (assistant.AppMessage, error) {
	if s.appMessages == nil {
		return assistant.AppMessage{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "app message store is not configured")
	}
	return s.appMessages.ReadAppMessage(ctx, strings.TrimSpace(userID), strings.TrimSpace(messageID), s.now())
}

func (s *AssistantService) GetAppMessageUnreadCount(ctx context.Context, userID string) (assistant.AppMessageUnreadCountView, error) {
	if s.appMessages == nil {
		return assistant.AppMessageUnreadCountView{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "app message store is not configured")
	}
	count, err := s.appMessages.UnreadAppMessageCount(ctx, strings.TrimSpace(userID))
	if err != nil {
		return assistant.AppMessageUnreadCountView{}, err
	}
	return assistant.AppMessageUnreadCountView{UnreadCount: count}, nil
}

func (s *AssistantService) normalizeAppMessageInput(input assistant.CreateAppMessageInput) (assistant.AppMessage, error) {
	input.UserID = strings.TrimSpace(input.UserID)
	if input.UserID == "" {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	messageType := strings.TrimSpace(input.MessageType)
	if messageType == "" {
		messageType = "assistant"
	}
	if strings.TrimSpace(input.Title) == "" {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "title 不能为空", "missing title")
	}
	if strings.TrimSpace(input.Summary) == "" {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "summary 不能为空", "missing summary")
	}
	destination := input.Destination
	destination.Type = strings.TrimSpace(destination.Type)
	destination.ID = strings.TrimSpace(destination.ID)
	if destination.Type == "" {
		destination.Type = "user"
	}
	if destination.ID == "" {
		destination.ID = input.UserID
	}
	if destination.Type != "user" {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "M3 仅支持 user destination", "unsupported destination type")
	}
	messageID, err := rtid.Generate(rtid.PrefixAppMessage)
	if err != nil {
		return assistant.AppMessage{}, rterr.NewUnavailable(rterr.ModuleAssistant, "生成消息 ID 失败", err.Error())
	}
	return assistant.AppMessage{
		MessageID:   messageID,
		UserID:      input.UserID,
		MessageType: messageType,
		Source:      strings.TrimSpace(input.Source),
		SourceID:    strings.TrimSpace(input.SourceID),
		Destination: destination,
		Title:       strings.TrimSpace(input.Title),
		Summary:     strings.TrimSpace(input.Summary),
		Target: assistant.AppMessageTarget{
			TargetType: strings.TrimSpace(input.Target.TargetType),
			TargetID:   strings.TrimSpace(input.Target.TargetID),
		},
		CreatedAt: s.now(),
	}, nil
}
