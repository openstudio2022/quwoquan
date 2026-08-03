package application

import (
	"strings"

	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func rejectSourceManagedConversation(conversation *model.Conversation, operation string) error {
	if conversation == nil || !IsManagedConversation(*conversation) {
		return nil
	}
	return generated.AppErrorFromSourceManagedConversation(
		"source-managed conversation rejects Chat operation " + strings.TrimSpace(operation),
	)
}
