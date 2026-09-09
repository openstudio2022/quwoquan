// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039
package runtimemedia

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestReleaseMediaRejectsRetiredClasses(t *testing.T) {
	root, _ := releaseMediaClosureFixture(t)
	for _, class := range []string{"", "research", "commercial", "prod-gray"} {
		t.Run(class, func(t *testing.T) {
			if _, err := LoadReleaseMediaAssets(root, "release-geo-media", class); err == nil {
				t.Fatalf("retired or absent class %q must fail closed", class)
			}
		})
	}
}

func TestProductionReleaseMediaRejectsPrivateObjectKeyEvenEmpty(t *testing.T) {
	for _, value := range []any{nil, "", "media/objects/sha256/aa/aa/private.jpg"} {
		root, _ := releaseMediaClosureFixture(t)
		path := filepath.Join(root, "payload", "media_manifest.json")
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var document map[string]any
		if err := json.Unmarshal(raw, &document); err != nil {
			t.Fatal(err)
		}
		asset := document["assets"].([]any)[0].(map[string]any)
		asset["privateObjectKey"] = value
		writeReleaseMediaClosureJSON(t, path, document)
		if _, err := LoadReleaseMediaAssets(root, "release-geo-media", "production"); err == nil {
			t.Fatalf("retired privateObjectKey=%v must be rejected, not ignored", value)
		}
	}
}

func TestProductionReleaseMediaRejectsAbsentPublicIdentity(t *testing.T) {
	root, _ := releaseMediaClosureFixture(t)
	path := filepath.Join(root, "payload", "media_manifest.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	delete(document["assets"].([]any)[0].(map[string]any), "publicSliceKey")
	writeReleaseMediaClosureJSON(t, path, document)
	if _, err := LoadReleaseMediaAssets(root, "release-geo-media", "production"); err == nil {
		t.Fatal("missing public identity must not become public by default")
	}
}
