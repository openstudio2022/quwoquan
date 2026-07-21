package api_integration

import (
	"context"
	"reflect"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

type circleDiscoveryIndexDocument struct {
	Name string `bson:"name"`
	Key  bson.D `bson:"key"`
}

func TestCircleDiscoveryIndexSetupKeepsLegacyPostIndexCompatible(t *testing.T) {
	ctx := context.Background()
	database := mongoClient.Database("circle_discovery_index_upgrade_contract")
	t.Cleanup(func() {
		_ = database.Drop(ctx)
	})

	legacyPostIndex := bson.D{
		{Key: "circleIds", Value: int32(1)},
		{Key: "status", Value: int32(1)},
		{Key: "publishedAt", Value: int32(-1)},
		{Key: "_id", Value: int32(-1)},
	}
	if _, err := database.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    legacyPostIndex,
		Options: options.Index().SetName("idx_circle_discovery_posts"),
	}); err != nil {
		t.Fatalf("prepare legacy circle discovery post index: %v", err)
	}

	reader := persistence.NewMongoCircleDiscoveryFeedReader(database)
	if err := reader.EnsureIndexes(ctx); err != nil {
		t.Fatalf("discovery index setup must tolerate the legacy post index: %v", err)
	}

	cursor, err := database.Collection("posts").Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list post indexes: %v", err)
	}
	defer cursor.Close(ctx)

	var indexes []circleDiscoveryIndexDocument
	if err := cursor.All(ctx, &indexes); err != nil {
		t.Fatalf("decode post indexes: %v", err)
	}
	for _, index := range indexes {
		if index.Name == "idx_circle_discovery_posts" {
			if !reflect.DeepEqual(index.Key, legacyPostIndex) {
				t.Fatalf("legacy post index was mutated: %#v", index.Key)
			}
			return
		}
	}
	t.Fatal("legacy circle discovery post index was removed")
}
