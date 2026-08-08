package reliabletaskmongo

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/runtime/reliabletask"
)

type dataContentCheckpointDocument struct {
	ID             string `bson:"_id"`
	ExecutionID    string `bson:"executionId"`
	Stage          string `bson:"stage"`
	PartitionKey   string `bson:"partitionKey"`
	JobSetDigest   string `bson:"jobSetDigest"`
	CursorJobID    string `bson:"cursorJobId"`
	CompletedCount int    `bson:"completedCount"`
}

func dataContentCheckpointID(value reliabletask.DataContentPartitionCheckpoint) string {
	return strings.Join([]string{value.ExecutionID, value.Stage, value.PartitionKey}, "|")
}

func validateDataContentCheckpoint(value reliabletask.DataContentPartitionCheckpoint) error {
	if strings.TrimSpace(value.ExecutionID) == "" ||
		(value.Stage != "author" && value.Stage != "publish") ||
		strings.TrimSpace(value.PartitionKey) == "" ||
		!reliabletask.ValidSHA256Digest(value.JobSetDigest) ||
		strings.TrimSpace(value.CursorJobID) == "" ||
		value.CompletedCount < 1 || value.FlushedAt.IsZero() {
		return fmt.Errorf("data content partition checkpoint identity is invalid")
	}
	return nil
}

// FlushDataContentPartitionCheckpoint advances one Mongo watermark. The
// job-set digest is part of the update predicate, so a stale controller cannot
// overwrite a checkpoint after a new immutable attempt owns the partition.
func (s *DataContentStore) FlushDataContentPartitionCheckpoint(
	ctx context.Context,
	checkpoint reliabletask.DataContentPartitionCheckpoint,
) error {
	if err := validateDataContentCheckpoint(checkpoint); err != nil {
		return err
	}
	id := dataContentCheckpointID(checkpoint)
	filter := bson.M{
		"_id":            id,
		"jobSetDigest":   checkpoint.JobSetDigest,
		"completedCount": bson.M{"$lte": checkpoint.CompletedCount},
	}
	update := bson.M{"$set": bson.M{
		"cursorJobId":    checkpoint.CursorJobID,
		"completedCount": checkpoint.CompletedCount,
		"flushedAt":      checkpoint.FlushedAt.UTC(),
	}}
	result, err := s.dataContentCheckpoints.UpdateOne(ctx, filter, update)
	if err != nil {
		return fmt.Errorf("flush data content partition checkpoint: %w", err)
	}
	if result.MatchedCount == 1 {
		return nil
	}
	document := bson.M{
		"_id":            id,
		"executionId":    checkpoint.ExecutionID,
		"stage":          checkpoint.Stage,
		"partitionKey":   checkpoint.PartitionKey,
		"jobSetDigest":   checkpoint.JobSetDigest,
		"cursorJobId":    checkpoint.CursorJobID,
		"completedCount": checkpoint.CompletedCount,
		"flushedAt":      checkpoint.FlushedAt.UTC(),
	}
	if _, err := s.dataContentCheckpoints.InsertOne(ctx, document); err == nil {
		return nil
	} else if !mongo.IsDuplicateKeyError(err) {
		return fmt.Errorf("create data content partition checkpoint: %w", err)
	}
	var existing dataContentCheckpointDocument
	if err := s.dataContentCheckpoints.FindOne(ctx, bson.M{"_id": id}).Decode(&existing); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return fmt.Errorf("data content partition checkpoint collision disappeared")
		}
		return fmt.Errorf("load data content partition checkpoint collision: %w", err)
	}
	if existing.JobSetDigest != checkpoint.JobSetDigest {
		return fmt.Errorf("DATA.RELIABLETASK.STALE_FENCE: partition checkpoint jobSetDigest drift")
	}
	return fmt.Errorf("DATA.RELIABLETASK.STALE_CHECKPOINT: partition checkpoint cannot move backwards")
}

var _ reliabletask.DataContentCheckpointStore = (*DataContentStore)(nil)
