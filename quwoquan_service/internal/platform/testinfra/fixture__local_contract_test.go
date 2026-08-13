package testinfra

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"quwoquan_service/runtime/streaming"
)

type fixtureSample struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

func TestLoadJSONFixtureAndRoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sample.json")
	if err := os.WriteFile(path, []byte(`{"id":"one","name":"fixture"}`), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
	loaded := LoadJSONFixture[fixtureSample](t, path)
	if loaded.ID != "one" {
		t.Fatalf("loaded = %#v", loaded)
	}
	decoded := RoundTripJSON(t, loaded)
	if decoded != loaded {
		t.Fatalf("roundtrip = %#v, want %#v", decoded, loaded)
	}
}

func TestFakeStreamTransport(t *testing.T) {
	event, err := streaming.NewEnvelope("assistant.partial", 1, map[string]string{"text": "hello"})
	if err != nil {
		t.Fatalf("NewEnvelope() error = %v", err)
	}
	transport := NewFakeStreamTransport()
	transport.Publish(event)

	if got := transport.Last(t); got.Event != "assistant.partial" {
		t.Fatalf("Last().Event = %q", got.Event)
	}
	if len(transport.Events()) != 1 {
		t.Fatalf("Events length = %d", len(transport.Events()))
	}
}

func TestFakeModelProvider(t *testing.T) {
	provider := NewFakeModelProvider("answer")
	answer, err := provider.Complete(context.Background(), "prompt")
	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if answer != "answer" {
		t.Fatalf("answer = %q", answer)
	}
	if calls := provider.Calls(); len(calls) != 1 || calls[0] != "prompt" {
		t.Fatalf("calls = %#v", calls)
	}
}
