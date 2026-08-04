package releaseimport_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestWriteImportReportKeepsZeroEntitiesLoaded(t *testing.T) {
	t.Parallel()

	reportPath := filepath.Join(t.TempDir(), "import.json")
	if err := releaseimport.WriteImportReport(reportPath, bson.M{
		"schema":         "quwoquan.content_import_report",
		"status":         "dry-run",
		"environment":    "gamma",
		"releaseId":      "release-posts-only",
		"sourceOwner":    "qwq_data",
		"manifestDigest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
		"mode":           "sync",
		"deletePolicy":   "tombstone",
		"counts": bson.M{
			"postsLoaded": 4,
			// Intentionally omit entitiesLoaded to prove WriteImportReport
			// backfills the schema-required zero counter.
		},
		"postBindings": []any{},
		"auditEvents":  []string{"DataReleasePrepared"},
	}); err != nil {
		t.Fatalf("WriteImportReport: %v", err)
	}

	raw, err := os.ReadFile(reportPath)
	if err != nil {
		t.Fatalf("read report: %v", err)
	}
	var report map[string]any
	if err := json.Unmarshal(raw, &report); err != nil {
		t.Fatalf("decode report: %v", err)
	}
	counts, ok := report["counts"].(map[string]any)
	if !ok {
		t.Fatalf("counts missing or wrong type: %#v", report["counts"])
	}
	if got, ok := counts["postsLoaded"].(float64); !ok || got != 4 {
		t.Fatalf("postsLoaded=%v, want 4", counts["postsLoaded"])
	}
	if got, ok := counts["entitiesLoaded"].(float64); !ok || got != 0 {
		t.Fatalf("entitiesLoaded=%v, want 0 (field must be present)", counts["entitiesLoaded"])
	}
}

func TestImportLoadedCountsAlwaysIncludesZeroEntities(t *testing.T) {
	t.Parallel()

	counts := releaseimport.ImportLoadedCounts(3, 0)
	if counts["postsLoaded"] != 3 {
		t.Fatalf("postsLoaded=%v, want 3", counts["postsLoaded"])
	}
	if counts["entitiesLoaded"] != 0 {
		t.Fatalf("entitiesLoaded=%v, want 0", counts["entitiesLoaded"])
	}
	raw, err := json.Marshal(counts)
	if err != nil {
		t.Fatalf("marshal counts: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("decode counts: %v", err)
	}
	if _, ok := decoded["entitiesLoaded"]; !ok {
		t.Fatal("json omitted entitiesLoaded=0")
	}
}
