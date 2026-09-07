// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
package searchindex_test

import (
	"context"
	"errors"
	"fmt"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
	"testing"

	"quwoquan_service/runtime/search/es"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
)

// recordingIndexer captures backfill writes through the VersionedIndexer
// contract and enforces the provider's strictly-newer fence in memory.
type recordingIndexer struct {
	events    []es.VersionedChangeEvent
	versions  map[string]int64
	failApply bool
}

func (b *recordingIndexer) ApplyVersioned(_ context.Context, event es.VersionedChangeEvent) (bool, error) {
	if b.failApply {
		return false, errors.New("versioned write failed")
	}
	if event.SourceVersion <= 0 {
		return false, errors.New("sourceVersion must be positive")
	}
	if b.versions == nil {
		b.versions = map[string]int64{}
	}
	b.events = append(b.events, event)
	id := es.IndexID(event.Doc)
	if b.versions[id] >= event.SourceVersion {
		return false, nil
	}
	b.versions[id] = event.SourceVersion
	return true, nil
}

func mkPost(id, status, visibility string) postmodel.Post {
	return postmodel.Post{
		ID: id, Version: 2, Title: id, ContentType: "article",
		Status: status, Visibility: visibility, ModerationStatus: "approved", AuthorId: "u1",
	}
}

func TestBackfillIndexesEligibleAndTombstonesRestUnderPostVersion(t *testing.T) {
	reader := fakeReader{all: []postmodel.Post{
		mkPost("post_pub", "published", "public"),
		mkPost("post_draft", "draft", "public"),
		mkPost("post_priv", "published", "private"),
		mkPost("post_pub2", "published", "public"),
	}}
	indexer := &recordingIndexer{}

	report, err := Backfill(context.Background(), indexer, reader)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if report.TotalPosts != 4 ||
		report.IndexedPosts != 2 ||
		report.TombstonedPosts != 2 ||
		report.StaleWrites != 0 {
		t.Fatalf("unexpected report: %#v", report)
	}
	if len(indexer.events) != 4 {
		t.Fatalf("expected 4 reconcile events, got %d", len(indexer.events))
	}
	gotIDs := map[string]bool{}
	for _, ev := range indexer.events {
		if ev.SourceVersion != 2 {
			t.Fatalf("every backfill write must carry the Post's own version: %#v", ev)
		}
		gotIDs[string(ev.Op)+":"+ev.Doc.ObjectID] = true
	}
	if !gotIDs["upsert:post_pub"] || !gotIDs["upsert:post_pub2"] {
		t.Fatalf("eligible posts missing from backfill: %#v", gotIDs)
	}
	if !gotIDs["delete:post_draft"] || !gotIDs["delete:post_priv"] {
		t.Fatalf("ineligible posts were not tombstoned: %#v", gotIDs)
	}
}

func TestBackfillReplayIsStaleNotFailure(t *testing.T) {
	var posts []postmodel.Post
	for i := 0; i < 5; i++ {
		posts = append(posts, mkPost(fmt.Sprintf("p%d", i), "published", "public"))
	}
	reader := fakeReader{all: posts}
	indexer := &recordingIndexer{}

	first, err := Backfill(context.Background(), indexer, reader)
	if err != nil || first.IndexedPosts != 5 || first.StaleWrites != 0 {
		t.Fatalf("first backfill report=%#v err=%v", first, err)
	}
	second, err := Backfill(context.Background(), indexer, reader)
	if err != nil {
		t.Fatalf("replayed backfill must not fail: %v", err)
	}
	if second.IndexedPosts != 5 || second.StaleWrites != 5 {
		t.Fatalf("replayed backfill must report every write as stale, got %#v", second)
	}
}

func TestBackfillRejectsPostWithoutVersion(t *testing.T) {
	post := mkPost("post_unversioned", "published", "public")
	post.Version = 0
	indexer := &recordingIndexer{}
	if _, err := Backfill(context.Background(), indexer, fakeReader{all: []postmodel.Post{post}}); err == nil {
		t.Fatal("a Post without a positive version must stop the backfill")
	}
	if len(indexer.events) != 0 {
		t.Fatalf("no unversioned document may be written: %#v", indexer.events)
	}
}

func TestBackfillWriteFailurePropagates(t *testing.T) {
	reader := fakeReader{all: []postmodel.Post{mkPost("post_pub", "published", "public")}}
	indexer := &recordingIndexer{failApply: true}

	if _, err := Backfill(context.Background(), indexer, reader); err == nil {
		t.Fatalf("expected versioned write failure to propagate")
	}
}

func TestBackfillListFailurePropagates(t *testing.T) {
	indexer := &recordingIndexer{}
	if _, err := Backfill(context.Background(), indexer, fakeReader{listErr: errors.New("malformed primary key")}); err == nil {
		t.Fatal("expected list failure to stop search backfill")
	}
	if len(indexer.events) != 0 {
		t.Fatalf("list failure must not write index documents: %#v", indexer.events)
	}
}

func TestBackfillMissingInputsFailFast(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, fakeReader{}); err == nil {
		t.Fatal("nil indexer must fail")
	}
	if _, err := Backfill(context.Background(), &recordingIndexer{}, nil); err == nil {
		t.Fatal("nil reader must fail")
	}
}
