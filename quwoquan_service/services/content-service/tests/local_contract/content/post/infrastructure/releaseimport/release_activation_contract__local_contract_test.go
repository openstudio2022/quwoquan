// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
package releaseimport_test

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestReleaseActivationCASConflictIsTyped(t *testing.T) {
	conflict := &releaseimport.ReleaseActivationCASConflictError{
		Expected: releaseimport.ExpectedActiveRelease{
			SourceOwner: "qwq_data", ReleaseID: "release-a",
			ManifestDigest: "sha256:" + strings.Repeat("a", 64), Revision: 3,
		},
		Actual: releaseimport.ActiveReleaseBinding{
			Found: true, SourceOwner: "qwq_data", ReleaseID: "release-b",
			ManifestDigest: "sha256:" + strings.Repeat("b", 64), Revision: 4,
		},
	}
	wrapped := errors.New("unrelated")
	if releaseimport.IsReleaseActivationCASConflict(wrapped) {
		t.Fatal("unrelated error classified as active CAS conflict")
	}
	if !releaseimport.IsReleaseActivationCASConflict(conflict) ||
		!strings.Contains(conflict.Error(), releaseimport.ReleaseActivationCASConflictCode) {
		t.Fatalf("typed CAS conflict identity missing: %v", conflict)
	}
}

func TestImportedReleaseValidationRequiresMediaClosure(t *testing.T) {
	valid := releaseimport.ImportedReleaseApplyResult{
		PostsUpserted: 2, OutboxEventsReady: 2, OutboxEventsAppended: 2,
		MediaAssetsExpected: 3, MediaAssetsProjected: 3,
	}
	if err := releaseimport.ValidateImportedReleaseApplyResult(valid, 2); err != nil {
		t.Fatalf("exact owner-local closure rejected: %v", err)
	}
	valid.MediaAssetsProjected = 2
	if err := releaseimport.ValidateImportedReleaseApplyResult(valid, 2); err == nil ||
		!strings.Contains(err.Error(), "media projection count mismatch") {
		t.Fatalf("partial media projection was accepted: %v", err)
	}
}

func TestReleaseBindingIncludesSourceOwnerTuple(t *testing.T) {
	binding := releaseimport.ReleaseBindingFromImportOptions(releaseimport.ImportOptions{
		SourceOwner: "qwq_data", ReleaseID: "release-a",
		ManifestDigest: "sha256:" + strings.Repeat("a", 64),
	})
	if binding.SourceOwner != "qwq_data" || binding.ReleaseID != "release-a" || binding.Empty() {
		t.Fatalf("release tuple is incomplete: %+v", binding)
	}
}

func TestImportReportStatusCannotClaimActivation(t *testing.T) {
	for mode, want := range map[string]string{
		"stage-only":    "staged",
		"activate":      "staged",
		"repair-active": "replay_validated",
	} {
		if got := releaseimport.ImportReportStatus(mode); got != want {
			t.Fatalf("ImportReportStatus(%q)=%q want=%q", mode, got, want)
		}
	}
}

func TestRepairReportUsesReplayStatusWithStageOnlyActivationMode(t *testing.T) {
	if got := releaseimport.ImportReportStatus("repair-active"); got != "replay_validated" {
		t.Fatalf("repair status=%q want=replay_validated", got)
	}
	for _, mode := range []string{"stage-only", "activate", "repair-active"} {
		if got := releaseimport.ImportReportActivationMode(mode, mode == "repair-active"); got != "stage-only" {
			t.Fatalf("%s activationMode=%q want=stage-only", mode, got)
		}
	}
	events := releaseimport.ImportReplayRepairAuditEvents()
	if len(events) < 2 || events[1] != "DataReleaseReplayValidated" {
		t.Fatalf("repair audit events=%#v", events)
	}
}

func TestImportOptionsRejectResetSourceAndInvalidCleanupPolicy(t *testing.T) {
	base := releaseimport.ImportOptions{ReleaseKind: "content", Mode: "upsert", DeletePolicy: "none"}
	if err := releaseimport.ValidateImportOptions(base); err != nil {
		t.Fatalf("valid upsert policy: %v", err)
	}
	for _, opts := range []releaseimport.ImportOptions{
		{ReleaseKind: "content", Mode: "reset-source", DeletePolicy: "tombstone"},
		{ReleaseKind: "content", Mode: "upsert", DeletePolicy: "tombstone"},
		{ReleaseKind: "content", Mode: "sync", DeletePolicy: "hard-delete"},
	} {
		if err := releaseimport.ValidateImportOptions(opts); err == nil {
			t.Fatalf("invalid candidate policy accepted: %+v", opts)
		}
	}
}

func TestCommittedFencePayloadBindsRevisionTargetAndPredecessor(t *testing.T) {
	now := time.Unix(1_800_000_000, 0).UTC()
	before := wire.ContentActiveReleaseFence{Found: true, Environment: "alpha", SourceOwner: "qwq_data", ReleaseId: "a", ManifestDigest: "sha256:" + strings.Repeat("a", 64), Revision: 3, ProjectionVersion: 16, ActivatedAt: &now}
	after := before
	after.ReleaseId = "b"
	after.ManifestDigest = "sha256:" + strings.Repeat("b", 64)
	after.Revision = 4
	after.ProjectionVersion = 17
	receipt := wire.ContentReleaseCommitReceipt{Transition: wire.ContentReleaseFenceChangedPayload{Before: before, After: after}}
	receipt.EventId = app.ReleaseFenceEventID(after)
	receipt.PayloadDigest = app.ReleaseFencePayloadDigest(receipt.Transition)
	q := wire.ReadContentReleaseCommitReceiptQuery{Expected: before, Release: wire.ReleaseCandidateBinding{Environment: "alpha", SourceOwner: "qwq_data", ReleaseId: "b", ManifestDigest: after.ManifestDigest}}
	if err := app.ValidateReleaseCommitReceipt(q, receipt); err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(receipt.Transition)
	var payload map[string]any
	_ = json.Unmarshal(raw, &payload)
	if len(payload) != 2 || payload["before"] == nil || payload["after"] == nil {
		t.Fatal("fence must only contain before/after")
	}
	receipt.Transition.After.Revision++
	if app.ValidateReleaseCommitReceipt(q, receipt) == nil {
		t.Fatal("tampered revision accepted")
	}
}
