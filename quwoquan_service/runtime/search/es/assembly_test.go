package es

import (
	"context"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
)

// TestNewRecallBackendFallsBackToNative proves an ES outage transparently
// degrades to the native backend instead of failing the search path.
func TestNewRecallBackendFallsBackToNative(t *testing.T) {
	// Unroutable endpoint => every ES request errors at transport.
	client, err := NewClient(Config{Endpoints: []string{"http://127.0.0.1:1"}})
	if err != nil {
		t.Fatalf("NewClient err=%v", err)
	}
	native := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType:  rtsearch.ObjectTypeContentPost,
		ObjectID:    "post_native",
		Title:       "native fallback hit",
		ContentType: "article",
		Visibility:  "public",
	}})

	backend := NewRecallBackend(client, native)
	if backend.Name() != "elasticsearch" {
		t.Fatalf("primary name should surface elasticsearch, got %q", backend.Name())
	}

	plan := rtsearch.RetrievePlan{
		Targets: []rtsearch.Target{rtsearch.TargetArticle},
		Terms:   []string{"native"},
		Limit:   10,
	}
	cands, err := backend.Recall(context.Background(), plan)
	if err != nil {
		t.Fatalf("Recall err=%v", err)
	}
	if len(cands) == 0 {
		t.Fatalf("expected native fallback candidates, got none")
	}
	if cands[0].Document.ObjectID != "post_native" {
		t.Fatalf("expected native doc, got %#v", cands[0].Document)
	}
}
