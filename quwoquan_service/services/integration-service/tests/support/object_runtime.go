package support

import (
	"context"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/reliabletaskmongo"
	"quwoquan_service/internal/platform/testinfra"
	attemptadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/adapters/inbound/runtime"
	deadletteradapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/adapters/inbound/runtime"
	deadletterpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/infrastructure/persistence"
)

type MongoRuntime struct {
	Context  context.Context
	Database *mongo.Database
	Reliable *reliabletaskmongo.Store
	runtime  *testinfra.RealMongo
}

func (runtime *MongoRuntime) CanonicalExternalStore(t testing.TB) *deadletteradapter.RuntimeStore {
	t.Helper()
	repository := deadletterpersistence.NewMongoRepository(runtime.Database)
	if err := repository.EnsureIndexes(runtime.Context); err != nil {
		t.Fatalf("ensure external interaction dead-letter indexes: %v", err)
	}
	return deadletteradapter.NewRuntimeStore(
		attemptadapter.NewRuntimeStore(runtime.Reliable),
		repository,
	)
}

func WithIntegrationMongo(t testing.TB, test func(*MongoRuntime)) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	realMongo, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("integration_object_%d", time.Now().UnixNano()),
	)
	if err != nil {
		cancel()
		t.Fatalf("start real Integration MongoDB: %v", err)
	}
	reliable := reliabletaskmongo.NewExternalInteraction(realMongo.Database)
	if err := reliable.EnsureIndexes(ctx); err != nil {
		cancel()
		_ = realMongo.Close(context.Background())
		t.Fatalf("ensure Integration reliable-task indexes: %v", err)
	}
	runtime := &MongoRuntime{
		Context: ctx, Database: realMongo.Database, Reliable: reliable, runtime: realMongo,
	}
	t.Cleanup(func() {
		cancel()
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if closeErr := realMongo.Close(cleanupCtx); closeErr != nil {
			t.Errorf("close Integration MongoDB: %v", closeErr)
		}
	})
	test(runtime)
}

func (runtime *MongoRuntime) ResetExternalInteraction(t testing.TB) {
	t.Helper()
	for _, collection := range []string{
		"reliable_task_outbox",
		"reliable_async_task",
		"external_provider_attempt_ledger",
		"external_interaction_dead_letters",
		"external_interaction_result_outbox",
		"reliable_task_recovery_receipts",
		"otp_code_reference_vault",
		"reliable_task_leases",
	} {
		if _, err := runtime.Database.Collection(collection).DeleteMany(runtime.Context, bson.D{}); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}
