package api_integration

import (
	"context"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

const (
	followingSubjectIdentityIndexForCanonicalTest = "idx_following_subject_viewer_subject"
	followingSubjectChangedIndexForCanonicalTest  = "idx_following_subject_viewer_type_changed"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
func TestFollowingSubjectCanonicalPersonaIdentity(t *testing.T) {
	t.Run("accepts canonical rows and creates canonical indexes idempotently", func(t *testing.T) {
		collection := prepareFollowingSubjectCanonicalTest(t)
		ctx := context.Background()
		if _, err := collection.InsertOne(ctx, bson.M{
			"viewerPersonaId": "ps_canonical",
			"subjectType":     "location",
			"subjectId":       "location_emeishan",
		}); err != nil {
			t.Fatalf("insert canonical following_subjects row: %v", err)
		}

		store := persistence.NewMongoFollowingSubjectStore(mongoDB)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("create canonical following_subjects indexes: %v", err)
		}
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("recheck canonical following_subjects indexes: %v", err)
		}
		assertCanonicalFollowingSubjectIndexes(t, collection)
	})

	t.Run("rejects non-canonical rows without mutating them", func(t *testing.T) {
		collection := prepareFollowingSubjectCanonicalTest(t)
		ctx := context.Background()
		if _, err := collection.InsertOne(ctx, bson.M{
			"subjectType": "homepage",
			"subjectId":   "homepage_missing_viewer",
		}); err != nil {
			t.Fatalf("insert non-canonical following_subjects row: %v", err)
		}

		store := persistence.NewMongoFollowingSubjectStore(mongoDB)
		err := store.EnsureIndexes(ctx)
		if err == nil || !strings.Contains(err.Error(), "non-canonical viewer Persona identity") {
			t.Fatalf("expected canonical identity rejection, got %v", err)
		}
		var row bson.M
		if err := collection.FindOne(ctx, bson.M{
			"subjectId": "homepage_missing_viewer",
		}).Decode(&row); err != nil {
			t.Fatalf("read rejected following_subjects row: %v", err)
		}
		if _, exists := row["viewerPersonaId"]; exists {
			t.Fatalf("rejected row was mutated: %#v", row)
		}
	})
}

func prepareFollowingSubjectCanonicalTest(t *testing.T) *mongo.Collection {
	t.Helper()
	requireMongoBackedRuntime(t)
	cleanAll(t)
	collection := mongoDB.Collection("following_subjects")
	ctx := context.Background()
	if err := collection.Indexes().DropAll(ctx); err != nil {
		t.Fatalf("drop following_subjects indexes for canonical fixture: %v", err)
	}
	t.Cleanup(func() { cleanAll(t) })
	return collection
}

func assertCanonicalFollowingSubjectIndexes(
	t *testing.T,
	collection *mongo.Collection,
) {
	t.Helper()
	ctx := context.Background()
	cursor, err := collection.Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list following_subjects indexes: %v", err)
	}
	defer cursor.Close(ctx)

	wantUnique := map[string]bool{
		followingSubjectIdentityIndexForCanonicalTest: true,
		followingSubjectChangedIndexForCanonicalTest:  false,
	}
	found := map[string]bool{}
	for cursor.Next(ctx) {
		var index struct {
			Name   string `bson:"name"`
			Key    bson.D `bson:"key"`
			Unique bool   `bson:"unique"`
		}
		if err := cursor.Decode(&index); err != nil {
			t.Fatalf("decode following_subjects index: %v", err)
		}
		expectedUnique, expected := wantUnique[index.Name]
		if !expected {
			continue
		}
		if len(index.Key) == 0 || index.Key[0].Key != "viewerPersonaId" {
			t.Fatalf("index %s does not use canonical Persona identity: %#v", index.Name, index.Key)
		}
		if index.Unique != expectedUnique {
			t.Fatalf("index %s uniqueness=%v want %v", index.Name, index.Unique, expectedUnique)
		}
		found[index.Name] = true
	}
	if err := cursor.Err(); err != nil {
		t.Fatalf("iterate following_subjects indexes: %v", err)
	}
	for name := range wantUnique {
		if !found[name] {
			t.Fatalf("canonical following_subjects index %s is missing", name)
		}
	}
}
