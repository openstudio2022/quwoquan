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

func IsCircleBoundConversation(conv model.Conversation) bool {
	// circleId only describes an origin. Only an explicit CircleGroup binding
	// transfers membership/role/lifecycle authority away from Chat.
	return strings.TrimSpace(conv.CircleGroupId) != ""
}
