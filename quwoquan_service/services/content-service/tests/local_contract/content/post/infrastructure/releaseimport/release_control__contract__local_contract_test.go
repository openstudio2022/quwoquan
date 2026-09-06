// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
package releaseimport_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func releaseControlBaseArgs(report string) []string {
	return []string{
		"--mongo-uri", "mongodb://127.0.0.1:27017",
		"--env", "alpha",
		"--report", report,
	}
}

func TestParseReleaseControlCommandRejectsMixedAndIncompleteOperations(t *testing.T) {
	digest := "sha256:" + strings.Repeat("a", 64)
	tests := []struct {
		name string
		args []string
	}{
		{name: "unknown operation", args: append(releaseControlBaseArgs("out.json"), "--operation", "read")},
		{name: "candidate missing target", args: append(releaseControlBaseArgs("out.json"), "--operation", "query-candidate")},
		{name: "candidate expected flags", args: append(releaseControlBaseArgs("out.json"), "--operation", "query-candidate", "--release-id", "release-a", "--manifest-digest", digest, "--expected-active-empty")},
		{name: "active target flags", args: append(releaseControlBaseArgs("out.json"), "--operation", "query-active", "--release-id", "release-a")},
		{name: "activate no expectation", args: append(releaseControlBaseArgs("out.json"), "--operation", "activate", "--release-id", "release-a", "--manifest-digest", digest)},
		{name: "activate mixed expectation", args: append(releaseControlBaseArgs("out.json"), "--operation", "activate", "--release-id", "release-a", "--manifest-digest", digest, "--expected-active-empty", "--expected-active-release-id", "old", "--expected-active-manifest-digest", digest, "--expected-active-revision", "1")},
		{name: "activate mixed explicit zero revision", args: append(releaseControlBaseArgs("out.json"), "--operation", "activate", "--release-id", "release-a", "--manifest-digest", digest, "--expected-active-empty", "--expected-active-revision", "0")},
		{name: "activate false empty", args: append(releaseControlBaseArgs("out.json"), "--operation", "activate", "--release-id", "release-a", "--manifest-digest", digest, "--expected-active-empty=false")},
		{name: "activate incomplete tuple", args: append(releaseControlBaseArgs("out.json"), "--operation", "activate", "--release-id", "release-a", "--manifest-digest", digest, "--expected-active-release-id", "old", "--expected-active-revision", "1")},
		{name: "activate nonpositive revision", args: append(releaseControlBaseArgs("out.json"), "--operation", "activate", "--release-id", "release-a", "--manifest-digest", digest, "--expected-active-release-id", "old", "--expected-active-manifest-digest", digest, "--expected-active-revision", "-1")},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if _, err := releaseimport.ParseReleaseControlCommand(test.args); err == nil {
				t.Fatalf("invalid release-control input accepted: %#v", test.args)
			}
		})
	}
}

func TestRunReleaseControlRejectsInvalidInputBeforeCreatingReport(t *testing.T) {
	report := filepath.Join(t.TempDir(), "invalid.json")
	err := releaseimport.RunReleaseControl(t.Context(), []string{
		"--operation", "activate", "--mongo-uri", "mongodb://127.0.0.1:1",
		"--env", "alpha", "--report", report,
	})
	if err == nil {
		t.Fatal("invalid release-control input was accepted")
	}
	if _, statErr := os.Lstat(report); !os.IsNotExist(statErr) {
		t.Fatalf("invalid command created report: %v", statErr)
	}
}

func TestParseReleaseControlCommandNormalizesValidOperations(t *testing.T) {
	digest := "sha256:" + strings.Repeat("b", 64)
	candidateArgs := append(releaseControlBaseArgs("candidate.json"),
		"--operation", "query-candidate", "--release-id", "release-a", "--manifest-digest", digest)
	candidate, err := releaseimport.ParseReleaseControlCommand(candidateArgs)
	if err != nil || candidate.PostsDB != "quwoquan_content" || candidate.SourceOwner != "qwq_data" {
		t.Fatalf("candidate command=%+v err=%v", candidate, err)
	}
	activateArgs := append(releaseControlBaseArgs("activate.json"),
		"--operation", "activate", "--release-id", "release-b", "--manifest-digest", digest,
		"--expected-active-empty")
	activate, err := releaseimport.ParseReleaseControlCommand(activateArgs)
	if err != nil || !activate.Expected.Empty || activate.Expected.SourceOwner != "qwq_data" || activate.Expected.Revision != 0 {
		t.Fatalf("activate command=%+v err=%v", activate, err)
	}
}

func TestReleaseControlReportMappingsAreExact(t *testing.T) {
	digest := "sha256:" + strings.Repeat("c", 64)
	closure := "sha256:" + strings.Repeat("d", 64)
	verifiedAt := time.Date(2026, 9, 5, 8, 0, 0, 0, time.UTC)
	generatedAt := verifiedAt.Add(time.Minute)
	candidate, err := releaseimport.BuildContentReleaseCandidateReceipt(
		releaseimport.VerifiedImportedPostReleaseCandidate{
			Found: true, Environment: "alpha", SourceOwner: "qwq_data",
			ReleaseID: "release-a", ManifestDigest: digest,
			ReleaseClass: "research", ReleaseKind: "content", Mode: "sync",
			DeletePolicy: "tombstone", ProjectionVersion: 7, VerifiedAt: verifiedAt,
			ClosureDigests: releaseimport.ImportedReleaseCandidateClosureDigests{
				Posts: closure, Facts: closure, Media: closure,
			},
			Counts: releaseimport.ImportedReleaseCandidateCounts{
				PostsExpected: 2, PostsProjected: 2, OutboxExpected: 2,
				OutboxProjected: 2, MediaExpected: 1, MediaProjected: 1,
			},
		}, generatedAt,
	)
	if err != nil || candidate.Status != "found" || candidate.Counts == nil ||
		candidate.Counts.PostsProjected != 2 || candidate.ClosureDigests == nil ||
		candidate.ProjectionVersion != 7 || candidate.VerifiedAt == nil {
		t.Fatalf("candidate receipt=%+v err=%v", candidate, err)
	}

	active := releaseimport.ActiveReleaseBinding{
		Found: true, Environment: "alpha", SourceOwner: "qwq_data",
		ReleaseID: "release-a", ManifestDigest: digest, ReleaseClass: "research",
		ProjectionVersion: 9, Revision: 1, ActivatedAt: verifiedAt,
	}
	activeReceipt, err := releaseimport.BuildContentReleaseActiveReceipt(active, generatedAt)
	if err != nil || activeReceipt.Status != "found" || activeReceipt.Revision != 1 || activeReceipt.ActivatedAt == nil {
		t.Fatalf("active receipt=%+v err=%v", activeReceipt, err)
	}

	expected := releaseimport.ExpectedActiveRelease{Empty: true, SourceOwner: "qwq_data"}
	result := releaseimport.ReleaseActivationResult{Active: active, PostsMaterialized: 2, MediaAssetsMaterialized: 1, OutboxEventsReady: 2, OutboxEventsAppended: 2}
	activation, err := releaseimport.BuildContentReleaseActivationReceipt(
		"alpha", "qwq_data",
		releaseimport.ImportedReleaseBinding{SourceOwner: "qwq_data", ReleaseID: "release-a", ManifestDigest: digest},
		expected, result, active, generatedAt,
	)
	if err != nil || activation.Status != "activated" || activation.ExpectedActive.Found ||
		activation.ExpectedActive.Revision != 0 || activation.PreviousActive.Found ||
		activation.Active.Revision != 1 || activation.Counts.PostsMaterialized != 2 {
		t.Fatalf("activation receipt=%+v err=%v", activation, err)
	}
}

func TestReleaseControlNotFoundReportsOmitFoundOnlyFields(t *testing.T) {
	digest := "sha256:" + strings.Repeat("9", 64)
	now := time.Date(2026, 9, 5, 9, 0, 0, 0, time.UTC)
	candidate, err := releaseimport.BuildContentReleaseCandidateReceipt(
		releaseimport.VerifiedImportedPostReleaseCandidate{
			Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "missing",
			ManifestDigest: digest,
		}, now,
	)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(candidate)
	if err != nil {
		t.Fatal(err)
	}
	var candidateJSON map[string]any
	if err := json.Unmarshal(raw, &candidateJSON); err != nil {
		t.Fatal(err)
	}
	if candidateJSON["status"] != "not_found" {
		t.Fatalf("candidate status=%v", candidateJSON["status"])
	}
	for _, field := range []string{"releaseClass", "releaseKind", "mode", "deletePolicy", "projectionVersion", "verifiedAt", "closureDigests", "counts"} {
		if _, exists := candidateJSON[field]; exists {
			t.Fatalf("not-found candidate exposed found-only field %q: %s", field, raw)
		}
	}

	active, err := releaseimport.BuildContentReleaseActiveReceipt(
		releaseimport.ActiveReleaseBinding{Environment: "alpha", SourceOwner: "qwq_data"}, now,
	)
	if err != nil {
		t.Fatal(err)
	}
	raw, err = json.Marshal(active)
	if err != nil {
		t.Fatal(err)
	}
	var activeJSON map[string]any
	if err := json.Unmarshal(raw, &activeJSON); err != nil {
		t.Fatal(err)
	}
	if activeJSON["status"] != "not_found" {
		t.Fatalf("active status=%v", activeJSON["status"])
	}
	for _, field := range []string{"releaseId", "manifestDigest", "releaseClass", "projectionVersion", "revision", "activatedAt"} {
		if _, exists := activeJSON[field]; exists {
			t.Fatalf("not-found active exposed found-only field %q: %s", field, raw)
		}
	}
}

func TestExpectedActiveReportMappingPreservesExactTuple(t *testing.T) {
	digest := "sha256:" + strings.Repeat("8", 64)
	empty, err := releaseimport.ContentReleaseExpectedActiveFromExpectation(
		releaseimport.ExpectedActiveRelease{Empty: true, SourceOwner: "qwq_data"},
	)
	if err != nil || empty.Found || empty.SourceOwner != "qwq_data" || empty.Revision != 0 || empty.ReleaseID != "" || empty.ManifestDigest != "" {
		t.Fatalf("empty expected active=%+v err=%v", empty, err)
	}
	found, err := releaseimport.ContentReleaseExpectedActiveFromExpectation(
		releaseimport.ExpectedActiveRelease{
			SourceOwner: "qwq_data", ReleaseID: "release-a",
			ManifestDigest: digest, Revision: 3,
		},
	)
	if err != nil || !found.Found || found.ReleaseID != "release-a" || found.ManifestDigest != digest || found.Revision != 3 {
		t.Fatalf("found expected active=%+v err=%v", found, err)
	}
}

func TestReleaseControlReplayReportUsesExpectedPredecessor(t *testing.T) {
	digestA := "sha256:" + strings.Repeat("a", 64)
	digestB := "sha256:" + strings.Repeat("b", 64)
	now := time.Date(2026, 9, 5, 9, 0, 0, 0, time.UTC)
	active := releaseimport.ActiveReleaseBinding{
		Found: true, Environment: "alpha", SourceOwner: "qwq_data",
		ReleaseID: "release-b", ManifestDigest: digestB, ReleaseClass: "research",
		ProjectionVersion: 11, Revision: 4, ActivatedAt: now,
	}
	expected := releaseimport.ExpectedActiveRelease{
		SourceOwner: "qwq_data", ReleaseID: "release-a",
		ManifestDigest: digestA, Revision: 3,
	}
	receipt, err := releaseimport.BuildContentReleaseActivationReceipt(
		"alpha", "qwq_data",
		releaseimport.ImportedReleaseBinding{SourceOwner: "qwq_data", ReleaseID: "release-b", ManifestDigest: digestB},
		expected, releaseimport.ReleaseActivationResult{Active: active, Replayed: true},
		active, now.Add(time.Minute),
	)
	if err != nil || receipt.Status != "replayed" || !receipt.PreviousActive.Found ||
		receipt.PreviousActive.ReleaseID != expected.ReleaseID ||
		receipt.PreviousActive.ManifestDigest != expected.ManifestDigest ||
		receipt.PreviousActive.Revision != expected.Revision {
		t.Fatalf("replay predecessor receipt=%+v err=%v", receipt, err)
	}
}

func TestWriteReleaseControlReportIsCreateOnceAndRejectsSymlink(t *testing.T) {
	directory := t.TempDir()
	path := filepath.Join(directory, "active.json")
	report := releaseimport.ContentReleaseActiveReceipt{
		Schema: releaseimport.ContentReleaseActiveReceiptSchema, Status: "not_found",
		Environment: "alpha", SourceOwner: "qwq_data", GeneratedAt: time.Now().UTC(),
	}
	if err := releaseimport.WriteReleaseControlReport(path, report); err != nil {
		t.Fatalf("first report write: %v", err)
	}
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := releaseimport.WriteReleaseControlReport(path, report); err == nil {
		t.Fatal("second report write overwrote create-once receipt")
	}
	after, err := os.ReadFile(path)
	if err != nil || string(before) != string(after) {
		t.Fatalf("existing report changed: err=%v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(before, &decoded); err != nil || decoded["schema"] != releaseimport.ContentReleaseActiveReceiptSchema {
		t.Fatalf("canonical report JSON=%s err=%v", before, err)
	}

	target := filepath.Join(directory, "target.json")
	if err := os.WriteFile(target, []byte("keep"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(directory, "report-link.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if err := releaseimport.WriteReleaseControlReport(link, report); err == nil {
		t.Fatal("symlink report destination was accepted")
	}
	if content, err := os.ReadFile(target); err != nil || string(content) != "keep" {
		t.Fatalf("symlink target changed content=%q err=%v", content, err)
	}

	realDirectory := filepath.Join(directory, "real")
	if err := os.Mkdir(realDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	linkedDirectory := filepath.Join(directory, "linked")
	if err := os.Symlink(realDirectory, linkedDirectory); err != nil {
		t.Fatal(err)
	}
	if err := releaseimport.WriteReleaseControlReport(filepath.Join(linkedDirectory, "report.json"), report); err == nil {
		t.Fatal("symlink report directory was accepted")
	}
}
