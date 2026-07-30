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

func writeReleaseBindingFixture(
	t *testing.T,
	headerReleaseID string,
	attestedReleaseID string,
	digest string,
) string {
	t.Helper()
	root := t.TempDir()
	for _, directory := range []string{"payload", "attestations"} {
		if err := os.MkdirAll(filepath.Join(root, directory), 0o755); err != nil {
			t.Fatalf("create %s: %v", directory, err)
		}
	}
	header := `{"schema":"quwoquan_data.release","releaseId":"` + headerReleaseID +
		`","sourceOwner":"qwq_data","releaseKind":"content"}`
	attestation := `{"schema":"quwoquan_data.release_attestation","releaseId":"` + attestedReleaseID +
		`","sourceOwner":"qwq_data","releaseKind":"content","payloadSha256":"` + digest + `"}`
	if err := os.WriteFile(filepath.Join(root, "payload", "release.json"), []byte(header), 0o644); err != nil {
		t.Fatalf("write release header: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "attestations", "release.json"), []byte(attestation), 0o644); err != nil {
		t.Fatalf("write release attestation: %v", err)
	}
	return root
}
