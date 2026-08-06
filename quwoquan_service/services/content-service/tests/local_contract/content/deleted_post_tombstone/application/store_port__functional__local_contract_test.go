// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-002
// readiness_case: append-deleted-post-tombstone-local
package application_test

import (
	"context"
	"testing"
	"time"

	tombstonepost "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/adapters/inbound/post"
	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
)

func TestDeletedPostTombstonePortAppendsAndReadsOneImmutableFact(t *testing.T) {
	t.Parallel()
	deletedAt := time.Now().UTC().Truncate(time.Millisecond)
	fact := tombstonemodel.Tombstone{
		PostID:    "post-deleted-001",
		AuthorID:  "author-001",
		Reason:    "author_delete",
		DeletedAt: deletedAt,
		ExpireAt:  deletedAt.Add(30 * 24 * time.Hour),
	}
	store := &recordingTombstoneStore{facts: map[string]tombstonemodel.Tombstone{}}
	port := tombstonepost.NewStorePort(store)

	inserted, err := port.AppendIfAbsent(context.Background(), fact)
	if err != nil || !inserted {
		t.Fatalf("append tombstone inserted=%v err=%v", inserted, err)
	}
	replayed, err := port.AppendIfAbsent(context.Background(), fact)
	if err != nil || replayed {
		t.Fatalf("replay tombstone inserted=%v err=%v", replayed, err)
	}
	loaded, found, err := port.Find(context.Background(), fact.PostID)
	if err != nil || !found || loaded != fact {
		t.Fatalf("read tombstone found=%v fact=%+v err=%v", found, loaded, err)
	}
	if store.appendCalls != 2 || store.findCalls != 1 || len(store.facts) != 1 {
		t.Fatalf("store calls append=%d find=%d facts=%d", store.appendCalls, store.findCalls, len(store.facts))
	}
}

type recordingTombstoneStore struct {
	facts       map[string]tombstonemodel.Tombstone
	appendCalls int
	findCalls   int
}

func (*recordingTombstoneStore) EnsureIndexes(context.Context) error { return nil }

func (store *recordingTombstoneStore) AppendIfAbsent(
	_ context.Context,
	fact tombstonemodel.Tombstone,
) (bool, error) {
	store.appendCalls++
	if _, exists := store.facts[fact.PostID]; exists {
		return false, nil
	}
	store.facts[fact.PostID] = fact
	return true, nil
}

func (store *recordingTombstoneStore) Find(
	_ context.Context,
	postID string,
) (tombstonemodel.Tombstone, bool, error) {
	store.findCalls++
	fact, found := store.facts[postID]
	return fact, found, nil
}
