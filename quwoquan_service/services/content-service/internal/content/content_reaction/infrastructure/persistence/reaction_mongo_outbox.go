package persistence

// This package is the ContentReaction object's Mongo adapter.

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

type contentReactionCheckpointDocument struct {
	ID          string    `bson:"_id"`
	Consumer    string    `bson:"consumer"`
	PartitionID int       `bson:"partitionId"`
	Sequence    int64     `bson:"sequence"`
	LeaseEpoch  int64     `bson:"leaseEpoch"`
	LeaseOwner  string    `bson:"leaseOwner,omitempty"`
	LeaseUntil  time.Time `bson:"leaseUntil,omitempty"`
	UpdatedAt   time.Time `bson:"updatedAt"`
}

func reactionCheckpointID(consumer string, partitionID int) string {
	return fmt.Sprintf("%s:%02d", strings.TrimSpace(consumer), partitionID)
}

func (s *MongoContentReactionStore) ClaimOutboxPartitions(
	ctx context.Context,
	consumer string,
	owner string,
	lease time.Duration,
	maxPartitions int,
) ([]reactionports.OutboxPartitionLease, error) {
	consumer = strings.TrimSpace(consumer)
	owner = strings.TrimSpace(owner)
	if consumer == "" || owner == "" {
		return nil, errors.New("ContentReaction outbox consumer and owner are required")
	}
	if lease <= 0 {
		lease = time.Minute
	}
	if maxPartitions <= 0 || maxPartitions > reactionports.ContentReactionOutboxPartitionCount {
		maxPartitions = reactionports.ContentReactionOutboxPartitionCount
	}
	now := s.now().UTC()
	leases := make([]reactionports.OutboxPartitionLease, 0, maxPartitions)
	for partitionID := 0; partitionID < reactionports.ContentReactionOutboxPartitionCount && len(leases) < maxPartitions; partitionID++ {
		id := reactionCheckpointID(consumer, partitionID)
		_, err := s.checkpoints.UpdateOne(ctx, bson.M{"_id": id}, bson.M{
			"$setOnInsert": bson.M{
				"consumer": consumer, "partitionId": partitionID,
				"sequence": int64(0), "leaseEpoch": int64(0), "updatedAt": now,
			},
		}, options.UpdateOne().SetUpsert(true))
		if err != nil {
			return nil, fmt.Errorf("ensure ContentReaction checkpoint: %w", err)
		}
		var document contentReactionCheckpointDocument
		err = s.checkpoints.FindOneAndUpdate(
			ctx,
			bson.M{"_id": id, "$or": []bson.M{
				{"leaseUntil": bson.M{"$lte": now}},
				{"leaseUntil": bson.M{"$exists": false}},
				{"leaseOwner": owner},
			}},
			bson.M{"$inc": bson.M{"leaseEpoch": int64(1)}, "$set": bson.M{
				"leaseOwner": owner, "leaseUntil": now.Add(lease), "updatedAt": now,
			}},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&document)
		if err == mongo.ErrNoDocuments {
			continue
		}
		if err != nil {
			return nil, fmt.Errorf("claim ContentReaction checkpoint partition: %w", err)
		}
		leases = append(leases, reactionports.OutboxPartitionLease{
			Consumer: consumer, Owner: owner, PartitionID: partitionID,
			Sequence: document.Sequence, LeaseEpoch: document.LeaseEpoch,
			LeaseUntil: document.LeaseUntil.UTC(),
		})
	}
	return leases, nil
}

func (s *MongoContentReactionStore) ReadOutboxPartition(
	ctx context.Context,
	lease reactionports.OutboxPartitionLease,
	limit int,
) ([]reactionports.OutboxFact, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	var checkpoint contentReactionCheckpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{
		"_id":      reactionCheckpointID(lease.Consumer, lease.PartitionID),
		"sequence": lease.Sequence, "leaseOwner": lease.Owner,
		"leaseEpoch": lease.LeaseEpoch, "leaseUntil": bson.M{"$gt": s.now().UTC()},
	}).Decode(&checkpoint)
	if err == mongo.ErrNoDocuments {
		return nil, fmt.Errorf("%w: partition %d epoch %d", reactionports.ErrOutboxLeaseLost, lease.PartitionID, lease.LeaseEpoch)
	}
	if err != nil {
		return nil, fmt.Errorf("validate ContentReaction outbox lease: %w", err)
	}
	cursor, err := s.outbox.Find(
		ctx,
		bson.M{"partitionId": lease.PartitionID, "partitionSequence": bson.M{"$gt": lease.Sequence}},
		options.Find().SetSort(bson.D{{Key: "partitionSequence", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read ContentReaction outbox partition: %w", err)
	}
	defer cursor.Close(ctx)
	facts := make([]reactionports.OutboxFact, 0, limit)
	expected := lease.Sequence + 1
	for cursor.Next(ctx) {
		var document contentReactionOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode ContentReaction outbox partition: %w", err)
		}
		if document.PartitionSequence != expected {
			return nil, fmt.Errorf(
				"ContentReaction partition %d has gap: got %d want %d",
				lease.PartitionID, document.PartitionSequence, expected,
			)
		}
		if document.PartitionKey != document.AggregateID ||
			document.PartitionID != reactionports.OutboxPartitionForKey(document.PartitionKey) {
			return nil, errors.New("ContentReaction outbox partition identity mismatch")
		}
		facts = append(facts, reactionports.OutboxFact{
			EventID: document.ID, EventType: document.EventType,
			AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
			Payload: append([]byte(nil), document.PayloadJSON...), OccurredAt: document.OccurredAt.UTC(),
			PartitionKey: document.PartitionKey, PartitionID: document.PartitionID,
			PartitionSequence: document.PartitionSequence,
		})
		expected++
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate ContentReaction outbox partition: %w", err)
	}
	return facts, nil
}

func (s *MongoContentReactionStore) AdvanceOutboxCheckpoint(
	ctx context.Context,
	lease reactionports.OutboxPartitionLease,
	fact reactionports.OutboxFact,
) error {
	if fact.PartitionID != lease.PartitionID || fact.PartitionSequence != lease.Sequence+1 {
		return fmt.Errorf("%w: non-contiguous sequence", reactionports.ErrOutboxLeaseLost)
	}
	result, err := s.checkpoints.UpdateOne(ctx, bson.M{
		"_id":      reactionCheckpointID(lease.Consumer, lease.PartitionID),
		"sequence": lease.Sequence, "leaseOwner": lease.Owner,
		"leaseEpoch": lease.LeaseEpoch, "leaseUntil": bson.M{"$gt": s.now().UTC()},
	}, bson.M{"$set": bson.M{
		"sequence": fact.PartitionSequence, "updatedAt": s.now().UTC(),
	}})
	if err != nil {
		return fmt.Errorf("advance ContentReaction checkpoint: %w", err)
	}
	if result.MatchedCount != 1 {
		return fmt.Errorf("%w: partition %d epoch %d", reactionports.ErrOutboxLeaseLost, lease.PartitionID, lease.LeaseEpoch)
	}
	return nil
}

var (
	_ reactionports.OutboxReader              = (*MongoContentReactionStore)(nil)
	_ reactionports.ProjectionCheckpointStore = (*MongoContentReactionStore)(nil)
)
