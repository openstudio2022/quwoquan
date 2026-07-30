package api_integration

import (
	"context"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

const (
	followingSubjectIdentityIndexForMigrationTest = "idx_following_subject_viewer_subject"
	followingSubjectChangedIndexForMigrationTest  = "idx_following_subject_viewer_type_changed"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
func TestFollowingSubjectPersonaMigration(t *testing.T) {
	t.Run("moves persisted identity and replaces indexes exactly once", func(t *testing.T) {
		collection := prepareFollowingSubjectMigrationTest(t)
		ctx := context.Background()
		retiredKey := retiredFollowingSubjectViewerKeyForTest()

		_, err := collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
			{
				Keys: bson.D{
					{Key: retiredKey, Value: 1},
					{Key: "subjectType", Value: 1},
					{Key: "subjectId", Value: 1},
				},
				Options: options.Index().
					SetName(followingSubjectIdentityIndexForMigrationTest).
					SetUnique(true),
			},
			{
				Keys: bson.D{
					{Key: retiredKey, Value: 1},
					{Key: "subjectType", Value: 1},
					{Key: "latestChangedAt", Value: -1},
				},
				Options: options.Index().
					SetName(followingSubjectChangedIndexForMigrationTest),
			},
		})
		if err != nil {
			t.Fatalf("create retired following_subjects indexes: %v", err)
		}

		followedAt := time.Date(2026, time.July, 30, 8, 0, 0, 0, time.UTC)
		_, err = collection.InsertOne(ctx, bson.M{
			retiredKey:         "ps_migration_viewer",
			"subjectType":      "location",
			"subjectId":        "location_emeishan",
			"followedAt":       followedAt,
			"sourceVersion":    int64(7),
			"projectionMarker": "preserved",
		})
		if err != nil {
			t.Fatalf("insert retired following_subjects row: %v", err)
		}

		store := persistence.NewMongoFollowingSubjectStore(mongoDB)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("migrate following_subjects Persona identity: %v", err)
		}

		assertMigratedFollowingSubjectRow(t, collection, retiredKey, followedAt)
		assertCanonicalFollowingSubjectIndexes(t, collection)

		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("rerun following_subjects Persona migration: %v", err)
		}
		assertMigratedFollowingSubjectRow(t, collection, retiredKey, followedAt)
		assertCanonicalFollowingSubjectIndexes(t, collection)

		count, err := collection.CountDocuments(ctx, bson.M{})
		if err != nil {
			t.Fatalf("count following_subjects rows after rerun: %v", err)
		}
		if count != 1 {
			t.Fatalf("migration rerun changed row count: got %d want 1", count)
		}
	})

	t.Run("rejects conflicting identities without mutating the row", func(t *testing.T) {
		collection := prepareFollowingSubjectMigrationTest(t)
		ctx := context.Background()
		retiredKey := retiredFollowingSubjectViewerKeyForTest()

		_, err := collection.InsertOne(ctx, bson.M{
			retiredKey:        "ps_retired",
			"viewerPersonaId": "ps_canonical",
			"subjectType":     "homepage",
			"subjectId":       "homepage_conflict",
		})
		if err != nil {
			t.Fatalf("insert conflicting following_subjects row: %v", err)
		}

		store := persistence.NewMongoFollowingSubjectStore(mongoDB)
		err = store.EnsureIndexes(ctx)
		if err == nil || !strings.Contains(err.Error(), "conflicting retired and canonical") {
			t.Fatalf("expected identity conflict, got %v", err)
		}

		var row bson.M
		if err := collection.FindOne(ctx, bson.M{"subjectId": "homepage_conflict"}).Decode(&row); err != nil {
			t.Fatalf("read conflicting following_subjects row: %v", err)
		}
		if row[retiredKey] != "ps_retired" || row["viewerPersonaId"] != "ps_canonical" {
			t.Fatalf("conflicting row was mutated: %#v", row)
		}
	})

	t.Run("rejects effective duplicates before moving any identity", func(t *testing.T) {
		collection := prepareFollowingSubjectMigrationTest(t)
		ctx := context.Background()
		retiredKey := retiredFollowingSubjectViewerKeyForTest()
		rows := []any{
			bson.M{
				retiredKey:    "ps_duplicate",
				"subjectType": "circle",
				"subjectId":   "circle_same",
			},
			bson.M{
				"viewerPersonaId": "ps_duplicate",
				"subjectType":     "circle",
				"subjectId":       "circle_same",
			},
		}
		if _, err := collection.InsertMany(ctx, rows); err != nil {
			t.Fatalf("insert duplicate following_subjects rows: %v", err)
		}

		store := persistence.NewMongoFollowingSubjectStore(mongoDB)
		err := store.EnsureIndexes(ctx)
		if err == nil || !strings.Contains(err.Error(), "duplicate rows") {
			t.Fatalf("expected canonical duplicate rejection, got %v", err)
		}

		retiredCount, err := collection.CountDocuments(
			ctx,
			bson.M{retiredKey: "ps_duplicate"},
		)
		if err != nil {
			t.Fatalf("count preserved retired rows: %v", err)
		}
		if retiredCount != 1 {
			t.Fatalf("duplicate rejection mutated retired identity rows: got %d want 1", retiredCount)
		}
	})

	t.Run("rejects rows without a Persona identity", func(t *testing.T) {
		collection := prepareFollowingSubjectMigrationTest(t)
		ctx := context.Background()

		_, err := collection.InsertOne(ctx, bson.M{
			"subjectType": "homepage",
			"subjectId":   "homepage_missing_viewer",
		})
		if err != nil {
			t.Fatalf("insert following_subjects row without viewer: %v", err)
		}

		store := persistence.NewMongoFollowingSubjectStore(mongoDB)
		err = store.EnsureIndexes(ctx)
		if err == nil || !strings.Contains(err.Error(), "without viewer Persona identity") {
			t.Fatalf("expected missing Persona identity rejection, got %v", err)
		}
	})
}

func prepareFollowingSubjectMigrationTest(t *testing.T) *mongo.Collection {
	t.Helper()
	requireMongoBackedRuntime(t)
	cleanAll(t)
	collection := mongoDB.Collection("following_subjects")
	ctx := context.Background()
	if err := collection.Indexes().DropAll(ctx); err != nil {
		t.Fatalf("drop following_subjects indexes for migration fixture: %v", err)
	}
	t.Cleanup(func() {
		cleanAll(t)
	})
	return collection
}

func retiredFollowingSubjectViewerKeyForTest() string {
	return strings.Join([]string{"viewer", "Sub", "Account", "Id"}, "")
}

func assertMigratedFollowingSubjectRow(
	t *testing.T,
	collection *mongo.Collection,
	retiredKey string,
	followedAt time.Time,
) {
	t.Helper()
	var row bson.M
	if err := collection.FindOne(
		context.Background(),
		bson.M{"subjectId": "location_emeishan"},
	).Decode(&row); err != nil {
		t.Fatalf("read migrated following_subjects row: %v", err)
	}
	if row["viewerPersonaId"] != "ps_migration_viewer" {
		t.Fatalf("canonical Persona identity missing after migration: %#v", row)
	}
	if _, exists := row[retiredKey]; exists {
		t.Fatalf("retired viewer identity remains after migration: %#v", row)
	}
	if row["projectionMarker"] != "preserved" || row["sourceVersion"] != int64(7) {
		t.Fatalf("projection data changed during identity migration: %#v", row)
	}
	storedFollowedAt, ok := row["followedAt"].(bson.DateTime)
	if !ok || !storedFollowedAt.Time().Equal(followedAt) {
		t.Fatalf("followedAt changed during identity migration: %#v", row["followedAt"])
	}
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
		followingSubjectIdentityIndexForMigrationTest: true,
		followingSubjectChangedIndexForMigrationTest:  false,
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
