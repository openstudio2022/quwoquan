// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package api_integration_test

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
)

func TestRetiredMediaProcessingDeadLetterIndexesMigrateWithoutDeletingFacts(
	t *testing.T,
) {
	runtime, err := testinfra.StartRealMongo(
		context.Background(),
		"media_processing_dead_letter_index_migration",
	)
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	ctx := context.Background()
	collection := runtime.Database.Collection("media_processing_dead_letters")
	if _, err := collection.InsertOne(ctx, bson.M{
		"_id":           "media-processing:evt-retained",
		"consumer":      "media-processing",
		"aggregateId":   "asset-retained",
		"quarantinedAt": "2030-01-01T00:00:00Z",
	}); err != nil {
		t.Fatalf("insert retained dead letter: %v", err)
	}
	if _, err := collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "consumer", Value: 1}, {Key: "quarantinedAt", Value: -1}},
			Options: options.Index().SetName(
				"idx_media_processing_dead_letters_consumer_time",
			),
		},
		{
			Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "quarantinedAt", Value: -1}},
			Options: options.Index().SetName(
				"idx_media_processing_dead_letters_aggregate_time",
			),
		},
	}); err != nil {
		t.Fatalf("create retired indexes: %v", err)
	}

	store := mediaassetpersistence.NewMongoMediaStore(runtime.Database)
	if _, err := store.MigrateRetiredProcessingDeadLetterIndexes(ctx, 0); err == nil {
		t.Fatal("migration with stale expected count must fail before dropping indexes")
	}
	assertProcessingDeadLetterIndexes(t, ctx, collection, map[string]bool{
		"_id_": true,
		"idx_media_processing_dead_letters_aggregate_time": true,
		"idx_media_processing_dead_letters_consumer_time":  true,
	})

	result, err := store.MigrateRetiredProcessingDeadLetterIndexes(ctx, 2)
	if err != nil {
		t.Fatalf("migrate retired indexes: %v", err)
	}
	if got, want := result.DroppedIndexes, []string{
		"idx_media_processing_dead_letters_aggregate_time",
		"idx_media_processing_dead_letters_consumer_time",
	}; !equalStrings(got, want) {
		t.Fatalf("dropped indexes=%v want=%v", got, want)
	}
	assertProcessingDeadLetterIndexes(t, ctx, collection, map[string]bool{"_id_": true})

	count, err := collection.CountDocuments(
		ctx,
		bson.M{"_id": "media-processing:evt-retained"},
	)
	if err != nil || count != 1 {
		t.Fatalf("retained dead-letter count=%d err=%v", count, err)
	}
	replay, err := store.MigrateRetiredProcessingDeadLetterIndexes(ctx, 0)
	if err != nil {
		t.Fatalf("replay retired-index migration: %v", err)
	}
	if len(replay.DroppedIndexes) != 0 {
		t.Fatalf("replayed migration dropped indexes again: %v", replay.DroppedIndexes)
	}
}

func assertProcessingDeadLetterIndexes(
	t *testing.T,
	ctx context.Context,
	collection *mongo.Collection,
	want map[string]bool,
) {
	t.Helper()
	specifications, err := collection.Indexes().ListSpecifications(ctx)
	if err != nil {
		t.Fatalf("list dead-letter indexes: %v", err)
	}
	got := make(map[string]bool, len(specifications))
	for _, specification := range specifications {
		got[specification.Name] = true
	}
	if len(got) != len(want) {
		t.Fatalf("dead-letter indexes=%v want=%v", got, want)
	}
	for name := range want {
		if !got[name] {
			t.Fatalf("dead-letter index %q missing: %v", name, got)
		}
	}
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
