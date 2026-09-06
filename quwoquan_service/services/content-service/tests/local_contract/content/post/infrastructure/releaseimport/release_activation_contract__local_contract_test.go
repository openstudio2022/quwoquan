// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
package releaseimport_test

import (
	"errors"
	"strings"
	"testing"
	"time"

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
		"stage-only":    "imported",
		"activate":      "imported",
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

func TestBuildActivationEventsBindsRevisionTargetAndPredecessor(t *testing.T) {
	now := time.Unix(1_800_000_000, 0).UTC()
	post := releaseimport.PostDoc{
		ContentID: "content-a", PostRef: "posts/article/a/1", ContentType: "article",
		ContentIdentity: "work", AuthorID: "author-a", ArticleMarkdown: "# A",
	}
	events, err := releaseimport.BuildActivationPostLifecycleEvents(
		[]releaseimport.PostDoc{post}, nil,
		releaseimport.ImportOptions{
			ReleaseID: "release-b", ManifestDigest: "sha256:" + strings.Repeat("b", 64),
			ReleaseClass: "research", ReleaseKind: "content", SourceOwner: "qwq_data",
			ProjectionVersion: 17,
		}, now,
		releaseimport.ActiveReleaseBinding{
			Found: true, SourceOwner: "qwq_data", ReleaseID: "release-a",
			ManifestDigest: "sha256:" + strings.Repeat("a", 64), Revision: 3,
		}, 4,
	)
	if err != nil || len(events) != 1 || events[0].AggregateVersion != 17 ||
		!strings.Contains(events[0].EventID, "data-release-activation:4:17:release-b:") ||
		!strings.Contains(events[0].EventID, "release-a") {
		t.Fatalf("activation event identity mismatch events=%+v err=%v", events, err)
	}
}
