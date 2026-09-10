// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package releaseimport_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

const testManifestDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func TestLoadReleaseBindingRequiresCanonicalHeaderAndAttestation(t *testing.T) {
	root := writeReleaseBindingFixture(t, "rel_pilot_002", "rel_pilot_002", testManifestDigest)

	binding, err := releaseimport.LoadReleaseBinding(root)
	if err != nil {
		t.Fatalf("LoadReleaseBinding: %v", err)
	}
	if binding.ReleaseID != "rel_pilot_002" || binding.SourceOwner != "qwq_data" ||
		binding.ReleaseKind != "content" || binding.ManifestDigest != testManifestDigest {
		t.Fatalf("release binding mismatch: %+v", binding)
	}
}

func TestLoadReleaseBindingAcceptsEmptyBaselineKind(t *testing.T) {
	root := writeReleaseBindingFixture(
		t,
		"content-empty-baseline-20260731",
		"content-empty-baseline-20260731",
		testManifestDigest,
		"empty_baseline",
	)

	binding, err := releaseimport.LoadReleaseBinding(root)
	if err != nil {
		t.Fatalf("LoadReleaseBinding empty_baseline: %v", err)
	}
	if binding.ReleaseKind != "empty_baseline" ||
		binding.ReleaseID != "content-empty-baseline-20260731" {
		t.Fatalf("empty baseline binding mismatch: %+v", binding)
	}
}

func TestLoadReleaseBindingRejectsUnknownReleaseKind(t *testing.T) {
	root := writeReleaseBindingFixture(
		t,
		"rel_pilot_002",
		"rel_pilot_002",
		testManifestDigest,
		"research_bundle",
	)
	_, err := releaseimport.LoadReleaseBinding(root)
	if err == nil || !strings.Contains(err.Error(), "releaseKind must be") {
		t.Fatalf("expected unknown releaseKind failure, got %v", err)
	}
}

func TestLoadReleaseBindingRejectsIdentityDriftAndNonCanonicalDigest(t *testing.T) {
	t.Run("release id drift", func(t *testing.T) {
		root := writeReleaseBindingFixture(t, "rel_header", "rel_attestation", testManifestDigest)
		_, err := releaseimport.LoadReleaseBinding(root)
		if err == nil || !strings.Contains(err.Error(), "releaseId drift") {
			t.Fatalf("expected releaseId drift, got %v", err)
		}
	})

	t.Run("digest", func(t *testing.T) {
		root := writeReleaseBindingFixture(t, "rel_pilot_002", "rel_pilot_002", "not-a-digest")
		_, err := releaseimport.LoadReleaseBinding(root)
		if err == nil || !strings.Contains(err.Error(), "payloadSha256") {
			t.Fatalf("expected canonical digest failure, got %v", err)
		}
	})
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
func TestLoadReleaseBindingRejectsRetiredCategoryFields(t *testing.T) {
	for _, relative := range []string{"payload/release.json", "attestations/release.json"} {
		for _, field := range []string{"releaseClass", "productLifecycleState", "readinessPhase"} {
			t.Run(relative+"/"+field, func(t *testing.T) {
				root := writeReleaseBindingFixture(t, "release-a", "release-a", testManifestDigest)
				path := filepath.Join(root, relative)
				raw, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				mutated := strings.Replace(string(raw), "{", `{"`+field+`":"research",`, 1)
				if err := os.WriteFile(path, []byte(mutated), 0o644); err != nil {
					t.Fatal(err)
				}
				if _, err := releaseimport.LoadReleaseBinding(root); err == nil || !strings.Contains(err.Error(), "retired category field "+field) {
					t.Fatalf("retired field must fail closed: %v", err)
				}
			})
		}
	}
}

func writeReleaseBindingFixture(
	t *testing.T,
	headerReleaseID string,
	attestedReleaseID string,
	digest string,
	releaseKind ...string,
) string {
	t.Helper()
	root := t.TempDir()
	for _, directory := range []string{"payload", "attestations"} {
		if err := os.MkdirAll(filepath.Join(root, directory), 0o755); err != nil {
			t.Fatalf("create %s: %v", directory, err)
		}
	}
	kind := "content"
	if len(releaseKind) > 0 && strings.TrimSpace(releaseKind[0]) != "" {
		kind = strings.TrimSpace(releaseKind[0])
	}
	header := `{"schema":"quwoquan_data.release","releaseId":"` + headerReleaseID +
		`","sourceOwner":"qwq_data","releaseKind":"` + kind + `"}`
	attestation := `{"schema":"quwoquan_data.release_attestation","releaseId":"` + attestedReleaseID +
		`","sourceOwner":"qwq_data","releaseKind":"` + kind + `","payloadSha256":"` + digest + `"}`
	if err := os.WriteFile(filepath.Join(root, "payload", "release.json"), []byte(header), 0o644); err != nil {
		t.Fatalf("write release header: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "attestations", "release.json"), []byte(attestation), 0o644); err != nil {
		t.Fatalf("write release attestation: %v", err)
	}
	return root
}
