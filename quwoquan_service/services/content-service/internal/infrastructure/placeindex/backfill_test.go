package placeindex

import (
	"context"
	"errors"
	"testing"

	"quwoquan_service/runtime/search/es"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// recordingBulk captures backfill writes through the BulkIndexer contract.
type recordingBulk struct {
	ensured    bool
	events     []es.ChangeEvent
	failEnsure bool
}

func (b *recordingBulk) EnsureIndex(_ context.Context) error {
	if b.failEnsure {
		return errors.New("ensure failed")
	}
	b.ensured = true
	return nil
}

func (b *recordingBulk) Bulk(_ context.Context, _ string, events []es.ChangeEvent) error {
	b.events = append(b.events, events...)
	return nil
}

func TestBackfillAggregatesAndDedups(t *testing.T) {
	eligibleA1 := placePost("p1", "稻城亚丁")
	eligibleA2 := placePost("p2", "稻城亚丁") // same place as p1
	eligibleB := placePost("p3", "色达")
	bound := placePost("p4", "已绑定地点")
	bound.CanonicalEntityId = "entity_1" // single source: carried by entity.homepage
	draft := placePost("p5", "草稿地点")
	draft.Status = "draft"

	reader := fakeReader{all: []postmodel.Post{eligibleA1, eligibleA2, eligibleB, bound, draft}}
	bulk := &recordingBulk{}
	store := NewInMemoryPlaceStore()

	report, err := Backfill(context.Background(), bulk, reader, store, 0)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if !bulk.ensured {
		t.Fatalf("backfill must ensure the index first")
	}
	if report.TotalPosts != 5 || report.ReferencedPosts != 3 || report.IndexedPlaces != 2 || report.SkippedPosts != 2 {
		t.Fatalf("unexpected report: %#v", report)
	}
	if len(bulk.events) != 2 {
		t.Fatalf("expected 2 deduplicated place docs, got %d", len(bulk.events))
	}
	// The shared place (稻城亚丁) must aggregate both posts into a 2-ref snapshot.
	places, _ := store.PlacesReferencing(context.Background(), "p1")
	if len(places) != 1 || len(places[0].RefPostIDs) != 2 {
		t.Fatalf("shared place must carry 2 references: %#v", places)
	}
	// The bound + draft posts must not have produced any place.
	for _, ev := range bulk.events {
		if ev.Op != es.OpUpsert {
			t.Fatalf("backfill must upsert, got %s", ev.Op)
		}
		if ev.Doc.Title == "已绑定地点" || ev.Doc.Title == "草稿地点" {
			t.Fatalf("ineligible place leaked into backfill: %#v", ev.Doc)
		}
	}
}

func TestBackfillEnsureIndexFailurePropagates(t *testing.T) {
	reader := fakeReader{all: []postmodel.Post{placePost("p1", "稻城亚丁")}}
	bulk := &recordingBulk{failEnsure: true}
	if _, err := Backfill(context.Background(), bulk, reader, NewInMemoryPlaceStore(), 0); err == nil {
		t.Fatalf("expected EnsureIndex failure to propagate")
	}
	if len(bulk.events) != 0 {
		t.Fatalf("no docs should be written when EnsureIndex fails: %#v", bulk.events)
	}
}

func TestBackfillNilInputsNoOp(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, fakeReader{}, NewInMemoryPlaceStore(), 0); err != nil {
		t.Fatalf("nil indexer must be a no-op, got %v", err)
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, nil, NewInMemoryPlaceStore(), 0); err != nil {
		t.Fatalf("nil reader must be a no-op, got %v", err)
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, fakeReader{}, nil, 0); err != nil {
		t.Fatalf("nil store must be a no-op, got %v", err)
	}
}

var _ = postmodel.Post{}
