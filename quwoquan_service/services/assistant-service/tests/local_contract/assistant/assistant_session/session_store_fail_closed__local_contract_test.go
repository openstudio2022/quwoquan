// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

// TestAssistantSessionStoreFailClosed 锁定：session/run store 未装配时
// 全部读写 fail-closed 返回 session_storage_unavailable，禁止回退进程内 map。
func TestAssistantSessionStoreFailClosed(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	service := NewAssistantService(
		skillconsenttest.NewMemoryStore(),
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

	_, err := service.CreateSession(ctx, "user-a", assistant.CreateSessionInput{
		Summary: "s", ClientRequestID: "storage-failure-session",
	})
	assertStorageUnavailable("CreateSession", err)
	_, err = service.GetSession(ctx, "user-a", "conv-1")
	assertStorageUnavailable("GetSession", err)
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

func TestAssistantSessionAndRunRequireStableClientRequestID(t *testing.T) {
	t.Parallel()
	service := NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
		WithSessionRunStore(persistence.NewMemorySessionRunStore()),
	)
	ctx := context.Background()

	_, err := service.CreateSession(
		ctx,
		"user-a",
		assistant.CreateSessionInput{},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.invalid_argument") {
		t.Fatalf("empty session clientRequestId error = %v", err)
	}

	session, err := service.CreateSession(
		ctx,
		"user-a",
		assistant.CreateSessionInput{ClientRequestID: "session-intent"},
	)
	if err != nil {
		t.Fatalf("create session with request identity: %v", err)
	}
	_, err = service.CreateTurn(
		ctx,
		"user-a",
		session.SessionID,
		assistant.CreateTurnInput{
			Input: assistant.AssistantTurnInput{Text: "hello"},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("empty run clientRequestId error = %v", err)
	}
}
