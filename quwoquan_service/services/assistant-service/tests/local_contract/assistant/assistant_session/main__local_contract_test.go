package local_contract

import (
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

// TestAssistantSessionMain exercises the real application composition through public ports.
func TestMainApplicationComposition(t *testing.T) {
	service := orchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
	)
	if service == nil {
		t.Fatal("assistant application composition returned nil")
	}
}
