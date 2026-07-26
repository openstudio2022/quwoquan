package placeindex_test

import (
	"context"
	"errors"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	"testing"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
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
	bound.PrimaryHomepageId = "homepage_1" // single source: carried by entity.homepage
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

func TestBackfillListFailurePropagates(t *testing.T) {
	bulk := &recordingBulk{}
	if _, err := Backfill(context.Background(), bulk, fakeReader{listErr: errors.New("malformed primary key")}, NewInMemoryPlaceStore(), 0); err == nil {
		t.Fatal("expected list failure to stop place backfill")
	}
	if len(bulk.events) != 0 {
		t.Fatalf("list failure must not write index documents: %#v", bulk.events)
	}
}

func TestBackfillDeletesPlacesWithoutLiveReferences(t *testing.T) {
	store := NewInMemoryPlaceStore()
	if err := store.Upsert(context.Background(), searchprojection.PlaceSnapshot{
		PlaceID:    "place:obsolete",
		Name:       "旧地点",
		RefPostIDs: []string{"deleted-post"},
	}); err != nil {
		t.Fatal(err)
	}
	bulk := &recordingBulk{}
	report, err := Backfill(
		context.Background(),
		bulk,
		fakeReader{},
		store,
		10,
	)
	if err != nil {
		t.Fatal(err)
	}
	if report.DeletedPlaces != 1 ||
		len(bulk.events) != 1 ||
		bulk.events[0].Op != es.OpDelete ||
		bulk.events[0].Doc.ObjectID != "place:obsolete" {
		t.Fatalf("obsolete place was not reconciled: report=%#v events=%#v", report, bulk.events)
	}
	places, err := store.ListAll(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(places) != 0 {
		t.Fatalf("obsolete materialized snapshot remains: %#v", places)
	}
}

func TestBackfillMissingInputsFailFast(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, fakeReader{}, NewInMemoryPlaceStore(), 0); err == nil {
		t.Fatal("nil indexer must fail")
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, nil, NewInMemoryPlaceStore(), 0); err == nil {
		t.Fatal("nil reader must fail")
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, fakeReader{}, nil, 0); err == nil {
		t.Fatal("nil store must fail")
	}
}

var _ = postmodel.Post{}
