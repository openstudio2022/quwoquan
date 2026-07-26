package application

import (
	"strings"

	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
)

func rejectCircleGroupManaged(conversation *model.Conversation, operation string) error {
	if conversation == nil || !IsCircleBoundConversation(*conversation) {
		return nil
	}
	return generated.AppErrorFromCircleGroupManagedByCircle(
		"circle group conversation rejects Chat operation " + strings.TrimSpace(operation),
	)
}
