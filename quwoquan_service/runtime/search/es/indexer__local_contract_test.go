package es

import (
	"context"
	"errors"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

type fakeWriter struct {
	docs     map[string]map[string]any
	versions map[string]int64
	digests  map[string]string
}

func newFakeWriter() *fakeWriter {
	return &fakeWriter{
		docs:     map[string]map[string]any{},
		versions: map[string]int64{},
		digests:  map[string]string{},
	}
}

func (w *fakeWriter) UpsertVersioned(
	_ context.Context,
	_ string,
	id string,
	sourceVersion int64,
	doc map[string]any,
) (bool, error) {
	canonical, err := WithCanonicalSourceDigest(doc)
	if err != nil {
		return false, err
	}
	doc = canonical
	digest, _ := doc["sourceDigest"].(string)
	if w.versions[id] > sourceVersion {
		return false, nil
	}
	if w.versions[id] == sourceVersion {
		if w.digests[id] == digest {
			return false, nil
		}
		return false, &SameVersionDigestConflictError{
			DocumentID: id, SourceVersion: sourceVersion, SourceDigest: digest,
		}
	}
	w.versions[id] = sourceVersion
	w.digests[id] = digest
	w.docs[id] = doc
	return true, nil
}
func (w *fakeWriter) TombstoneVersioned(
	_ context.Context,
	_ string,
	id string,
	objectType string,
	objectID string,
	sourceVersion int64,
) (bool, error) {
	document, err := VersionedTombstoneDocument(objectType, objectID, sourceVersion)
	if err != nil {
		return false, err
	}
	return w.UpsertVersioned(context.Background(), "", id, sourceVersion, document)
}

func TestIndexerUpsertMapsTargetAndAnchors(t *testing.T) {
	w := newFakeWriter()
	ix := NewIndexer(w, "")
	doc := rtsearch.Document{
		ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post_1",
		Title: "露营攻略", ContentType: "video", Visibility: "public",
		Freshness: time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
		Fields:    map[string]string{"authorId": "user_1", "authorName": "alice"},
	}
	applied, err := ix.ApplyVersioned(context.Background(), VersionedChangeEvent{Op: OpUpsert, Doc: doc, SourceVersion: 1})
	if err != nil || !applied {
		t.Fatalf("apply applied=%v err=%v", applied, err)
	}
	stored, ok := w.docs["content.post:post_1"]
	if !ok {
		t.Fatalf("doc not indexed: %#v", w.docs)
	}
	if stored["target"] != string(rtsearch.TargetVideo) {
		t.Fatalf("target=%v want video", stored["target"])
	}
	if stored["authorId"] != "user_1" || stored["authorName"] != "alice" {
		t.Fatalf("anchor fields missing: %#v", stored)
	}
	if stored["sourceVersion"] != int64(1) || stored["deleted"] != false {
		t.Fatalf("versioned upsert must persist sourceVersion and live marker: %#v", stored)
	}
}

func TestDocumentToIndexProjectsLocationDimension(t *testing.T) {
	doc := rtsearch.Document{
		ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: "hp_1",
		Title: "西湖主页", Visibility: "public",
		Geo:    &rtsearch.GeoPoint{Lat: 30.2431, Lng: 120.1505},
		Fields: map[string]string{"placeId": "entity:sight:xihu", "placeName": "杭州"},
	}
	idx := DocumentToIndex(doc)
	geo, ok := idx["geo"].(map[string]any)
	if !ok || geo["lat"] != 30.2431 || geo["lon"] != 120.1505 {
		t.Fatalf("geo projected wrong (ES expects lat/lon): %#v", idx["geo"])
	}
	if idx["placeId"] != "entity:sight:xihu" || idx["placeName"] != "杭州" {
		t.Fatalf("place reference missing: %#v", idx)
	}
}

func TestLocationDimensionRoundTrip(t *testing.T) {
	orig := rtsearch.Document{
		ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post_1",
		Title: "西湖露营", ContentType: "article", Visibility: "public",
		Geo:    &rtsearch.GeoPoint{Lat: 30.2431, Lng: 120.1505},
		Fields: map[string]string{"placeId": "entity:sight:xihu", "placeName": "杭州"},
	}
	// DocumentToIndex -> IndexToDocument must be lossless on the location dimension.
	back := IndexToDocument(DocumentToIndex(orig))
	if back.Geo == nil || back.Geo.Lat != orig.Geo.Lat || back.Geo.Lng != orig.Geo.Lng {
		t.Fatalf("geo round trip lost coords: got=%#v want=%#v", back.Geo, orig.Geo)
	}
	if back.Fields["placeId"] != "entity:sight:xihu" || back.Fields["placeName"] != "杭州" {
		t.Fatalf("place reference round trip lost: %#v", back.Fields)
	}
}

func TestIndexToDocumentRequiresCanonicalContentTypeField(t *testing.T) {
	document := IndexToDocument(map[string]any{
		"objectType": rtsearch.ObjectTypeContentPost,
		"objectId":   "post_legacy",
		"target":     string(rtsearch.TargetVideo),
		"type":       "video",
		"tags":       []any{"video"},
	})

	if document.ContentType != "" {
		t.Fatalf(
			"contentType must not be inferred from retired fields: %q",
			document.ContentType,
		)
	}
}

func TestDocumentToIndexOmitsGeoWhenAbsent(t *testing.T) {
	doc := rtsearch.Document{
		ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: "user_1", Title: "alice",
	}
	idx := DocumentToIndex(doc)
	if _, ok := idx["geo"]; ok {
		t.Fatalf("nil geo must not be indexed: %#v", idx)
	}
	if back := IndexToDocument(idx); back.Geo != nil {
		t.Fatalf("absent geo must round-trip to nil, got %#v", back.Geo)
	}
}

func TestIndexerTombstoneIsIdempotent(t *testing.T) {
	w := newFakeWriter()
	ix := NewIndexer(w, "")
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: "user_1", Title: "alice"}
	if _, err := ix.ApplyVersioned(context.Background(), VersionedChangeEvent{Op: OpUpsert, Doc: doc, SourceVersion: 1}); err != nil {
		t.Fatalf("upsert err=%v", err)
	}
	applied, err := ix.ApplyVersioned(context.Background(), VersionedChangeEvent{Op: OpDelete, Doc: doc, SourceVersion: 2})
	if err != nil || !applied {
		t.Fatalf("tombstone applied=%v err=%v", applied, err)
	}
	// Replayed tombstone is a same-version same-digest replay: no error, no write.
	applied, err = ix.ApplyVersioned(context.Background(), VersionedChangeEvent{Op: OpDelete, Doc: doc, SourceVersion: 2})
	if err != nil || applied {
		t.Fatalf("replay tombstone applied=%v err=%v", applied, err)
	}
	stored := w.docs[IndexID(doc)]
	if stored["deleted"] != true || stored["sourceVersion"] != int64(2) {
		t.Fatalf("tombstone must persist as a versioned soft-delete, got %#v", stored)
	}
}

func TestApplyVersionedRejectsOutOfOrderAndPreventsResurrection(t *testing.T) {
	w := newFakeWriter()
	ix := NewIndexer(w, "")
	doc := rtsearch.Document{
		ObjectType: rtsearch.ObjectTypeEntityHomepage,
		ObjectID:   "homepage-1",
		Title:      "version two",
	}
	apply := func(op ChangeOp, version int64, title string) (bool, error) {
		doc.Title = title
		return ix.ApplyVersioned(context.Background(), VersionedChangeEvent{
			Op: op, Doc: doc, SourceVersion: version,
		})
	}
	if applied, err := apply(OpUpsert, 2, "version two"); err != nil || !applied {
		t.Fatalf("v2 upsert applied=%v err=%v", applied, err)
	}
	if applied, err := apply(OpUpsert, 1, "late version one"); err != nil || applied {
		t.Fatalf("stale v1 applied=%v err=%v", applied, err)
	}
	if applied, err := apply(OpUpsert, 2, "version two"); err != nil || applied {
		t.Fatalf("same-digest v2 replay applied=%v err=%v", applied, err)
	}
	if applied, err := apply(OpUpsert, 2, "different version two"); applied || !errors.Is(err, ErrSameVersionDigestConflict) {
		t.Fatalf("different-digest v2 applied=%v err=%v", applied, err)
	}
	stored := w.docs[IndexID(doc)]
	if stored["title"] != "version two" || stored["sourceVersion"] != int64(2) || stored["deleted"] != false {
		t.Fatalf("out-of-order upsert changed document: %#v", stored)
	}
	if applied, err := apply(OpDelete, 3, ""); err != nil || !applied {
		t.Fatalf("v3 tombstone applied=%v err=%v", applied, err)
	}
	if applied, err := apply(OpUpsert, 2, "late version two"); err != nil || applied {
		t.Fatalf("late v2 applied=%v err=%v", applied, err)
	}
	tombstone := w.docs[IndexID(doc)]
	if tombstone["deleted"] != true || tombstone["sourceVersion"] != int64(3) || len(tombstone) != 5 {
		t.Fatalf("unexpected persistent tombstone: %#v", tombstone)
	}
	if applied, err := apply(OpDelete, 3, ""); err != nil || applied {
		t.Fatalf("tombstone replay applied=%v err=%v", applied, err)
	}
	if applied, err := apply(OpUpsert, 3, "different same-version facts"); applied || !errors.Is(err, ErrSameVersionDigestConflict) {
		t.Fatalf("same-version conflict applied=%v err=%v", applied, err)
	}
}

func TestApplyVersionedRequiresExplicitPositiveVersion(t *testing.T) {
	ix := NewIndexer(newFakeWriter(), "")
	_, err := ix.ApplyVersioned(context.Background(), VersionedChangeEvent{
		Op:  OpUpsert,
		Doc: rtsearch.Document{ObjectType: rtsearch.ObjectTypeCircle, ObjectID: "circle-1"},
	})
	if err == nil {
		t.Fatal("missing sourceVersion must fail")
	}
}
