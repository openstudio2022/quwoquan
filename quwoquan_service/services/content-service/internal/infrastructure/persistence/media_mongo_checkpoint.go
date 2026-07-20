package persistence

import (
	"context"
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
