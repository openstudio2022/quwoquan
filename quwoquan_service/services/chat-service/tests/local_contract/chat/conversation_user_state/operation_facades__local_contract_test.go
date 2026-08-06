// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: mark-as-read-local
// readiness_case: update-conversation-settings-local
package local_contract

import (
	"context"
	"testing"

	userstateapp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/application"
)

func TestConversationUserStateUseCasesExecuteBothCommandFacets(t *testing.T) {
	backend := &userStateOperationBackend{}
	useCases := userstateapp.NewUseCases(backend, backend)
	ctx := context.Background()

	if err := useCases.MarkAsRead(ctx, userstateapp.MarkAsReadRequest{
		ConversationId: "conversation-1", MessageId: "message-7", UserId: "persona-1",
	}); err != nil {
		t.Fatal(err)
	}
	muted := true
	if err := useCases.UpdateSettings(ctx, userstateapp.UpdateSettingsRequest{
		ConversationId: "conversation-1", UserId: "persona-1", Muted: &muted,
	}); err != nil {
		t.Fatal(err)
	}
	if backend.read.MessageId != "message-7" || backend.read.UserId != "persona-1" {
		t.Fatalf("MarkAsRead request drift: %+v", backend.read)
	}
	if backend.settings.Muted == nil || !*backend.settings.Muted || backend.settings.ConversationId != "conversation-1" {
		t.Fatalf("UpdateConversationSettings request drift: %+v", backend.settings)
	}
}

type userStateOperationBackend struct {
	read     userstateapp.MarkAsReadRequest
	settings userstateapp.UpdateSettingsRequest
}

func (backend *userStateOperationBackend) MarkAsRead(_ context.Context, request userstateapp.MarkAsReadRequest) error {
	backend.read = request
	return nil
}

func (backend *userStateOperationBackend) UpdateSettings(_ context.Context, request userstateapp.UpdateSettingsRequest) error {
	backend.settings = request
	return nil
}
