package local_contract

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

func assertMigratedAssistantApplicationPort(t *testing.T) {
	t.Helper()
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	items, err := service.ListConsents(context.Background(), "assistant-local-contract-user")
	if err != nil || len(items) != 0 {
		t.Fatalf("ListConsents() items=%#v err=%v", items, err)
	}
}
