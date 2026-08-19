package api_integration

import (
	"context"
	"reflect"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestPostMongoIndexesIncludeGatheringReferenceReadPath(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	cursor, err := requireMongoDB(t).Collection("posts").Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list Post indexes: %v", err)
	}
	defer cursor.Close(ctx)

	type indexDocument struct {
		Name   string `bson:"name"`
		Key    bson.D `bson:"key"`
		Sparse bool   `bson:"sparse"`
	}
	for cursor.Next(ctx) {
		var index indexDocument
		if err := cursor.Decode(&index); err != nil {
			t.Fatalf("decode Post index: %v", err)
		}
		if index.Name != "idx_posts_gathering_ref" {
			continue
		}
		wantKeys := bson.D{
			{Key: "gatheringRef", Value: int32(1)},
			{Key: "publishedAt", Value: int32(-1)},
		}
		if !reflect.DeepEqual(index.Key, wantKeys) {
			t.Fatalf("idx_posts_gathering_ref keys = %#v, want %#v", index.Key, wantKeys)
		}
		if !index.Sparse {
			t.Fatal("idx_posts_gathering_ref must remain sparse for ordinary Posts")
		}
		return
	}
	if err := cursor.Err(); err != nil {
		t.Fatalf("iterate Post indexes: %v", err)
	}
	t.Fatal("idx_posts_gathering_ref was not created by MongoPostStore.EnsureIndexes")
}
