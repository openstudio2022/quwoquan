package releaseimport_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046
func TestPostManifestCarrierVectorsShareDataContract(t *testing.T) {
	path := filepath.Join("..", "..", "..", "..", "..", "..", "..", "..", "quwoquan_data", "tests", "fixtures", "contracts", "post_manifest_vectors.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var payload struct {
		Vectors []struct {
			Name     string          `json:"name"`
			Valid    bool            `json:"valid"`
			Manifest json.RawMessage `json:"manifest"`
		} `json:"vectors"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatal(err)
	}
	for _, vector := range payload.Vectors {
		t.Run(vector.Name, func(t *testing.T) {
			err := ValidatePostManifestCarrierJSON(vector.Manifest, vector.Name)
			if (err == nil) != vector.Valid {
				t.Fatalf("valid=%v, error=%v", vector.Valid, err)
			}
		})
	}
}
