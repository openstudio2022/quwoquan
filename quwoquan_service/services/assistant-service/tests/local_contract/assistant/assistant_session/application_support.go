package local_contract

import (
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

func assertAssistantApplicationPort(t *testing.T) {
	t.Helper()
	service := orchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
	)
	if service == nil {
		t.Fatal("assistant application composition returned nil")
	}
}
