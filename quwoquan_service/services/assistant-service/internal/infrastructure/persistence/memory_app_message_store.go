package persistence

import (
	"context"
	"sort"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type MemoryAppMessageStore struct {
	mu       sync.RWMutex
	messages map[string]assistant.AppMessage
}

func NewMemoryAppMessageStore() *MemoryAppMessageStore {
	return &MemoryAppMessageStore{messages: map[string]assistant.AppMessage{}}
}

func (s *MemoryAppMessageStore) CreateAppMessage(_ context.Context, message assistant.AppMessage) (assistant.AppMessage, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.messages[message.MessageID] = message
	return message, nil
}

func (s *MemoryAppMessageStore) GetAppMessage(_ context.Context, userID, messageID string) (assistant.AppMessage, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	message, ok := s.messages[messageID]
	if !ok || message.UserID != userID {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "消息不存在", "app message not found")
	}
	return message, nil
}

func (s *MemoryAppMessageStore) ListAppMessages(_ context.Context, userID string, limit int, _ string) ([]assistant.AppMessage, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]assistant.AppMessage, 0, len(s.messages))
	for _, message := range s.messages {
		if message.UserID == userID {
			items = append(items, message)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func (s *MemoryAppMessageStore) AckAppMessage(_ context.Context, userID, messageID string, ackedAt time.Time) (assistant.AppMessage, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	message, ok := s.messages[messageID]
	if !ok || message.UserID != userID {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "消息不存在", "app message not found")
	}
	message.AckedAt = &ackedAt
	s.messages[messageID] = message
	return message, nil
}

func (s *MemoryAppMessageStore) ReadAppMessage(_ context.Context, userID, messageID string, readAt time.Time) (assistant.AppMessage, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	message, ok := s.messages[messageID]
	if !ok || message.UserID != userID {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "消息不存在", "app message not found")
	}
	message.Read = true
	message.ReadAt = &readAt
	s.messages[messageID] = message
	return message, nil
}

func (s *MemoryAppMessageStore) UnreadAppMessageCount(_ context.Context, userID string) (int, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	count := 0
	for _, message := range s.messages {
		if message.UserID == userID && !message.Read {
			count++
		}
	}
	return count, nil
}
