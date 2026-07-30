package application

import (
	"context"
	"sort"
	"strings"

	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
)

const searchFetchBatchSize = 200

type MessageSearchHit struct {
	Conversation conversationmodel.Conversation
	Message      messagemodel.Message
}

type ContactSearchHit struct {
	ContactID        string
	UserHandle       string
	DisplayName      string
	AvatarURL        string
	Bio              string
	MetFrom          string
	LastInteraction  string
	RelationState    string
	ConversationID   string
	ConversationType string
	Source           string
	Subtitle         string
	HighlightText    string
	MatchedField     string
	IsStarred        bool
}

func listUserConversations(
	ctx context.Context,
	conversationStore ConversationStore,
	userStates UserStateStore,
	userID string,
) ([]conversationmodel.Conversation, error) {
	states, err := userStates.ListUserStates(ctx, userID, searchFetchBatchSize, "")
	if err != nil {
		return nil, err
	}
	conversations := make([]conversationmodel.Conversation, 0, len(states))
	seen := make(map[string]struct{}, len(states))
	for _, state := range states {
		conversationID := strings.TrimSpace(state.ConversationId)
		if conversationID == "" {
			continue
		}
		if _, ok := seen[conversationID]; ok {
			continue
		}
		conversation, err := conversationStore.FindConversationByID(ctx, conversationID)
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
	return clampLimit(limit, defaultLimit, 100)
}

func clampLimit(limit int, defaultLimit int, maxLimit int) int {
	if limit <= 0 {
		return defaultLimit
	}
	if limit > maxLimit {
		return maxLimit
	}
	return limit
}
