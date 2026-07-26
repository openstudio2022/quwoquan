package local_contract

import (
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

// TestMigratedCommandContract exercises the command's real application composition through public ports.
func TestMigratedCommandContractApplicationComposition(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	if service == nil {
		t.Fatal("assistant application composition returned nil")
	}
}
