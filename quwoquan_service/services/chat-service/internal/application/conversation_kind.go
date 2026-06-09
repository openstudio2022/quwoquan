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

// NormalizeConversationType 收口会话类型语义。商用版本只接受
// direct/group/encrypted；历史 circle 类型必须迁移或清理，不再运行时兼容。
func NormalizeConversationType(rawType string, circleID string) string {
	if strings.TrimSpace(circleID) != "" {
		return conversationTypeGroup
	}
	return strings.TrimSpace(rawType)
}

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
	return strings.TrimSpace(conv.CircleId) != "" || strings.TrimSpace(conv.CircleGroupId) != ""
}
