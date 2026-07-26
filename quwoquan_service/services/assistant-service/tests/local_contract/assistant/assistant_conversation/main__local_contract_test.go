package local_contract

import (
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

// TestMigratedMain exercises the command's real application composition through public ports.
func TestMigratedMainApplicationComposition(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	if service == nil {
		t.Fatal("assistant application composition returned nil")
	}
}
