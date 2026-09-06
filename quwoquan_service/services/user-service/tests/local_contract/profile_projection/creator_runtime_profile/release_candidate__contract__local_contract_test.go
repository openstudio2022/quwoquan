// readiness_case: creator-release-candidate-stage-local
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
package local_contract

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	"quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

func TestCandidateReceiptFoundAndNotFoundAreExact(t *testing.T) {
	identity := model.ReleaseIdentity{Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-a", ManifestDigest: digest("a")}
	generatedAt := time.Date(2026, 9, 6, 5, 0, 0, 0, time.UTC)
	missing, err := releaseimport.BuildCreatorReleaseCandidateReceipt(model.CreatorReleaseCandidateState{ReleaseIdentity: identity}, false, generatedAt)
	if err != nil {
		t.Fatal(err)
	}
	if missing.Status != "not_found" || missing.ReleaseID != "release-a" || missing.ProjectionVersion != 0 || missing.Counts != nil || len(missing.AuthorIDs) != 0 {
		t.Fatalf("unexpected not_found receipt: %+v", missing)
	}
	verifiedAt := generatedAt.Add(-time.Minute)
	state := model.CreatorReleaseCandidateState{ReleaseIdentity: identity, Status: "verified", ProjectionVersion: 1, VerifiedAt: verifiedAt, ClosureDigest: digest("b"), ExpectedCount: 1, ProjectedCount: 1, AuthorIDs: []string{"author-a"}, ProfileDigests: []model.CreatorProfileDigestBinding{{CreatorID: "creator-a", AuthorID: "author-a", Digest: digest("c")}}}
	found, err := releaseimport.BuildCreatorReleaseCandidateReceipt(state, true, generatedAt)
	if err != nil {
		t.Fatal(err)
	}
	if state.PostgreSQLWrites != (model.CandidatePostgreSQLWriteCounts{}) {
		t.Fatalf("stage-only PostgreSQL writes must be zero: %+v", state.PostgreSQLWrites)
	}
	if found.Schema != releaseimport.CreatorReleaseCandidateReceiptSchema || found.Status != "found" || found.ProjectionVersion != 1 || found.VerifiedAt == nil || found.Counts == nil || found.Counts.Expected != 1 || found.Counts.Projected != 1 || len(found.AuthorIDs) != 1 || len(found.ProfileDigests) != 1 {
		t.Fatalf("unexpected found receipt: %+v", found)
	}
}

func TestReleaseControlAcceptsOnlyExactCandidateTuple(t *testing.T) {
	_, err := releaseimport.ParseReleaseControlCommand([]string{"--operation", "query-candidate", "--mongo-uri", "mongodb://localhost", "--env", "alpha", "--release-id", "release-a", "--manifest-digest", digest("a"), "--report", t.TempDir() + "/receipt.json"})
	if err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{
		{"--operation", "query-candidate", "--mongo-uri", "mongodb://localhost", "--env", "alpha", "--release-id", "release-a", "--manifest-digest", digest("A"), "--report", "receipt.json"},
		{"--operation", "query-active", "--mongo-uri", "mongodb://localhost", "--env", "alpha", "--release-id", "release-a", "--manifest-digest", digest("a"), "--report", "receipt.json"},
	} {
		if _, parseErr := releaseimport.ParseReleaseControlCommand(args); parseErr == nil {
			t.Fatalf("non-exact query accepted: %#v", args)
		}
	}
}

func TestReceiptIsCreateOnceAndSymlinkFailClosed(t *testing.T) {
	report := struct {
		Status string `json:"status"`
	}{Status: "found"}
	root := t.TempDir()
	path := root + "/receipt.json"
	if err := releaseimport.WriteCreateOnceReport(path, report); err != nil {
		t.Fatal(err)
	}
	if err := releaseimport.WriteCreateOnceReport(path, report); err == nil {
		t.Fatal("receipt replay overwrote create-once evidence")
	}
	outside := t.TempDir()
	link := root + "/link"
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	if err := releaseimport.WriteCreateOnceReport(link+"/receipt.json", report); err == nil {
		t.Fatal("symlink parent was accepted")
	}
}

func TestUnavailableFenceReaderNeverInventsActiveTuple(t *testing.T) {
	fence, found, err := (userports.UnavailableContentReleaseFenceReader{}).ActiveContentReleaseFence(context.Background())
	if err != nil || found || fence != (userports.ContentReleaseFence{}) {
		t.Fatalf("unavailable seam must fail closed: %+v %v %v", fence, found, err)
	}
}

func digest(character string) string { return "sha256:" + strings.Repeat(character, 64) }
