package es

import (
	"context"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

type fakeWriter struct {
	docs map[string]map[string]any
}

func newFakeWriter() *fakeWriter { return &fakeWriter{docs: map[string]map[string]any{}} }

func (w *fakeWriter) Upsert(_ context.Context, _ string, id string, doc map[string]any) error {
	w.docs[id] = doc
	return nil
}
func (w *fakeWriter) Delete(_ context.Context, _ string, id string) error {
	delete(w.docs, id)
	return nil
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
	if err := ix.Apply(context.Background(), ChangeEvent{Op: OpUpsert, Doc: doc}); err != nil {
		t.Fatalf("apply err=%v", err)
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
}

func TestIndexerDeleteIsIdempotent(t *testing.T) {
	w := newFakeWriter()
	ix := NewIndexer(w, "")
	doc := rtsearch.Document{ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: "user_1", Title: "alice"}
	_ = ix.Apply(context.Background(), ChangeEvent{Op: OpUpsert, Doc: doc})
	if err := ix.Apply(context.Background(), ChangeEvent{Op: OpDelete, Doc: doc}); err != nil {
		t.Fatalf("delete err=%v", err)
	}
	// Replayed delete must not error.
	if err := ix.Apply(context.Background(), ChangeEvent{Op: OpDelete, Doc: doc}); err != nil {
		t.Fatalf("replay delete err=%v", err)
	}
	if len(w.docs) != 0 {
		t.Fatalf("expected empty index, got %#v", w.docs)
	}
}
