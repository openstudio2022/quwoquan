// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
package placeindex_test

import (
	"context"
	"errors"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	"testing"

	"quwoquan_service/runtime/search/es"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
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

func TestBackfillAggregatesAndDedups(t *testing.T) {
	eligibleA1 := placePost("p1", "稻城亚丁")
	eligibleA2 := placePost("p2", "稻城亚丁") // same place as p1
	eligibleB := placePost("p3", "色达")
	bound := placePost("p4", "已绑定地点")
	bound.PrimaryHomepageId = "homepage_1" // single source: carried by entity.homepage
	draft := placePost("p5", "草稿地点")
	draft.Status = "draft"

	reader := fakeReader{all: []postmodel.Post{eligibleA1, eligibleA2, eligibleB, bound, draft}}
	indexer := &recordingIndexer{}
	store := NewInMemoryPlaceStore()

	report, err := Backfill(context.Background(), indexer, reader, store)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if report.TotalPosts != 5 || report.ReferencedPosts != 3 || report.IndexedPlaces != 2 || report.SkippedPosts != 2 || report.StaleWrites != 0 {
		t.Fatalf("unexpected report: %#v", report)
	}
	if len(indexer.events) != 2 {
		t.Fatalf("expected 2 deduplicated place docs, got %d", len(indexer.events))
	}
	// The shared place (稻城亚丁) must aggregate both posts into a 2-ref snapshot.
	places, _ := store.PlacesReferencing(context.Background(), "p1")
	if len(places) != 1 || len(places[0].RefPostIDs) != 2 || places[0].Version != 1 {
		t.Fatalf("shared place must carry 2 references at version 1: %#v", places)
	}
	// The bound + draft posts must not have produced any place.
	for _, ev := range indexer.events {
		if ev.Op != es.OpUpsert {
			t.Fatalf("backfill must upsert, got %s", ev.Op)
		}
		if ev.SourceVersion != 1 {
			t.Fatalf("backfill write must carry the stored snapshot version: %#v", ev)
		}
		if ev.Doc.Title == "已绑定地点" || ev.Doc.Title == "草稿地点" {
			t.Fatalf("ineligible place leaked into backfill: %#v", ev.Doc)
		}
	}
}

func TestBackfillRebuildAdvancesVersionSoRebuildNeverRegresses(t *testing.T) {
	reader := fakeReader{all: []postmodel.Post{placePost("p1", "稻城亚丁")}}
	indexer := &recordingIndexer{}
	store := NewInMemoryPlaceStore()
	if _, err := Backfill(context.Background(), indexer, reader, store); err != nil {
		t.Fatal(err)
	}
	report, err := Backfill(context.Background(), indexer, reader, store)
	if err != nil {
		t.Fatal(err)
	}
	if report.IndexedPlaces != 1 || report.StaleWrites != 0 || indexer.events[1].SourceVersion != 2 {
		t.Fatalf("a rebuild must bump the snapshot version and be accepted, report=%#v events=%#v", report, indexer.events)
	}
}

func TestBackfillWriteFailurePropagates(t *testing.T) {
	reader := fakeReader{all: []postmodel.Post{placePost("p1", "稻城亚丁")}}
	indexer := &recordingIndexer{failApply: true}
	if _, err := Backfill(context.Background(), indexer, reader, NewInMemoryPlaceStore()); err == nil {
		t.Fatalf("expected versioned write failure to propagate")
	}
}

func TestBackfillListFailurePropagates(t *testing.T) {
	indexer := &recordingIndexer{}
	if _, err := Backfill(context.Background(), indexer, fakeReader{listErr: errors.New("malformed primary key")}, NewInMemoryPlaceStore()); err == nil {
		t.Fatal("expected list failure to stop place backfill")
	}
	if len(indexer.events) != 0 {
		t.Fatalf("list failure must not write index documents: %#v", indexer.events)
	}
}

func TestBackfillRetiresAndTombstonesPlacesWithoutLiveReferences(t *testing.T) {
	store := NewInMemoryPlaceStore()
	if _, err := store.Upsert(context.Background(), searchprojection.PlaceSnapshot{
		PlaceID:    "place:obsolete",
		Name:       "旧地点",
		RefPostIDs: []string{"deleted-post"},
	}); err != nil {
		t.Fatal(err)
	}
	indexer := &recordingIndexer{}
	report, err := Backfill(
		context.Background(),
		indexer,
		fakeReader{},
		store,
	)
	if err != nil {
		t.Fatal(err)
	}
	if report.TombstonedPlaces != 1 ||
		len(indexer.events) != 1 ||
		indexer.events[0].Op != es.OpDelete ||
		indexer.events[0].Doc.ObjectID != "place:obsolete" ||
		indexer.events[0].SourceVersion != 2 {
		t.Fatalf("obsolete place was not retired + tombstoned under the bumped version: report=%#v events=%#v", report, indexer.events)
	}
	places, err := store.ListAll(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(places) != 1 || len(places[0].RefPostIDs) != 0 || places[0].Version != 2 {
		t.Fatalf("retired snapshot must remain with an empty reference set and its version: %#v", places)
	}
	// A second run re-issues the same tombstone as an idempotent stale write.
	report, err = Backfill(context.Background(), indexer, fakeReader{}, store)
	if err != nil {
		t.Fatal(err)
	}
	if report.TombstonedPlaces != 1 || report.StaleWrites != 1 {
		t.Fatalf("retired place replay must be stale, not a failure: %#v", report)
	}
}

func TestBackfillMissingInputsFailFast(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, fakeReader{}, NewInMemoryPlaceStore()); err == nil {
		t.Fatal("nil indexer must fail")
	}
	if _, err := Backfill(context.Background(), &recordingIndexer{}, nil, NewInMemoryPlaceStore()); err == nil {
		t.Fatal("nil reader must fail")
	}
	if _, err := Backfill(context.Background(), &recordingIndexer{}, fakeReader{}, nil); err == nil {
		t.Fatal("nil store must fail")
	}
}

var _ = postmodel.Post{}
