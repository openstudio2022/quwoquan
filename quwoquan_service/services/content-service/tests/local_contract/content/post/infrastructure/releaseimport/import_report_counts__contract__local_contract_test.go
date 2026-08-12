package releaseimport_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
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

func TestImportAuditEventsRecordPreviousActiveRelease(t *testing.T) {
	repairs := []releaseimport.ImportedPostOutboxRepairAudit{
		{
			EventID: "event-b", BeforeSHA256: "sha256:" + strings.Repeat("b", 64),
			AfterSHA256: "sha256:" + strings.Repeat("c", 64),
		},
		{
			EventID: "event-a", BeforeSHA256: "sha256:" + strings.Repeat("d", 64),
			AfterSHA256: "sha256:" + strings.Repeat("e", 64),
		},
	}
	events := releaseimport.ImportAuditEvents(
		"release-previous",
		"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		repairs...,
	)
	if len(events) != 6 ||
		events[2] != "PreviousDataRelease|release-previous|sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" ||
		events[3] != "DataReleaseOutboxRepair|count=2" ||
		events[4] != "DataReleaseOutboxEventRepair|eventId=event-a|beforeSha256=sha256:"+strings.Repeat("d", 64)+"|afterSha256=sha256:"+strings.Repeat("e", 64) ||
		events[5] != "DataReleaseOutboxEventRepair|eventId=event-b|beforeSha256=sha256:"+strings.Repeat("b", 64)+"|afterSha256=sha256:"+strings.Repeat("c", 64) {
		t.Fatalf("previous active release audit event mismatch: %#v", events)
	}
	serialized, err := json.Marshal(events)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(serialized), "releaseDigest") ||
		strings.Contains(string(serialized), "sourceOwner") ||
		strings.Contains(string(serialized), "deletedAt") {
		t.Fatalf("repair audit leaked raw payload: %s", serialized)
	}
	if withoutPrevious := releaseimport.ImportAuditEvents("", ""); len(withoutPrevious) != 3 || withoutPrevious[2] != "DataReleaseOutboxRepair|count=0" {
		t.Fatalf("unexpected empty previous audit event: %#v", withoutPrevious)
	}
	replayEvents := releaseimport.ImportReplayRepairAuditEvents(repairs...)
	if len(replayEvents) != 5 || replayEvents[0] != "DataReleasePrepared" ||
		replayEvents[1] != "DataReleaseReplayValidated" ||
		replayEvents[2] != "DataReleaseOutboxRepair|count=2" {
		t.Fatalf("repair replay claimed activation: %#v", replayEvents)
	}
}
