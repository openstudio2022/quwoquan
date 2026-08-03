package application

import (
	"strings"

	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

const (
	conversationTypeDirect    = "direct"
	conversationTypeGroup     = "group"
	conversationTypeEncrypted = "encrypted"
)

// conversationOriginGreetingReply 是 ConversationOriginType 闭集中「打招呼被回复
// 后升级」的取值（_shared/types.yaml ConversationOriginType）。
const conversationOriginGreetingReply = "greeting_reply"

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

func IsManagedConversation(conv model.Conversation) bool {
	// circleId only describes an origin. Explicit CircleGroup or Gathering
	// bindings transfer membership/role/lifecycle authority to the source object.
	return strings.TrimSpace(conv.CircleGroupId) != "" || strings.TrimSpace(conv.GatheringId) != ""
}
