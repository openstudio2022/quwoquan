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

const (
	releaseImportFailedBlocker              = "CONTENT.RELEASE.IMPORT_FAILED"
	ReleaseLegacyStateMigrationRequiredCode = "CONTENT.RELEASE.LEGACY_STATE_MIGRATION_REQUIRED"
)

type releaseStageReceipt struct {
	Environment            string    `bson:"environment"`
	SourceOwner            string    `bson:"sourceOwner"`
	ReleaseID              string    `bson:"releaseId"`
	ManifestDigest         string    `bson:"manifestDigest"`
	Stage                  string    `bson:"stage"`
	AttemptID              string    `bson:"attemptId"`
	Status                 string    `bson:"status"`
	RecordedAt             time.Time `bson:"recordedAt"`
	DurationMs             int64     `bson:"durationMs"`
	AttemptedCount         int       `bson:"attemptedCount"`
	SuccessCount           int       `bson:"successCount"`
	Checkpoint             string    `bson:"checkpoint"`
	FirstTypedBlocker      string    `bson:"firstTypedBlocker,omitempty"`
	ExpectedEmpty          bool      `bson:"expectedEmpty,omitempty"`
	ExpectedSourceOwner    string    `bson:"expectedSourceOwner,omitempty"`
	ExpectedReleaseID      string    `bson:"expectedReleaseId,omitempty"`
	ExpectedManifestDigest string    `bson:"expectedManifestDigest,omitempty"`
	ExpectedRevision       int64     `bson:"expectedRevision,omitempty"`
}

func releaseAttemptID(environment string, opts ImportOptions, requestedAt time.Time) string {
	return fmt.Sprintf(
		"%s:%s:%s:%d",
		strings.TrimSpace(environment),
		strings.TrimSpace(opts.SourceOwner),
		strings.TrimSpace(opts.ReleaseID),
		requestedAt.UTC().UnixNano(),
	)
}

func ensureReleaseControlIndexes(
	ctx context.Context,
	state *mongo.Collection,
	receipts *mongo.Collection,
) error {
	if err := inspectReleaseControlIndexes(ctx, state, receipts); err != nil {
		return err
	}
	candidatePartial := bson.D{{Key: "kind", Value: releaseCandidateKind}}
	pointerPartial := bson.D{{Key: "kind", Value: releaseActivePointerKind}}
	if _, err := state.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1},
				{Key: "kind", Value: 1}, {Key: "releaseId", Value: 1},
				{Key: "manifestDigest", Value: 1},
			},
			Options: options.Index().SetName("uq_data_release_state_environment_candidate").
				SetUnique(true).SetPartialFilterExpression(candidatePartial),
		},
		{
			Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "kind", Value: 1}},
			Options: options.Index().SetName("uq_data_release_state_active_pointer").
				SetUnique(true).SetPartialFilterExpression(pointerPartial),
		},
	}); err != nil {
		return fmt.Errorf("ensure Data release state indexes: %w", err)
	}
	if _, err := receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1},
				{Key: "stage", Value: 1}, {Key: "attemptId", Value: 1},
			},
			Options: options.Index().SetName("uq_data_release_stage_receipt_attempt").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1}, {Key: "recordedAt", Value: 1},
			},
			Options: options.Index().SetName("idx_data_release_stage_receipt_timeline"),
		},
	}); err != nil {
		return fmt.Errorf("ensure Data release stage receipt indexes: %w", err)
	}
	return nil
}

type releaseControlIndexExpectation struct {
	name    string
	keys    bson.D
	unique  bool
	partial bson.D
}

func inspectReleaseControlIndexes(
	ctx context.Context,
	state *mongo.Collection,
	receipts *mongo.Collection,
) error {
	expectations := map[*mongo.Collection][]releaseControlIndexExpectation{
		state: {
			{name: "uq_data_release_state_environment_candidate", keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "kind", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}}, unique: true, partial: bson.D{{Key: "kind", Value: releaseCandidateKind}}},
			{name: "uq_data_release_state_active_pointer", keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "kind", Value: int32(1)}}, unique: true, partial: bson.D{{Key: "kind", Value: releaseActivePointerKind}}},
		},
		receipts: {
			{name: "uq_data_release_stage_receipt_attempt", keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}, {Key: "stage", Value: int32(1)}, {Key: "attemptId", Value: int32(1)}}, unique: true},
			{name: "idx_data_release_stage_receipt_timeline", keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "recordedAt", Value: int32(1)}}},
		},
	}
	for collection, expectedIndexes := range expectations {
		cursor, err := collection.Indexes().List(ctx)
		if err != nil {
			return fmt.Errorf("inspect Data release control indexes: %w", err)
		}
		var indexes []struct {
			Name    string `bson:"name"`
			Key     bson.D `bson:"key"`
			Unique  bool   `bson:"unique"`
			Partial bson.D `bson:"partialFilterExpression"`
		}
		if err := cursor.All(ctx, &indexes); err != nil {
			return fmt.Errorf("decode Data release control indexes: %w", err)
		}
		for _, expected := range expectedIndexes {
			for _, actual := range indexes {
				if actual.Name != expected.name {
					continue
				}
				if !bsonDocumentsEqual(actual.Key, expected.keys) || actual.Unique != expected.unique ||
					!bsonDocumentsEqual(actual.Partial, expected.partial) {
					return fmt.Errorf("%s: incompatible existing index %s.%s requires explicit migration", ReleaseLegacyStateMigrationRequiredCode, collection.Name(), expected.name)
				}
			}
		}
	}
	return nil
}

func bsonDocumentsEqual(left, right bson.D) bool {
	return bsonValuesEqual(left, right)
}

func bsonValuesEqual(left, right any) bool {
	switch leftValue := left.(type) {
	case bson.D:
		rightValue, ok := right.(bson.D)
		if !ok || len(leftValue) != len(rightValue) {
			return false
		}
		for index := range leftValue {
			if leftValue[index].Key != rightValue[index].Key ||
				!bsonValuesEqual(leftValue[index].Value, rightValue[index].Value) {
				return false
			}
		}
		return true
	case bson.M:
		rightValue, ok := right.(bson.M)
		if !ok || len(leftValue) != len(rightValue) {
			return false
		}
		for key, value := range leftValue {
			rightItem, exists := rightValue[key]
			if !exists || !bsonValuesEqual(value, rightItem) {
				return false
			}
		}
		return true
	default:
		leftNumber, leftIsNumber := bsonNumericValue(left)
		rightNumber, rightIsNumber := bsonNumericValue(right)
		if leftIsNumber || rightIsNumber {
			return leftIsNumber && rightIsNumber && leftNumber == rightNumber
		}
		return fmt.Sprint(left) == fmt.Sprint(right)
	}
}

func bsonNumericValue(value any) (float64, bool) {
	switch number := value.(type) {
	case int:
		return float64(number), true
	case int32:
		return float64(number), true
	case int64:
		return float64(number), true
	case float32:
		return float64(number), true
	case float64:
		return number, true
	default:
		return 0, false
	}
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
		strings.TrimSpace(receipt.SourceOwner) == "" ||
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

func readLatestReleaseStageReceipt(
	ctx context.Context,
	receipts *mongo.Collection,
	environment string,
	sourceOwner string,
	releaseID string,
	recordedAt time.Time,
) (releaseStageReceipt, error) {
	var receipt releaseStageReceipt
	err := receipts.FindOne(
		ctx,
		bson.M{
			"environment": environment, "sourceOwner": sourceOwner,
			"releaseId": releaseID, "recordedAt": bson.M{"$lte": recordedAt},
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
