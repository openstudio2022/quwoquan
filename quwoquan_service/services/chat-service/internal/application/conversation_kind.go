package application

import (
	"strings"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

const (
	conversationTypeDirect    = "direct"
	conversationTypeGroup     = "group"
	conversationTypeEncrypted = "encrypted"
)

func IsGroupConversationType(rawType string) bool {
	switch strings.TrimSpace(rawType) {
	case conversationTypeGroup:
		return true
	default:
		return false
	}
}

func IsGroupConversation(conv model.Conversation) bool {
	return IsGroupConversationType(conv.Type)
}

func IsCircleBoundConversation(conv model.Conversation) bool {
	// circleId only describes an origin. Only an explicit CircleGroup binding
	// transfers membership/role/lifecycle authority away from Chat.
	return strings.TrimSpace(conv.CircleGroupId) != ""
}
