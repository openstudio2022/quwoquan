// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package api_integration

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func TestMongoActiveSupplyReaderUsesEnvironmentScopedActiveRelease(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	const environment = "api-integration-active-supply"
	collection := db.Collection("data_release_state")
	if _, err := collection.DeleteMany(ctx, bson.M{"environment": environment}); err != nil {
		t.Fatalf("delete release state: %v", err)
	}
	t.Cleanup(func() {
		_, _ = collection.DeleteMany(context.Background(), bson.M{"environment": environment})
	})

	reader := persistence.NewMongoActiveSupplyReader(db, environment)
	active, err := reader.HasActiveSupply(ctx)
	if err != nil {
		t.Fatalf("HasActiveSupply missing: %v", err)
	}
	if active {
		t.Fatal("environment without data_release_state must not report active supply")
	}

	if _, err := collection.InsertMany(ctx, []any{
		bson.M{
			"environment": environment, "sourceOwner": "inactive",
			"status": "inactive", "activeReleaseId": "rel_inactive",
		},
		bson.M{
			"environment": environment, "sourceOwner": "qwq_data",
			"status": "active", "activeReleaseId": "rel_active",
		},
	}); err != nil {
		t.Fatalf("insert release states: %v", err)
	}

	active, err = reader.HasActiveSupply(ctx)
	if err != nil {
		t.Fatalf("HasActiveSupply active: %v", err)
	}
	if !active {
		t.Fatal("environment-scoped active release must report available supply")
	}
}
