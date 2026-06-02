package recpolicy

import (
	"context"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// waitFor polls cond until true or the deadline elapses.
func waitFor(t *testing.T, timeout time.Duration, cond func() bool) bool {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return true
		}
		time.Sleep(5 * time.Millisecond)
	}
	return cond()
}

func TestStartSyncLoop_StartupLoadAndReload(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policy.yaml")
	if err := os.WriteFile(path, []byte(testPolicyYAML), 0o644); err != nil {
		t.Fatalf("write initial: %v", err)
	}

	store := NewStoreFromBaseline()
	quietLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go StartSyncLoop(ctx, store, quietLogger, SyncConfig{Path: path, Interval: 10 * time.Millisecond})

	// Startup load must swap to the file policy.
	if !waitFor(t, time.Second, func() bool { return store.Current().PolicyVersion == "test-v1" }) {
		t.Fatalf("startup load did not apply file policy, got %q", store.Current().PolicyVersion)
	}

	// Edit the file (new mtime + new version) -> ticker reload should pick it up.
	edited := `
version: 1
policyVersion: test-v2
defaultPreset: control
weightPresets:
  control: { tagRelevance: 3.0, popularity: 2.0, freshness: 1.5, negativePenalty: 5.0 }
scorer:
  freshnessHalfLifeHours: 24.0
  exploreFraction: 0.1
  maxAuthorPerFeed: 3
`
	// Ensure a strictly newer mtime even on coarse-grained filesystems.
	future := time.Now().Add(2 * time.Second)
	if err := os.WriteFile(path, []byte(edited), 0o644); err != nil {
		t.Fatalf("write edited: %v", err)
	}
	_ = os.Chtimes(path, future, future)

	if !waitFor(t, time.Second, func() bool { return store.Current().PolicyVersion == "test-v2" }) {
		t.Fatalf("reload did not pick up edited policy, got %q", store.Current().PolicyVersion)
	}
}

func TestStartSyncLoop_BadEditKeepsLastGood(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policy.yaml")
	if err := os.WriteFile(path, []byte(testPolicyYAML), 0o644); err != nil {
		t.Fatalf("write initial: %v", err)
	}

	store := NewStoreFromBaseline()
	quietLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go StartSyncLoop(ctx, store, quietLogger, SyncConfig{Path: path, Interval: 10 * time.Millisecond})

	if !waitFor(t, time.Second, func() bool { return store.Current().PolicyVersion == "test-v1" }) {
		t.Fatalf("startup load failed, got %q", store.Current().PolicyVersion)
	}

	// Write a structurally invalid policy: it must be rejected and the
	// last-good (test-v1) retained — a bad edit never degrades scoring.
	bad := `
version: 1
policyVersion: broken
defaultPreset: missing
weightPresets:
  control: { tagRelevance: 1.0 }
scorer:
  freshnessHalfLifeHours: 24.0
  maxAuthorPerFeed: 3
  exploreFraction: 0.1
`
	future := time.Now().Add(2 * time.Second)
	if err := os.WriteFile(path, []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad: %v", err)
	}
	_ = os.Chtimes(path, future, future)

	// Give the loop several ticks; version must stay test-v1.
	time.Sleep(120 * time.Millisecond)
	if store.Current().PolicyVersion != "test-v1" {
		t.Fatalf("bad edit changed live policy to %q, want last-good test-v1", store.Current().PolicyVersion)
	}
}
