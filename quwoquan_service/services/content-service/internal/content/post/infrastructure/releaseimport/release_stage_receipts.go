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
	CandidateRevision int64     `bson:"candidateRevision,omitempty"`
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
	if err := attestReleaseStateDocuments(ctx, state); err != nil {
		return err
	}
	if _, err := state.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "environment", Value: 1},
				{Key: "sourceOwner", Value: 1},
			},
			Options: options.Index().
				SetName("uq_data_release_state_environment_source_owner").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "environment", Value: 1},
				{Key: "sourceOwner", Value: 1},
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

type releaseStateIdentityCount struct {
	ID struct {
		Environment string `bson:"environment"`
		SourceOwner string `bson:"sourceOwner"`
	} `bson:"_id"`
	Count int64 `bson:"count"`
}

func attestReleaseStateDocuments(ctx context.Context, state *mongo.Collection) error {
	if state == nil {
		return fmt.Errorf("Data release state collection is required")
	}
	existingIndexes, err := state.Indexes().List(ctx)
	if err != nil {
		return fmt.Errorf("list Data release state indexes: %w", err)
	}
	defer existingIndexes.Close(ctx)
	for existingIndexes.Next(ctx) {
		var index struct {
			Name   string `bson:"name"`
			Unique bool   `bson:"unique"`
			Key    bson.D `bson:"key"`
		}
		if err := existingIndexes.Decode(&index); err != nil {
			return fmt.Errorf("decode Data release state index: %w", err)
		}
		if index.Name == "uq_data_release_state_environment_source_owner" &&
			(!index.Unique || !releaseStateAuthorityIndexKeys(index.Key)) {
			return fmt.Errorf(
				"GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_INDEX_DRIFT: index=%q must be unique on environment+sourceOwner",
				index.Name,
			)
		}
	}
	if err := existingIndexes.Err(); err != nil {
		return fmt.Errorf("scan Data release state indexes: %w", err)
	}
	invalidCount, err := state.CountDocuments(ctx, bson.M{"$or": bson.A{
		bson.M{"environment": bson.M{"$not": bson.M{"$type": "string"}}},
		bson.M{"environment": ""},
		bson.M{"sourceOwner": bson.M{"$not": bson.M{"$type": "string"}}},
		bson.M{"sourceOwner": ""},
		bson.M{"revision": bson.M{"$not": bson.M{"$type": "long"}}},
		bson.M{"revision": bson.M{"$lte": int64(0)}},
		bson.M{"sourceVersion": bson.M{"$not": bson.M{"$type": "long"}}},
		bson.M{"sourceVersion": bson.M{"$lte": int64(0)}},
	}})
	if err != nil {
		return fmt.Errorf("attest Data release state schema: %w", err)
	}
	if invalidCount != 0 {
		return fmt.Errorf(
			"GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_MIGRATION_REQUIRED: invalidDocuments=%d; backfill revision/sourceVersion through the governed migration before index creation",
			invalidCount,
		)
	}
	cursor, err := state.Aggregate(ctx, mongo.Pipeline{
		{{Key: "$group", Value: bson.D{
			{Key: "_id", Value: bson.D{
				{Key: "environment", Value: "$environment"},
				{Key: "sourceOwner", Value: "$sourceOwner"},
			}},
			{Key: "count", Value: bson.D{{Key: "$sum", Value: 1}}},
		}}},
		{{Key: "$match", Value: bson.D{{Key: "count", Value: bson.D{{Key: "$gt", Value: 1}}}}}},
		{{Key: "$limit", Value: 1}},
	})
	if err != nil {
		return fmt.Errorf("attest Data release state uniqueness: %w", err)
	}
	defer cursor.Close(ctx)
	if cursor.Next(ctx) {
		var duplicate releaseStateIdentityCount
		if err := cursor.Decode(&duplicate); err != nil {
			return fmt.Errorf("decode duplicate Data release state identity: %w", err)
		}
		return fmt.Errorf(
			"GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_DUPLICATE: environment=%q sourceOwner=%q count=%d; resolve duplicates through the governed migration before index creation",
			duplicate.ID.Environment, duplicate.ID.SourceOwner, duplicate.Count,
		)
	}
	if err := cursor.Err(); err != nil {
		return fmt.Errorf("scan duplicate Data release state identities: %w", err)
	}
	return nil
}

func releaseStateAuthorityIndexKeys(keys bson.D) bool {
	if len(keys) != 2 {
		return false
	}
	keyValueIsOne := func(value any) bool {
		switch numeric := value.(type) {
		case int32:
			return numeric == 1
		case int64:
			return numeric == 1
		case float64:
			return numeric == 1
		default:
			return false
		}
	}
	return keys[0].Key == "environment" && keyValueIsOne(keys[0].Value) &&
		keys[1].Key == "sourceOwner" && keyValueIsOne(keys[1].Value)
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
