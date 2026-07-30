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
	baselineDigest := store.EffectiveHash()
	quietLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go StartSyncLoop(ctx, store, quietLogger, SyncConfig{Path: path, Interval: 10 * time.Millisecond})

	// Startup load must swap to the file policy.
	if !waitFor(t, time.Second, func() bool { return store.EffectiveHash() != baselineDigest }) {
		t.Fatalf("startup load did not apply file policy, digest stayed %q", baselineDigest)
	}
	initialDigest := store.EffectiveHash()

	// Edit the file (new mtime + changed policy content) -> reload picks it up.
	edited := `
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

	if !waitFor(t, time.Second, func() bool { return store.EffectiveHash() != initialDigest }) {
		t.Fatalf("reload did not pick up edited policy, digest stayed %q", initialDigest)
	}
}

func TestStartSyncLoop_BadEditKeepsLastGood(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policy.yaml")
	if err := os.WriteFile(path, []byte(testPolicyYAML), 0o644); err != nil {
		t.Fatalf("write initial: %v", err)
	}

	store := NewStoreFromBaseline()
	baselineDigest := store.EffectiveHash()
	quietLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go StartSyncLoop(ctx, store, quietLogger, SyncConfig{Path: path, Interval: 10 * time.Millisecond})

	if !waitFor(t, time.Second, func() bool { return store.EffectiveHash() != baselineDigest }) {
		t.Fatalf("startup load failed, digest stayed %q", baselineDigest)
	}
	goodDigest := store.EffectiveHash()

	// Write a structurally invalid policy: it must be rejected and the
	// last-good digest retained — a bad edit never degrades scoring.
	bad := `
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

	// Give the loop several ticks; the last-good digest must remain unchanged.
	time.Sleep(120 * time.Millisecond)
	if store.EffectiveHash() != goodDigest {
		t.Fatalf("bad edit changed live digest to %q, want %q", store.EffectiveHash(), goodDigest)
	}
}
