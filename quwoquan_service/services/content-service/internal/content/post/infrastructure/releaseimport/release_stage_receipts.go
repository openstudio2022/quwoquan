package releaseimport

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const releaseImportFailedBlocker = "CONTENT.RELEASE.IMPORT_FAILED"

type releaseStageReceipt struct {
	Environment       string    `bson:"environment"`
	ReleaseID         string    `bson:"releaseId"`
	ManifestDigest    string    `bson:"manifestDigest"`
	Stage             string    `bson:"stage"`
	AttemptID         string    `bson:"attemptId"`
	Status            string    `bson:"status"`
	RecordedAt        time.Time `bson:"recordedAt"`
	DurationMs        int64     `bson:"durationMs"`
	AttemptedCount    int       `bson:"attemptedCount"`
	SuccessCount      int       `bson:"successCount"`
	Checkpoint        string    `bson:"checkpoint"`
	FirstTypedBlocker string    `bson:"firstTypedBlocker,omitempty"`
}

func releaseAttemptID(environment string, opts ImportOptions, requestedAt time.Time) string {
	return fmt.Sprintf(
		"%s:%s:%d",
		strings.TrimSpace(environment),
		strings.TrimSpace(opts.ReleaseID),
		requestedAt.UTC().UnixNano(),
	)
}

func ensureReleaseControlIndexes(
	ctx context.Context,
	state *mongo.Collection,
	receipts *mongo.Collection,
) error {
	if _, err := state.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "environment", Value: 1},
				{Key: "releaseId", Value: 1},
				{Key: "manifestDigest", Value: 1},
			},
			Options: options.Index().
				SetName("uq_data_release_state_environment_candidate").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "environment", Value: 1},
				{Key: "status", Value: 1},
				{Key: "activatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_data_release_state_active_pointer"),
		},
	}); err != nil {
		return fmt.Errorf("ensure Data release state indexes: %w", err)
	}
	if _, err := receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "environment", Value: 1},
				{Key: "releaseId", Value: 1},
				{Key: "manifestDigest", Value: 1},
				{Key: "stage", Value: 1},
				{Key: "attemptId", Value: 1},
			},
			Options: options.Index().
				SetName("uq_data_release_stage_receipt_attempt").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "environment", Value: 1},
				{Key: "releaseId", Value: 1},
				{Key: "recordedAt", Value: 1},
			},
			Options: options.Index().SetName("idx_data_release_stage_receipt_timeline"),
		},
	}); err != nil {
		return fmt.Errorf("ensure Data release stage receipt indexes: %w", err)
	}
	return nil
}

func appendReleaseStageReceipt(
	ctx context.Context,
	receipts *mongo.Collection,
	receipt releaseStageReceipt,
) error {
	if receipts == nil {
		return fmt.Errorf("Data release stage receipt collection is required")
	}
	if strings.TrimSpace(receipt.Environment) == "" ||
		strings.TrimSpace(receipt.ReleaseID) == "" ||
		strings.TrimSpace(receipt.ManifestDigest) == "" ||
		strings.TrimSpace(receipt.Stage) == "" ||
		strings.TrimSpace(receipt.AttemptID) == "" ||
		strings.TrimSpace(receipt.Status) == "" ||
		receipt.RecordedAt.IsZero() {
		return fmt.Errorf("Data release stage receipt identity is incomplete")
	}
	if receipt.DurationMs < 0 || receipt.AttemptedCount < 0 ||
		receipt.SuccessCount < 0 || receipt.SuccessCount > receipt.AttemptedCount {
		return fmt.Errorf("Data release stage receipt counts are invalid")
	}
	if _, err := receipts.InsertOne(ctx, receipt); err != nil {
		return fmt.Errorf("append Data release %s stage receipt: %w", receipt.Stage, err)
	}
	return nil
}

// readLatestReleaseStageReceipt exercises the object-owned timeline index and
// attests that the create-once prepared receipt is durable before mutations.
func readLatestReleaseStageReceipt(
	ctx context.Context,
	receipts *mongo.Collection,
	environment string,
	releaseID string,
	recordedAt time.Time,
) (releaseStageReceipt, error) {
	var receipt releaseStageReceipt
	err := receipts.FindOne(
		ctx,
		bson.M{
			"environment": environment,
			"releaseId":   releaseID,
			"recordedAt":  bson.M{"$lte": recordedAt},
		},
		options.FindOne().SetSort(bson.D{{Key: "recordedAt", Value: -1}}),
	).Decode(&receipt)
	if err != nil {
		return releaseStageReceipt{}, fmt.Errorf("read Data release receipt timeline: %w", err)
	}
	return receipt, nil
}

func releaseStageDurationMs(started time.Time) int64 {
	duration := time.Since(started).Milliseconds()
	if duration < 0 {
		return 0
	}
	return duration
}
