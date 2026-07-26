package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

type mediaCheckpointDocument struct {
	ID         string    `bson:"_id"`
	Checkpoint string    `bson:"checkpoint"`
	OccurredAt time.Time `bson:"occurredAt"`
	PositionNS int64     `bson:"positionNanos"`
	EventID    string    `bson:"eventId"`
	LeaseOwner string    `bson:"leaseOwner,omitempty"`
	LeaseUntil time.Time `bson:"leaseUntil,omitempty"`
	UpdatedAt  time.Time `bson:"updatedAt"`
}

// LoadCheckpoint returns the durable media outbox consumer offset. Media
// checkpoints are opaque `occurredAt|eventId` strings, deliberately separate
// from Post sequence checkpoints so replays can never cross aggregates.
func (s *MongoMediaStore) LoadCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("media projection consumer is required")
	}
	var document mediaCheckpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": consumer}).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("load media projection checkpoint: %w", err)
	}
	return document.Checkpoint, nil
}

func (s *MongoMediaStore) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return fmt.Errorf("media projection consumer is required")
	}
	if strings.TrimSpace(checkpoint) == "" {
		return fmt.Errorf("media projection checkpoint is required")
	}
	checkpoint = strings.TrimSpace(checkpoint)
	occurredAt, eventID, err := parseMediaOutboxCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	positionNS := occurredAt.UnixNano()

	// 条件更新由 MongoDB 原子求值；所有副本写同一个 consumer 文档，只有更大的
	// (occurredAt,eventId) 元组才能替换存量。晚到保存会成为 no-op，不会回退水位。
	advance := bson.D{{Key: "$or", Value: bson.A{
		bson.D{{Key: "$eq", Value: bson.A{
			bson.D{{Key: "$type", Value: "$positionNanos"}},
			"missing",
		}}},
		bson.D{{Key: "$lt", Value: bson.A{"$positionNanos", positionNS}}},
		bson.D{{Key: "$and", Value: bson.A{
			bson.D{{Key: "$eq", Value: bson.A{"$positionNanos", positionNS}}},
			bson.D{{Key: "$lt", Value: bson.A{"$eventId", eventID}}},
		}}},
	}}}
	keepOrSet := func(next any, current string) bson.D {
		return bson.D{{Key: "$cond", Value: bson.A{advance, next, current}}}
	}
	_, err = s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": consumer},
		mongo.Pipeline{bson.D{{Key: "$set", Value: bson.D{
			{Key: "checkpoint", Value: keepOrSet(checkpoint, "$checkpoint")},
			{Key: "occurredAt", Value: keepOrSet(occurredAt, "$occurredAt")},
			{Key: "positionNanos", Value: keepOrSet(positionNS, "$positionNanos")},
			{Key: "eventId", Value: keepOrSet(eventID, "$eventId")},
			{Key: "updatedAt", Value: keepOrSet(time.Now().UTC(), "$updatedAt")},
		}}}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("save media projection checkpoint: %w", err)
	}
	return nil
}

// TryAcquireMediaProcessingLease elects exactly one active media processor for
// a shared consumer cursor. The lease lives alongside the cursor so a future
// extracted worker can retain the same durable ownership protocol.
func (s *MongoMediaStore) TryAcquireMediaProcessingLease(
	ctx context.Context,
	consumer string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	consumer, owner, now, err := validateMediaProcessingLease(consumer, owner, now, ttl)
	if err != nil {
		return false, err
	}
	result, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{
			"_id": consumer,
			"$or": bson.A{
				bson.M{"leaseOwner": owner},
				bson.M{"leaseUntil": bson.M{"$exists": false}},
				bson.M{"leaseUntil": bson.M{"$lte": now}},
			},
		},
		bson.M{"$set": bson.M{
			"leaseOwner": owner,
			"leaseUntil": now.Add(ttl),
			"updatedAt":  now,
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if isMediaProcessingLeaseContention(err) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("acquire media processing lease: %w", err)
	}
	return result.MatchedCount == 1 || result.UpsertedCount == 1, nil
}

func (s *MongoMediaStore) RenewMediaProcessingLease(
	ctx context.Context,
	consumer string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	consumer, owner, now, err := validateMediaProcessingLease(consumer, owner, now, ttl)
	if err != nil {
		return false, err
	}
	result, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{
			"_id":        consumer,
			"leaseOwner": owner,
			"leaseUntil": bson.M{"$gt": now},
		},
		bson.M{"$set": bson.M{
			"leaseUntil": now.Add(ttl),
			"updatedAt":  now,
		}},
	)
	if err != nil {
		return false, fmt.Errorf("renew media processing lease: %w", err)
	}
	return result.MatchedCount == 1, nil
}

// SaveMediaProcessingCheckpointWithLease advances the cursor only for the
// current lease owner. If a worker loses ownership while FFmpeg is active, it
// cannot write a newer checkpoint after a standby replica takes over.
func (s *MongoMediaStore) SaveMediaProcessingCheckpointWithLease(
	ctx context.Context,
	consumer string,
	owner string,
	checkpoint string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	consumer, owner, now, err := validateMediaProcessingLease(consumer, owner, now, ttl)
	if err != nil {
		return false, err
	}
	checkpoint = strings.TrimSpace(checkpoint)
	if checkpoint == "" {
		return false, fmt.Errorf("media projection checkpoint is required")
	}
	occurredAt, eventID, err := parseMediaOutboxCheckpoint(checkpoint)
	if err != nil {
		return false, err
	}
	positionNS := occurredAt.UnixNano()
	advance := bson.D{{Key: "$or", Value: bson.A{
		bson.D{{Key: "$eq", Value: bson.A{
			bson.D{{Key: "$type", Value: "$positionNanos"}},
			"missing",
		}}},
		bson.D{{Key: "$lt", Value: bson.A{"$positionNanos", positionNS}}},
		bson.D{{Key: "$and", Value: bson.A{
			bson.D{{Key: "$eq", Value: bson.A{"$positionNanos", positionNS}}},
			bson.D{{Key: "$lt", Value: bson.A{"$eventId", eventID}}},
		}}},
	}}}
	keepOrSet := func(next any, current string) bson.D {
		return bson.D{{Key: "$cond", Value: bson.A{advance, next, current}}}
	}
	result, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{
			"_id":        consumer,
			"leaseOwner": owner,
			"leaseUntil": bson.M{"$gt": now},
		},
		mongo.Pipeline{bson.D{{Key: "$set", Value: bson.D{
			{Key: "checkpoint", Value: keepOrSet(checkpoint, "$checkpoint")},
			{Key: "occurredAt", Value: keepOrSet(occurredAt, "$occurredAt")},
			{Key: "positionNanos", Value: keepOrSet(positionNS, "$positionNanos")},
			{Key: "eventId", Value: keepOrSet(eventID, "$eventId")},
			{Key: "leaseUntil", Value: now.Add(ttl)},
			{Key: "updatedAt", Value: now},
		}}}},
	)
	if err != nil {
		return false, fmt.Errorf("save media projection checkpoint with lease: %w", err)
	}
	return result.MatchedCount == 1, nil
}

func validateMediaProcessingLease(
	consumer string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (string, string, time.Time, error) {
	consumer = strings.TrimSpace(consumer)
	owner = strings.TrimSpace(owner)
	if consumer == "" || owner == "" {
		return "", "", time.Time{}, fmt.Errorf(
			"media processing lease consumer and owner are required",
		)
	}
	if ttl <= 0 {
		return "", "", time.Time{}, fmt.Errorf("media processing lease ttl must be positive")
	}
	if now.IsZero() {
		return "", "", time.Time{}, fmt.Errorf("media processing lease time is required")
	}
	return consumer, owner, now.UTC(), nil
}

func isMediaProcessingLeaseContention(err error) bool {
	if err == nil {
		return false
	}
	if mongo.IsDuplicateKeyError(err) {
		return true
	}
	var commandError mongo.CommandError
	if errors.As(err, &commandError) && commandError.Code == 112 {
		return true
	}
	var writeError mongo.WriteException
	return errors.As(err, &writeError) && writeError.HasErrorCode(112)
}
