// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
package releaseimport_test

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func legacyMigrationArgs(report string) []string {
	return []string{
		"--mongo-uri", "mongodb://operator:secret@127.0.0.1:27017/?authSource=admin",
		"--database", "quwoquan_content", "--env", "alpha", "--source-owner", "qwq_data",
		"--expected-release-id", "release-research-1",
		"--expected-manifest-digest", "sha256:" + strings.Repeat("a", 64),
		"--expected-release-class", "research", "--expected-projection-version", "7",
		"--expected-activated-at", "2026-09-05T08:00:00.123Z",
		"--expected-legacy-index-set", releaseimport.LegacyReleaseStateIndexSetV1,
		"--expected-legacy-receipt-index-set", releaseimport.LegacyReleaseStageReceiptIndexSetV1,
		"--expected-receipt-count", "5",
		"--report", report,
	}
}

func TestParseLegacyReleaseStateMigrationCommandRequiresExactCurrentBinding(t *testing.T) {
	command, err := releaseimport.ParseLegacyReleaseStateMigrationCommand(legacyMigrationArgs("receipt.json"))
	if err != nil {
		t.Fatal(err)
	}
	if command.Database != "quwoquan_content" || command.Expected.Environment != "alpha" ||
		command.Expected.SourceOwner != "qwq_data" || command.Expected.ProjectionVersion != 7 ||
		command.Expected.AllowReplay || command.Expected.ActivatedAt.Nanosecond() != 123000000 {
		t.Fatalf("parsed migration command fields drifted")
	}

	invalid := [][]string{
		append(legacyMigrationArgs("receipt.json"), "positional"),
		removeLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-release-id"),
		replaceLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-manifest-digest", "not-a-digest"),
		replaceLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-release-class", "internal"),
		replaceLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-projection-version", "0"),
		replaceLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-activated-at", "yesterday"),
		replaceLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-legacy-index-set", "guess"),
		replaceLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-legacy-receipt-index-set", "guess"),
		removeLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-receipt-count"),
		replaceLegacyMigrationFlag(legacyMigrationArgs("receipt.json"), "--expected-receipt-count", "-1"),
	}
	for _, args := range invalid {
		if _, err := releaseimport.ParseLegacyReleaseStateMigrationCommand(args); err == nil {
			t.Fatalf("invalid migration command accepted: %#v", args)
		}
	}
}

func TestRunLegacyReleaseStateMigrationRequiresQuiescenceBeforeMongoAccess(t *testing.T) {
	report := filepath.Join(t.TempDir(), "receipt.json")
	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", "")
	t.Setenv("QWQ_CONTENT_RELEASE_STATE_QUIESCED", "")
	err := releaseimport.RunLegacyReleaseStateMigration(t.Context(), legacyMigrationArgs(report))
	if err == nil || !strings.Contains(err.Error(), "QWQ_STORAGE_MIGRATION_MODE=quiesced_atomic") {
		t.Fatalf("missing migration mode error=%v", err)
	}
	if _, statErr := os.Lstat(report); !os.IsNotExist(statErr) {
		t.Fatalf("failed precondition created receipt: %v", statErr)
	}

	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", releaseimport.QuiescedAtomicStorageMigrationMode)
	err = releaseimport.RunLegacyReleaseStateMigration(t.Context(), legacyMigrationArgs(report))
	if err == nil || !strings.Contains(err.Error(), "QWQ_CONTENT_RELEASE_STATE_QUIESCED=confirmed") {
		t.Fatalf("missing quiescence confirmation error=%v", err)
	}
}

func TestLegacyReleaseStateMigrationRedactsMongoURIFromConnectionErrors(t *testing.T) {
	report := filepath.Join(t.TempDir(), "receipt.json")
	secretURI := "mongodb://operator:do-not-log-me@127.0.0.1:1/?serverSelectionTimeoutMS=20"
	args := removeLegacyMigrationFlag(legacyMigrationArgs(report), "--mongo-uri")
	t.Setenv("MONGO_URI", secretURI)
	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", releaseimport.QuiescedAtomicStorageMigrationMode)
	t.Setenv("QWQ_CONTENT_RELEASE_STATE_QUIESCED", releaseimport.ContentReleaseStateQuiescedConfirmation)
	ctx, cancel := context.WithTimeout(t.Context(), 100*time.Millisecond)
	defer cancel()
	err := releaseimport.RunLegacyReleaseStateMigration(ctx, args)
	if err == nil {
		t.Fatal("unreachable MongoDB unexpectedly succeeded")
	}
	message := err.Error()
	if strings.Contains(message, secretURI) || strings.Contains(message, "do-not-log-me") || strings.Contains(message, "operator") {
		t.Fatalf("Mongo connection error leaked URI credentials: %s", message)
	}
	if _, statErr := os.Lstat(report); !os.IsNotExist(statErr) {
		t.Fatalf("failed Mongo connection created receipt: %v", statErr)
	}
}

func TestLegacyReleaseStateMigrationRefusesExistingReceiptBeforeMongoAccess(t *testing.T) {
	report := filepath.Join(t.TempDir(), "receipt.json")
	if err := os.WriteFile(report, []byte("do not overwrite\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", releaseimport.QuiescedAtomicStorageMigrationMode)
	t.Setenv("QWQ_CONTENT_RELEASE_STATE_QUIESCED", releaseimport.ContentReleaseStateQuiescedConfirmation)
	err := releaseimport.RunLegacyReleaseStateMigration(t.Context(), legacyMigrationArgs(report))
	if err == nil || !strings.Contains(err.Error(), "already exists") {
		t.Fatalf("existing receipt was not rejected: %v", err)
	}
	contents, readErr := os.ReadFile(report)
	if readErr != nil || string(contents) != "do not overwrite\n" {
		t.Fatalf("existing receipt changed: %q err=%v", contents, readErr)
	}
}

func TestLegacyReleaseStateIndexDigestsAreStableAndDistinct(t *testing.T) {
	legacy := releaseimport.LegacyReleaseStateExpectedIndexDigest()
	current := releaseimport.CurrentReleaseStateExpectedIndexDigest()
	legacyReceipts := releaseimport.LegacyReleaseStageReceiptExpectedIndexDigest()
	currentReceipts := releaseimport.CurrentReleaseStageReceiptExpectedIndexDigest()
	for label, digest := range map[string]string{
		"legacy": legacy, "current": current,
		"legacy receipts": legacyReceipts, "current receipts": currentReceipts,
	} {
		if !strings.HasPrefix(digest, "sha256:") || len(digest) != 71 {
			t.Fatalf("%s index digest is non-canonical: %q", label, digest)
		}
	}
	if legacy == current || legacyReceipts == currentReceipts {
		t.Fatal("legacy and current index digests must differ")
	}
}

func removeLegacyMigrationFlag(args []string, name string) []string {
	result := append([]string(nil), args...)
	for index := range result {
		if result[index] == name {
			return append(result[:index], result[index+2:]...)
		}
	}
	return result
}

func replaceLegacyMigrationFlag(args []string, name, value string) []string {
	result := append([]string(nil), args...)
	for index := range result {
		if result[index] == name {
			result[index+1] = value
			return result
		}
	}
	return result
}
