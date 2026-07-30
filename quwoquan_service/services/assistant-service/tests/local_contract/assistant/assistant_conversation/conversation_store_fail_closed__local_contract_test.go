// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

// TestAssistantConversationStoreFailClosed 锁定：conversation/run store 未装配时
// 全部读写 fail-closed 返回 conversation_storage_unavailable，禁止回退进程内 map。
func TestAssistantConversationStoreFailClosed(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	service := NewAssistantService(
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)

	assertStorageUnavailable := func(operation string, err error) {
		t.Helper()
		var appErr *rterr.AppError
		if !errors.As(err, &appErr) ||
			!strings.Contains(appErr.Code.String(), "storage_unavailable") {
			t.Fatalf("%s must fail closed with storage_unavailable, got %v", operation, err)
		}
	}

	_, err := service.CreateConversation(ctx, "user-a", assistant.CreateConversationInput{
		Summary: "s", ClientRequestID: "storage-failure-conversation",
	})
	assertStorageUnavailable("CreateConversation", err)
	_, err = service.GetConversation(ctx, "user-a", "conv-1")
	assertStorageUnavailable("GetConversation", err)
	_, err = service.CreateTurn(ctx, "user-a", "conv-1", assistant.CreateTurnInput{
		Input:           assistant.AssistantTurnInput{Text: "hello"},
		ClientRequestID: "storage-failure-turn",
	})
	assertStorageUnavailable("CreateTurn", err)
	_, err = service.GetTurn(ctx, "user-a", "turn-1")
	assertStorageUnavailable("GetTurn", err)
	_, err = service.ExecuteTurn(ctx, "user-a", "turn-1")
	assertStorageUnavailable("ExecuteTurn", err)
}

func TestAssistantConversationAndRunRequireStableClientRequestID(t *testing.T) {
	t.Parallel()
	service := NewAssistantService(
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
	)
	ctx := context.Background()

	_, err := service.CreateConversation(
		ctx,
		"user-a",
		assistant.CreateConversationInput{},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.invalid_argument") {
		t.Fatalf("empty conversation clientRequestId error = %v", err)
	}

	conversation, err := service.CreateConversation(
		ctx,
		"user-a",
		assistant.CreateConversationInput{ClientRequestID: "conversation-intent"},
	)
	if err != nil {
		t.Fatalf("create conversation with request identity: %v", err)
	}
	_, err = service.CreateTurn(
		ctx,
		"user-a",
		conversation.ConversationID,
		assistant.CreateTurnInput{
			Input: assistant.AssistantTurnInput{Text: "hello"},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("empty run clientRequestId error = %v", err)
	}
}
