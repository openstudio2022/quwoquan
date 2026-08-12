// Command migrate-media-processing-dead-letter-indexes removes retired
// MediaAsset dead-letter secondary indexes in a quiesced storage migration.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
)

const quiescedAtomicMigrationMode = "quiesced_atomic"

type migrationReport struct {
	Schema               string   `json:"schema"`
	Status               string   `json:"status"`
	Database             string   `json:"database"`
	MigrationMode        string   `json:"migrationMode"`
	ExpectedDropCount    int      `json:"expectedDropCount"`
	DroppedIndexes       []string `json:"droppedIndexes"`
	RetiredIndexesAbsent bool     `json:"retiredIndexesAbsent"`
}

func main() {
	expectedDropCount := flag.Int(
		"expected-drop-count",
		-1,
		"exact retired index count expected to be removed (0 for replay, 2 for first migration)",
	)
	reportPath := flag.String(
		"report",
		"",
		"create-once JSON migration report path",
	)
	flag.Parse()
	if *expectedDropCount < 0 {
		log.Fatal(
			"media processing dead-letter index migration expected drop count must be non-negative",
		)
	}
	if strings.TrimSpace(*reportPath) == "" {
		log.Fatal("media processing dead-letter index migration requires --report")
	}
	if mode := strings.TrimSpace(os.Getenv("QWQ_STORAGE_MIGRATION_MODE")); mode != quiescedAtomicMigrationMode {
		log.Fatalf(
			"media processing dead-letter index migration requires QWQ_STORAGE_MIGRATION_MODE=%s",
			quiescedAtomicMigrationMode,
		)
	}
	mongoURI := strings.TrimSpace(os.Getenv("MONGO_URI"))
	databaseName := strings.TrimSpace(os.Getenv("CONTENT_MONGO_DATABASE"))
	if mongoURI == "" || databaseName == "" {
		log.Fatal("media processing dead-letter index migration requires MONGO_URI and CONTENT_MONGO_DATABASE")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	client, err := mongo.Connect(options.Client().ApplyURI(mongoURI))
	if err != nil {
		log.Fatalf("connect MongoDB: %v", err)
	}
	defer client.Disconnect(context.Background())
	if err := client.Ping(ctx, nil); err != nil {
		log.Fatalf("ping MongoDB: %v", err)
	}

	result, err := mediaassetpersistence.NewMongoMediaStore(
		client.Database(databaseName),
	).MigrateRetiredProcessingDeadLetterIndexes(ctx, *expectedDropCount)
	if err != nil {
		log.Fatalf("migrate media processing dead-letter indexes: %v", err)
	}
	if err := writeMigrationReport(*reportPath, migrationReport{
		Schema:               "quwoquan.content.media_processing_dead_letter_index_migration.v1",
		Status:               "passed",
		Database:             databaseName,
		MigrationMode:        quiescedAtomicMigrationMode,
		ExpectedDropCount:    *expectedDropCount,
		DroppedIndexes:       result.DroppedIndexes,
		RetiredIndexesAbsent: true,
	}); err != nil {
		log.Fatalf("write media processing dead-letter index migration report: %v", err)
	}
	log.Printf(
		"OK: media processing dead-letter retired indexes absent; database=%s dropped=%v",
		databaseName,
		result.DroppedIndexes,
	)
}

func writeMigrationReport(path string, report migrationReport) error {
	resolved := filepath.Clean(strings.TrimSpace(path))
	if resolved == "." || resolved == string(filepath.Separator) {
		return fmt.Errorf("migration report path is invalid")
	}
	encoded, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return fmt.Errorf("encode migration report: %w", err)
	}
	encoded = append(encoded, '\n')
	file, err := os.OpenFile(resolved, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create migration report: %w", err)
	}
	if _, err := file.Write(encoded); err != nil {
		_ = file.Close()
		return fmt.Errorf("write migration report: %w", err)
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return fmt.Errorf("sync migration report: %w", err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close migration report: %w", err)
	}
	return nil
}
