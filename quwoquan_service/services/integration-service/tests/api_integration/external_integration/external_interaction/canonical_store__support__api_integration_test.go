package api_integration

import (
	"context"
	"testing"
	"time"

	attemptadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/adapters/inbound/runtime"
	deadletteradapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/adapters/inbound/runtime"
	deadletterpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/infrastructure/persistence"
)

func canonicalMongoExternalStore(t testing.TB) *deadletteradapter.RuntimeStore {
	return canonicalMongoExternalStoreFrom(t, integrationReliableStore)
}

func canonicalMongoExternalStoreFrom(
	t testing.TB,
	delegate attemptadapter.Delegate,
) *deadletteradapter.RuntimeStore {
	t.Helper()
	repository := deadletterpersistence.NewMongoRepository(integrationMongoDB)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := repository.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure external interaction dead-letter indexes: %v", err)
	}
	return deadletteradapter.NewRuntimeStore(
		attemptadapter.NewRuntimeStore(delegate),
		repository,
	)
}
