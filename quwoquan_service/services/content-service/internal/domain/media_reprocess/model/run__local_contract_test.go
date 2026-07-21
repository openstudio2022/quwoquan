package mediaimagereprocessrun

import (
	"testing"
	"time"
)

func TestRunPauseResumeAndRollbackFollowDurableCursorOrder(t *testing.T) {
	now := time.Date(2026, 7, 21, 1, 0, 0, 0, time.UTC)
	run, err := Start(StartParams{
		RunID:                         "run-1",
		TargetDerivativePolicyVersion: 2,
		AssetIDs:                      []string{"image-a", "image-b"},
		Now:                           now,
	})
	if err != nil {
		t.Fatalf("start: %v", err)
	}
	if err := run.Pause(now.Add(time.Second)); err != nil {
		t.Fatalf("pause: %v", err)
	}
	if _, runnable := run.NextAssetID(); runnable {
		t.Fatal("paused run must not expose a new asset")
	}
	if err := run.Resume(now.Add(2 * time.Second)); err != nil {
		t.Fatalf("resume: %v", err)
	}
	if err := run.RecordAssetOutcome("image-a", &Activation{
		AssetID:           "image-a",
		PreviousRevision:  1,
		ActivatedRevision: 2,
		ActivatedAt:       now.Add(3 * time.Second),
	}, "", now.Add(3*time.Second)); err != nil {
		t.Fatalf("record activation: %v", err)
	}
	if err := run.RecordAssetOutcome(
		"image-b",
		nil,
		"image decoder rejected malformed bytes",
		now.Add(4*time.Second),
	); err != nil {
		t.Fatalf("record content failure: %v", err)
	}
	if run.Status() != StatusCompleted {
		t.Fatalf("status=%s, want completed", run.Status())
	}
	if err := run.StartRollback(now.Add(5 * time.Second)); err != nil {
		t.Fatalf("start rollback: %v", err)
	}
	activation, found := run.NextRollbackActivation()
	if !found || activation.AssetID != "image-a" {
		t.Fatalf("rollback must use reverse activation audit: %+v found=%v", activation, found)
	}
	if err := run.RecordRollback(activation, now.Add(6*time.Second)); err != nil {
		t.Fatalf("record rollback: %v", err)
	}
	if run.Status() != StatusRolledBack {
		t.Fatalf("status=%s, want rolled_back", run.Status())
	}
	if _, err := Restore(run.Snapshot()); err != nil {
		t.Fatalf("restored run must preserve rollback audit: %v", err)
	}
}

func TestRunRejectsDuplicateOrOutOfOrderAssets(t *testing.T) {
	now := time.Date(2026, 7, 21, 1, 0, 0, 0, time.UTC)
	if _, err := Start(StartParams{
		RunID:                         "run-duplicate",
		TargetDerivativePolicyVersion: 2,
		AssetIDs:                      []string{"image-a", "image-a"},
		Now:                           now,
	}); err == nil {
		t.Fatal("duplicate explicit target assets must be rejected")
	}
}
