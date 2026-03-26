package application

import (
	"context"
	"sort"
	"strings"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

const searchFetchBatchSize = 200

type MessageSearchHit struct {
	Conversation model.Conversation
	Message      model.Message
}

type ContactSearchHit struct {
	ContactID        string
	DisplayName      string
	AvatarURL        string
	ConversationID   string
	ConversationType string
	Subtitle         string
	HighlightText    string
	MatchedField     string
}

func listUserConversations(
	ctx context.Context,
	repo persistence.ChatRepository,
	userID string,
) ([]model.Conversation, error) {
	states, err := repo.ListUserStates(ctx, userID, searchFetchBatchSize, "")
	if err != nil {
		return nil, err
	}
	conversations := make([]model.Conversation, 0, len(states))
	seen := make(map[string]struct{}, len(states))
	for _, state := range states {
		conversationID := strings.TrimSpace(state.ConversationId)
		if conversationID == "" {
			continue
		}
		if _, ok := seen[conversationID]; ok {
			continue
		}
		conversation, err := repo.FindConversationByID(ctx, conversationID)
		if err != nil || conversation == nil {
			continue
		}
		seen[conversationID] = struct{}{}
		conversations = append(conversations, *conversation)
	}
	sort.SliceStable(conversations, func(i, j int) bool {
		return conversations[i].LastMessageTime.After(conversations[j].LastMessageTime)
	})
	return conversations, nil
}

func normalizeSearchQuery(raw string) string {
	return strings.TrimSpace(strings.ToLower(raw))
}

func containsQuery(values []string, query string) (bool, string) {
	for _, value := range values {
		if strings.Contains(strings.ToLower(strings.TrimSpace(value)), query) {
			return true, value
		}
	}
	return false, ""
}

func clampSearchLimit(limit int, defaultLimit int) int {
	if limit <= 0 {
		return defaultLimit
	}
	if limit > 100 {
		return 100
	}
	return limit
}
