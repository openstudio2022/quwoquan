// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
package releaseimport_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestRetiredContentTypeMigrationClassification(t *testing.T) {
	emptyDocument, err := bson.Marshal(bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name string
		row  releaseimport.RetiredContentTypePostRow
		want releaseimport.RetiredContentTypeOutcome
	}{
		{"video_without_legacy_url", releaseimport.RetiredContentTypePostRow{MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "video"}}}, releaseimport.RetiredContentTypeMigratedVideo},
		{"video_and_image", releaseimport.RetiredContentTypePostRow{MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "image"}, {Kind: "video"}}}, releaseimport.RetiredContentTypeMigratedVideo},
		{"image_with_caption", releaseimport.RetiredContentTypePostRow{MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "image"}}, Body: "caption"}, releaseimport.RetiredContentTypeMigratedImage},
		{"legacy_video", releaseimport.RetiredContentTypePostRow{VideoURL: "https://example.test/video"}, releaseimport.RetiredContentTypeMigratedVideo},
		{"legacy_image", releaseimport.RetiredContentTypePostRow{MediaURLs: []string{"", "https://example.test/image"}}, releaseimport.RetiredContentTypeMigratedImage},
		{"plain_text", releaseimport.RetiredContentTypePostRow{Body: "text"}, releaseimport.RetiredContentTypeMigratedArticle},
		{"markdown", releaseimport.RetiredContentTypePostRow{ArticleMarkdown: "article"}, releaseimport.RetiredContentTypeMigratedArticle},
		{"empty", releaseimport.RetiredContentTypePostRow{}, releaseimport.RetiredContentTypeBlockedUnclassifiable},
		{"empty_semantic_envelope", releaseimport.RetiredContentTypePostRow{SemanticDocument: emptyDocument}, releaseimport.RetiredContentTypeBlockedUnclassifiable},
		{"image_contradicts_video_url", releaseimport.RetiredContentTypePostRow{MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "image"}}, VideoURL: "video"}, releaseimport.RetiredContentTypeBlockedConflict},
		{"unknown_media_kind", releaseimport.RetiredContentTypePostRow{MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "audio"}}, Body: "text"}, releaseimport.RetiredContentTypeBlockedConflict},
		{"mixed_unknown_media_kind", releaseimport.RetiredContentTypePostRow{MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "video"}, {Kind: "future"}}}, releaseimport.RetiredContentTypeBlockedConflict},
		{"markdown_with_media_requires_adjudication", releaseimport.RetiredContentTypePostRow{ArticleMarkdown: "article", MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "image"}}}, releaseimport.RetiredContentTypeBlockedConflict},
		{"semantic_document_with_media_requires_adjudication", releaseimport.RetiredContentTypePostRow{SemanticDocument: emptyDocument, VideoURL: "video"}, releaseimport.RetiredContentTypeBlockedConflict},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			tc.row.ContentType = "micro"
			if got := releaseimport.ClassifyRetiredContentType(tc.row); got != tc.want {
				t.Fatalf("got %s; want %s", got, tc.want)
			}
		})
	}
}

func TestRetiredContentTypeMigrationNeverClassifiesFutureOrCanonicalTypes(t *testing.T) {
	for _, kind := range []string{"future", "audio", "", " micro", "MICRO", "image", "video", "article"} {
		row := releaseimport.RetiredContentTypePostRow{ContentType: kind, Body: "text", VideoURL: "video", MediaItems: []releaseimport.RetiredContentTypeMediaRow{{Kind: "video"}}}
		if got := releaseimport.ClassifyRetiredContentType(row); got != releaseimport.RetiredContentTypeBlockedUnknownType {
			t.Fatalf("type %q was classified: %s", kind, got)
		}
	}
}

func TestRetiredContentTypeMigrationRetriesRemainBlockedWithoutCanonicalRecovery(t *testing.T) {
	// 不配置 client，不接触 provider；入口必须在任何 Mongo 操作前 fail-closed。
	db := &mongo.Database{}
	for range 2 {
		result, err := releaseimport.MigrateRetiredContentTypes(t.Context(), db)
		if !errors.Is(err, releaseimport.ErrRetiredContentTypeProjectionRecoveryRequired) {
			t.Fatalf("error=%v", err)
		}
		if result.Scanned != 0 || result.Migrated != 0 || result.Blocked != 0 || len(result.ByOutcome) != 0 {
			t.Fatalf("fabricated results: %+v", result)
		}
	}
	if _, err := releaseimport.MigrateRetiredContentTypes(context.Background(), nil); err == nil {
		t.Fatal("nil database accepted")
	}
	if _, err := releaseimport.MigrateRetiredContentTypes(nil, db); err == nil {
		t.Fatal("nil context accepted")
	}
}

func retiredMigrationDirectory(t *testing.T) string {
	t.Helper()
	path, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return path
}

func retiredMigrationArgs(report string) []string {
	return []string{"--mongo-uri", "mongodb://operator:never-log-secret@example.invalid", "--database", "content_test", "--report", report}
}

func retiredMigrationQuiescence(t *testing.T) {
	t.Helper()
	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", releaseimport.QuiescedAtomicStorageMigrationMode)
	t.Setenv("QWQ_CONTENT_POSTS_QUIESCED", releaseimport.RetiredContentTypeQuiescedConfirmation)
}

func TestRetiredContentTypeMigrationFailureReceiptAndConflict(t *testing.T) {
	retiredMigrationQuiescence(t)
	report := filepath.Join(retiredMigrationDirectory(t), "receipt.json")
	err := releaseimport.RunRetiredContentTypeMigration(t.Context(), retiredMigrationArgs(report))
	if err != releaseimport.ErrRetiredContentTypeProjectionRecoveryRequired {
		t.Fatalf("error=%v", err)
	}
	before, err := os.ReadFile(report)
	if err != nil {
		t.Fatal(err)
	}
	var receipt releaseimport.RetiredContentTypeMigrationReceipt
	if err := json.Unmarshal(before, &receipt); err != nil {
		t.Fatal(err)
	}
	if receipt.Status != "blocked" || receipt.FirstTypedBlocker != "canonical_projection_recovery_required" || receipt.Migrated != 0 || receipt.Scanned != 0 {
		t.Fatalf("receipt=%+v", receipt)
	}
	for _, secret := range []string{"operator", "never-log-secret", "mongodb://", "invalid.test"} {
		if bytes.Contains(before, []byte(secret)) {
			t.Fatalf("receipt leaked %q", secret)
		}
	}
	if err := releaseimport.RunRetiredContentTypeMigration(t.Context(), retiredMigrationArgs(report)); err == nil || !strings.Contains(err.Error(), "already exists") {
		t.Fatalf("conflict=%v", err)
	}
	after, err := os.ReadFile(report)
	if err != nil || !bytes.Equal(before, after) {
		t.Fatalf("conflict changed receipt: %v", err)
	}
	info, err := os.Stat(report)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("receipt permissions: %v %v", info, err)
	}
}

func TestRetiredContentTypeMigrationReceiptAtomicCreateOnce(t *testing.T) {
	retiredMigrationQuiescence(t)
	dir := retiredMigrationDirectory(t)
	// 通过公开入口并发竞争同一槽位；不注入私有预检钩子，不扩大生产 API。
	// 唯一成功写回执者仍必须返回恢复协议阻断，而非迁移成功。
	for round := range 4 {
		path := filepath.Join(dir, fmt.Sprintf("race-%d.json", round))
		start := make(chan struct{})
		type attempt struct {
			database string
			err      error
		}
		const writers = 16
		results := make(chan attempt, writers)
		for writer := range writers {
			go func() {
				args := retiredMigrationArgs(path)
				args[3] = fmt.Sprintf("writer_%d", writer)
				<-start
				results <- attempt{args[3], releaseimport.RunRetiredContentTypeMigration(t.Context(), args)}
			}()
		}
		close(start)
		winner := ""
		for range writers {
			result := <-results
			switch {
			case result.err == releaseimport.ErrRetiredContentTypeProjectionRecoveryRequired:
				if winner != "" {
					t.Errorf("multiple successful receipt writers: %s and %s", winner, result.database)
				}
				winner = result.database
			case errors.Is(result.err, os.ErrExist):
				// 已通过预检的竞争写者在原子 create-once 处失败。
			case result.err != nil && strings.Contains(result.err.Error(), "already exists"):
				// 较晚到达的竞争写者在公开入口预检处失败。
			default:
				t.Errorf("unexpected migration outcome: %v", result.err)
			}
		}
		if winner == "" {
			t.Fatal("no successful receipt writer")
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var receipt releaseimport.RetiredContentTypeMigrationReceipt
		if err := json.Unmarshal(raw, &receipt); err != nil {
			t.Fatalf("partial/overwritten receipt: %v", err)
		}
		if receipt.Database != winner || receipt.Status != "blocked" || receipt.FirstTypedBlocker != "canonical_projection_recovery_required" || receipt.Migrated != 0 {
			t.Fatalf("receipt does not match blocked winner %s: %+v", winner, receipt)
		}
	}
}

func TestRetiredContentTypeMigrationRefusesSymlinkReceipts(t *testing.T) {
	retiredMigrationQuiescence(t)
	dir := retiredMigrationDirectory(t)
	target := filepath.Join(dir, "untouched.json")
	if err := os.WriteFile(target, []byte("unchanged"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "receipt.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if err := releaseimport.RunRetiredContentTypeMigration(t.Context(), retiredMigrationArgs(link)); err == nil || !strings.Contains(err.Error(), "already exists") {
		t.Fatalf("symlink error=%v", err)
	}
	raw, err := os.ReadFile(target)
	if err != nil || string(raw) != "unchanged" {
		t.Fatalf("symlink target changed: %v", err)
	}
	ancestor := filepath.Join(dir, "ancestor")
	if err := os.Symlink(dir, ancestor); err != nil {
		t.Fatal(err)
	}
	if err := releaseimport.RunRetiredContentTypeMigration(t.Context(), retiredMigrationArgs(filepath.Join(ancestor, "new.json"))); err == nil || !strings.Contains(err.Error(), "non-symlink directory") {
		t.Fatalf("symlink ancestor error=%v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "new.json")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("symlink ancestor created receipt: %v", err)
	}
}

func TestRetiredContentTypeMigrationCommandPreconditions(t *testing.T) {
	report := filepath.Join(retiredMigrationDirectory(t), "receipt.json")
	args := retiredMigrationArgs(report)
	if _, err := releaseimport.ParseRetiredContentTypeMigrationCommand(append(args, "extra")); err == nil {
		t.Fatal("positional argument accepted")
	}
	if _, err := releaseimport.ParseRetiredContentTypeMigrationCommand(nil); err == nil {
		t.Fatal("empty args accepted")
	}
	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", "")
	t.Setenv("QWQ_CONTENT_POSTS_QUIESCED", "")
	if err := releaseimport.RunRetiredContentTypeMigration(t.Context(), args); err == nil || !strings.Contains(err.Error(), "QWQ_STORAGE_MIGRATION_MODE") {
		t.Fatalf("mode error=%v", err)
	}
	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", releaseimport.QuiescedAtomicStorageMigrationMode)
	if err := releaseimport.RunRetiredContentTypeMigration(t.Context(), args); err == nil || !strings.Contains(err.Error(), "QWQ_CONTENT_POSTS_QUIESCED") {
		t.Fatalf("confirmation error=%v", err)
	}
	if _, err := os.Stat(report); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("preconditions wrote receipt: %v", err)
	}
}
