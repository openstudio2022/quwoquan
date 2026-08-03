package deleted_post_tombstone_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
	tombstonepersistence "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/infrastructure/persistence"
)

func TestMongoStoreParticipatesInCallerTransactionAndDeduplicatesPostIdentity(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "deleted_post_tombstone")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := tombstonepersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure DeletedPostTombstone indexes: %v", err)
	}
	deletedAt := time.Date(2026, 8, 2, 9, 10, 0, 0, time.UTC)
	tombstone := tombstonemodel.Tombstone{
		PostID:    "post-tombstone",
		AuthorID:  "author-tombstone",
		Reason:    "author_delete",
		DeletedAt: deletedAt,
		ExpireAt:  deletedAt.Add(30 * 24 * time.Hour),
	}

	session, err := runtime.Client.StartSession()
	if err != nil {
		t.Fatalf("start Mongo session: %v", err)
	}
	defer session.EndSession(context.Background())
	rollback := errors.New("force caller transaction rollback")
	_, err = session.WithTransaction(context.Background(), func(txCtx context.Context) (any, error) {
		if _, appendErr := store.AppendIfAbsent(txCtx, tombstone); appendErr != nil {
			return nil, appendErr
		}
		return nil, rollback
	})
	if !errors.Is(err, rollback) {
		t.Fatalf("transaction rollback error=%v", err)
	}
	if count, countErr := runtime.Database.Collection("deleted_post_tombstones").CountDocuments(
		context.Background(), bson.M{},
	); countErr != nil || count != 0 {
		t.Fatalf("rolled back tombstone count=%d err=%v", count, countErr)
	}

	inserted, err := store.AppendIfAbsent(context.Background(), tombstone)
	if err != nil || !inserted {
		t.Fatalf("append tombstone inserted=%v err=%v", inserted, err)
	}
	inserted, err = store.AppendIfAbsent(context.Background(), tombstone)
	if err != nil || inserted {
		t.Fatalf("replay tombstone inserted=%v err=%v", inserted, err)
	}
	found, exists, err := store.Find(context.Background(), tombstone.PostID)
	if err != nil || !exists || found.PostID != tombstone.PostID || found.ExpireAt.IsZero() {
		t.Fatalf("find tombstone found=%#v exists=%v err=%v", found, exists, err)
	}
}
