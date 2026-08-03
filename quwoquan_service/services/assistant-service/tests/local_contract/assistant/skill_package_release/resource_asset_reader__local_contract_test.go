// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package skill_package_release_test

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
)

func TestOfficialAssetReaderAllowsOnlyBoundedFilesInsideRoot(t *testing.T) {
	root := t.TempDir()
	assetPath := filepath.Join(root, "release-a", "manifest.json")
	if err := os.MkdirAll(filepath.Dir(assetPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(assetPath, []byte(`{"skillId":"travel_companion"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	reader, err := artifact.NewResourceReader(root)
	if err != nil {
		t.Fatal(err)
	}
	content, err := reader.ReadAsset(
		t.Context(),
		"skill-package://official/release-a/manifest.json",
	)
	if err != nil {
		t.Fatalf("ReadAsset() error = %v", err)
	}
	if string(content) != `{"skillId":"travel_companion"}` {
		t.Fatalf("ReadAsset() = %q", content)
	}

	outside := filepath.Join(t.TempDir(), "outside.json")
	if err := os.WriteFile(outside, []byte("outside"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "escape.json")); err != nil {
		t.Fatal(err)
	}
	for _, locator := range []string{
		"file:///etc/passwd",
		"skill-package://other/release-a/manifest.json",
		"skill-package://official/../outside.json",
		"skill-package://official/%2e%2e/outside.json",
		"skill-package://official/escape.json",
	} {
		if _, err := reader.ReadAsset(t.Context(), locator); !errors.Is(err, packagemodel.ErrAssetUnavailable) {
			t.Fatalf("ReadAsset(%q) error=%v, want ErrAssetUnavailable", locator, err)
		}
	}
}

func TestOfficialAssetReaderRejectsOversizedAsset(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "oversized.bin")
	if err := os.WriteFile(path, make([]byte, (4<<20)+1), 0o600); err != nil {
		t.Fatal(err)
	}
	reader, err := artifact.NewResourceReader(root)
	if err != nil {
		t.Fatal(err)
	}
	_, err = reader.ReadAsset(t.Context(), "skill-package://official/oversized.bin")
	if !errors.Is(err, packagemodel.ErrAssetUnavailable) {
		t.Fatalf("ReadAsset() error=%v, want ErrAssetUnavailable", err)
	}
}
