package application

import (
	"strings"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

const (
	conversationTypeDirect    = "direct"
	conversationTypeGroup     = "group"
	conversationTypeCircle    = "circle"
	conversationTypeEncrypted = "encrypted"
)

// NormalizeConversationType 收口会话类型语义：
// - 对外产品语义只区分 direct/group/encrypted
// - 绑定 circleId 的会话仍是 group，只是圈子发起/绑定的默认群
// - legacy circle 数据继续按 group 兼容读取
func NormalizeConversationType(rawType string, circleID string) string {
	if strings.TrimSpace(circleID) != "" {
		return conversationTypeGroup
	}
	switch strings.TrimSpace(rawType) {
	case conversationTypeCircle:
		return conversationTypeGroup
	default:
		return strings.TrimSpace(rawType)
	}
}

func PublicConversationType(rawType string, circleID string) string {
	normalized := NormalizeConversationType(rawType, circleID)
	if normalized != "" {
		return normalized
	}
	return strings.TrimSpace(rawType)
}

func IsGroupConversationType(rawType string) bool {
	switch strings.TrimSpace(rawType) {
	case conversationTypeGroup, conversationTypeCircle:
		return true
	default:
		return false
	}
}

func IsGroupConversation(conv model.Conversation) bool {
	return IsGroupConversationType(conv.Type)
}

func IsCircleBoundConversation(conv model.Conversation) bool {
	return strings.TrimSpace(conv.CircleId) != "" || strings.TrimSpace(conv.Type) == conversationTypeCircle
}
