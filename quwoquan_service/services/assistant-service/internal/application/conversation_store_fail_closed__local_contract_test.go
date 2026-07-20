package application

import (
	"context"
	"errors"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

// TestAssistantConversationStoreFailClosed 锁定：conversation/run store 未装配时
// 全部读写 fail-closed 返回 conversation_storage_unavailable，禁止回退进程内 map。
func TestAssistantConversationStoreFailClosed(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
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

	_, err := service.CreateConversation(ctx, "user-a", assistant.CreateConversationInput{Summary: "s"})
	assertStorageUnavailable("CreateConversation", err)
	_, err = service.GetConversation(ctx, "user-a", "conv-1")
	assertStorageUnavailable("GetConversation", err)
	_, err = service.CreateTurn(ctx, "user-a", "conv-1", assistant.CreateTurnInput{
		Input: assistant.AssistantTurnInput{Text: "hello"},
	})
	assertStorageUnavailable("CreateTurn", err)
	_, err = service.GetTurn(ctx, "user-a", "turn-1")
	assertStorageUnavailable("GetTurn", err)
	_, err = service.ExecuteTurn(ctx, "user-a", "turn-1")
	assertStorageUnavailable("ExecuteTurn", err)
}
