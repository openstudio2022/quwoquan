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

// recordingBulk captures backfill writes through the BulkIndexer contract.
type recordingBulk struct {
	ensured    bool
	events     []es.ChangeEvent
	failEnsure bool
	failBulk   bool
	bulkCalls  int
}

func (b *recordingBulk) EnsureIndex(_ context.Context) error {
	if b.failEnsure {
		return errors.New("ensure failed")
	}
	b.ensured = true
	return nil
}

func (b *recordingBulk) Bulk(_ context.Context, _ string, events []es.ChangeEvent) error {
	if b.failBulk {
		return errors.New("bulk failed")
	}
	b.bulkCalls++
	b.events = append(b.events, events...)
	return nil
}

func mkPost(id, status, visibility string) postmodel.Post {
	return postmodel.Post{
		ID: id, Title: id, ContentType: "article",
		Status: status, Visibility: visibility, ModerationStatus: "approved", AuthorId: "u1",
	}
}

func TestBackfillIndexesEligibleOnly(t *testing.T) {
	reader := fakeReader{all: []postmodel.Post{
		mkPost("post_pub", "published", "public"),
		mkPost("post_draft", "draft", "public"),
		mkPost("post_priv", "published", "private"),
		mkPost("post_pub2", "published", "public"),
	}}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, reader, 0)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if !bulk.ensured {
		t.Fatalf("backfill must ensure the index first")
	}
	if report.TotalPosts != 4 ||
		report.IndexedPosts != 2 ||
		report.DeletedPosts != 2 {
		t.Fatalf("unexpected report: %#v", report)
	}
	if len(bulk.events) != 4 {
		t.Fatalf("expected 4 reconcile events, got %d", len(bulk.events))
	}
	gotIDs := map[string]bool{}
	for _, ev := range bulk.events {
		gotIDs[string(ev.Op)+":"+ev.Doc.ObjectID] = true
	}
	if !gotIDs["upsert:post_pub"] || !gotIDs["upsert:post_pub2"] {
		t.Fatalf("eligible posts missing from backfill: %#v", gotIDs)
	}
	if !gotIDs["delete:post_draft"] || !gotIDs["delete:post_priv"] {
		t.Fatalf("ineligible posts were not deleted: %#v", gotIDs)
	}
}

func TestBackfillBatches(t *testing.T) {
	var posts []postmodel.Post
	for i := 0; i < 5; i++ {
		posts = append(posts, mkPost(fmt.Sprintf("p%d", i), "published", "public"))
	}
	reader := fakeReader{all: posts}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, reader, 2)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if report.IndexedPosts != 5 {
		t.Fatalf("expected 5 indexed, got %d", report.IndexedPosts)
	}
	if bulk.bulkCalls != 3 { // 2 + 2 + 1
		t.Fatalf("expected 3 bulk round trips for batchSize=2, got %d", bulk.bulkCalls)
	}
	if report.BatchesPushed != 3 {
		t.Fatalf("expected report.BatchesPushed=3, got %d", report.BatchesPushed)
	}
}

func TestBackfillEnsureIndexFailurePropagates(t *testing.T) {
	reader := fakeReader{all: []postmodel.Post{mkPost("post_pub", "published", "public")}}
	bulk := &recordingBulk{failEnsure: true}

	if _, err := Backfill(context.Background(), bulk, reader, 0); err == nil {
		t.Fatalf("expected EnsureIndex failure to propagate")
	}
	if len(bulk.events) != 0 {
		t.Fatalf("no docs should be written when EnsureIndex fails: %#v", bulk.events)
	}
}

func TestBackfillListFailurePropagates(t *testing.T) {
	bulk := &recordingBulk{}
	if _, err := Backfill(context.Background(), bulk, fakeReader{listErr: errors.New("malformed primary key")}, 0); err == nil {
		t.Fatal("expected list failure to stop search backfill")
	}
	if len(bulk.events) != 0 {
		t.Fatalf("list failure must not write index documents: %#v", bulk.events)
	}
}

func TestBackfillMissingInputsFailFast(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, fakeReader{}, 0); err == nil {
		t.Fatal("nil indexer must fail")
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, nil, 0); err == nil {
		t.Fatal("nil reader must fail")
	}
}
