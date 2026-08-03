package local_contract

import (
	"quwoquan_service/runtime/reliabletask"
	attemptadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/adapters/inbound/runtime"
	deadletteradapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/adapters/inbound/runtime"
	deadletterpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/infrastructure/persistence"
)

func canonicalMemoryExternalStore(
	store *reliabletask.MemoryStore,
) *deadletteradapter.RuntimeStore {
	return deadletteradapter.NewRuntimeStore(
		attemptadapter.NewRuntimeStore(store),
		deadletterpersistence.NewMemoryRepository(),
	)
}
