package application

import (
	"strings"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	generated "quwoquan_service/services/chat-service/internal/generated"
)

func rejectCircleGroupManaged(conversation *model.Conversation, operation string) error {
	if conversation == nil || !IsCircleBoundConversation(*conversation) {
		return nil
	}
	return generated.AppErrorFromCircleGroupManagedByCircle(
		"circle group conversation rejects Chat operation " + strings.TrimSpace(operation),
	)
}
