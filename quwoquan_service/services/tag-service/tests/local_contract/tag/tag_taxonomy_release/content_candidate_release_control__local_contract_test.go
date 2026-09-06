package tag_taxonomy_release_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/tagreleasecontrol"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

func TestTagReleaseControlParsesOnlyExactCandidateQuery(t *testing.T) {
	digest := "sha256:" + strings.Repeat("a", 64)
	valid := []string{
		"--operation", "query-candidate", "--mongo-uri", "mongodb://127.0.0.1:27017",
		"--env", "alpha", "--release-id", "release-a", "--manifest-digest", digest,
		"--report", filepath.Join(t.TempDir(), "candidate.json"),
	}
	command, err := tagreleasecontrol.ParseCommand(valid)
	if err != nil || command.SourceOwner != "qwq_data" || command.Database != "quwoquan_tag" {
		t.Fatalf("ParseCommand()=%+v err=%v", command, err)
	}
	for _, invalid := range [][]string{
		valid[:len(valid)-2],
		append(append([]string{}, valid...), "--source-owner", "other"),
		append(append([]string{}, valid...), "--operation", "query-active"),
	} {
		if _, err := tagreleasecontrol.ParseCommand(invalid); err == nil {
			t.Fatalf("accepted invalid exact candidate query: %#v", invalid)
		}
	}
}

func TestTagCandidateReceiptFoundAndNotFoundAreExact(t *testing.T) {
	digest := "sha256:" + strings.Repeat("a", 64)
	closure := "sha256:" + strings.Repeat("b", 64)
	now := time.Date(2026, 9, 6, 1, 2, 3, 0, time.UTC)
	identity := taxonomyreleasestore.ContentCandidate{
		Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-a",
		ManifestDigest: digest,
	}
	notFound, err := tagreleasecontrol.BuildCandidateReceipt(identity, false, now)
	if err != nil || notFound.Status != "not_found" || notFound.Schema != tagreleasecontrol.TagReleaseCandidateReceiptSchema {
		t.Fatalf("not-found receipt=%+v err=%v", notFound, err)
	}
	raw, err := json.Marshal(notFound)
	if err != nil {
		t.Fatal(err)
	}
	var object map[string]any
	if err := json.Unmarshal(raw, &object); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"projectionVersion", "verifiedAt", "closureDigest", "expectedNodeCount", "projectedNodeCount", "canonicalDigest", "releaseKind", "tagRefsDigest"} {
		if _, exists := object[field]; exists {
			t.Fatalf("not_found exposed found-only field %q: %s", field, raw)
		}
	}
	identity.Status = "verified"
	identity.ProjectionVersion = 1
	identity.VerifiedAt = now.Add(-time.Minute)
	identity.ClosureDigest = closure
	identity.ExpectedNodeCount = 2
	identity.ProjectedNodeCount = 2
	identity.CanonicalDigest = digest
	identity.ReleaseKind = "content"
	identity.TagRefsDigest = closure
	found, err := tagreleasecontrol.BuildCandidateReceipt(identity, true, now)
	if err != nil || found.Status != "found" || found.ProjectionVersion != 1 ||
		found.ExpectedNodeCount == nil || *found.ExpectedNodeCount != 2 ||
		found.ProjectedNodeCount == nil || *found.ProjectedNodeCount != 2 || found.VerifiedAt == nil {
		t.Fatalf("found receipt=%+v err=%v", found, err)
	}
}

func TestTagCandidateReceiptIsCreateOnceAndRejectsSymlinks(t *testing.T) {
	directory := t.TempDir()
	path := filepath.Join(directory, "candidate.json")
	receipt := tagreleasecontrol.CandidateReceipt{
		Schema: tagreleasecontrol.TagReleaseCandidateReceiptSchema, Status: "not_found",
		Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-a",
		ManifestDigest: "sha256:" + strings.Repeat("a", 64), GeneratedAt: time.Now().UTC(),
	}
	if err := tagreleasecontrol.WriteReceipt(path, receipt); err != nil {
		t.Fatalf("write first receipt: %v", err)
	}
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := tagreleasecontrol.WriteReceipt(path, receipt); err == nil {
		t.Fatal("second write overwrote create-once receipt")
	}
	after, err := os.ReadFile(path)
	if err != nil || string(before) != string(after) {
		t.Fatalf("existing receipt changed: err=%v", err)
	}
	target := filepath.Join(directory, "target.json")
	if err := os.WriteFile(target, []byte("keep"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(directory, "link.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if err := tagreleasecontrol.WriteReceipt(link, receipt); err == nil {
		t.Fatal("symlink receipt destination was accepted")
	}
	linkedParent := filepath.Join(directory, "linked-parent")
	realParent := filepath.Join(directory, "real-parent")
	if err := os.Mkdir(realParent, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(realParent, linkedParent); err != nil {
		t.Fatal(err)
	}
	if err := tagreleasecontrol.WriteReceipt(filepath.Join(linkedParent, "receipt.json"), receipt); err == nil {
		t.Fatal("symlink parent was accepted")
	}
}
