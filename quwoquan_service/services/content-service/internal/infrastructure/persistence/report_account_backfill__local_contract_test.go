package persistence

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadReporterAccountBackfillsAcceptsCanonicalVerifiedArtifact(t *testing.T) {
	t.Parallel()

	path := filepath.Join(t.TempDir(), "report-account-backfill.json")
	if err := os.WriteFile(path, []byte(`{
  "kind": "content.reporter_account_backfill",
  "entries": [{"reporterId": "persona-1", "accountId": "account-1"}]
}`), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}

	entries, err := LoadReporterAccountBackfills(path)
	if err != nil {
		t.Fatalf("LoadReporterAccountBackfills() error = %v", err)
	}
	if len(entries) != 1 || entries[0].ReporterID != "persona-1" ||
		entries[0].AccountID != "account-1" {
		t.Fatalf("entries = %#v, want canonical verified mapping", entries)
	}
}

func TestReporterAccountBackfillsRejectConflictingOrUnclassifiedIdentityInput(t *testing.T) {
	t.Parallel()

	if _, err := normalizeReporterAccountBackfills([]ReporterAccountBackfill{
		{ReporterID: "persona-1", AccountID: "account-1"},
		{ReporterID: "persona-1", AccountID: "account-2"},
	}); err == nil {
		t.Fatal("conflicting reporter ownership must fail closed")
	}

	path := filepath.Join(t.TempDir(), "unclassified-backfill.json")
	if err := os.WriteFile(path, []byte(`{"entries":[]}`), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
	if _, err := LoadReporterAccountBackfills(path); err == nil {
		t.Fatal("artifact without a canonical kind must fail closed")
	}
}
