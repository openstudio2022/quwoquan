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

// TestAssistantSessionStoreFailClosed 锁定：Session store 未装配时全部读写
// fail-closed，禁止回退进程内 map。Run storage 由 AssistantRun 对象测试证明。
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
}

func TestAssistantSessionRequiresStableClientRequestID(t *testing.T) {
	t.Parallel()
	service := NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
		WithSessionStore(persistence.NewMemorySessionStore()),
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

}
