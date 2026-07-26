package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

type placementOutboxDocument struct {
	ID               string    `bson:"_id"`
	OutboxSequence   int64     `bson:"outboxSequence"`
	EventType        string    `bson:"eventType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	PayloadJSON      string    `bson:"payloadJson"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

func (store *MongoAggregateStore) ReadAfter(ctx context.Context, checkpoint string, limit int) ([]placementports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		sequence, err := parsePlacementCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["outboxSequence"] = bson.M{"$gt": sequence}
	}
	cursor, err := store.outbox.Find(ctx, filter, options.Find().
		SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).
		SetLimit(int64(limit)))
	if err != nil {
		return nil, fmt.Errorf("read CirclePostPlacement outbox: %w", err)
	}
	defer cursor.Close(ctx)
	events := make([]placementports.OutboxEvent, 0, limit)
	for cursor.Next(ctx) {
		var document placementOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode CirclePostPlacement outbox: %w", err)
		}
		payload := json.RawMessage(document.PayloadJSON)
		if !json.Valid(payload) {
			return nil, fmt.Errorf("CirclePostPlacement outbox %q contains invalid payload JSON", document.ID)
		}
		events = append(events, placementports.OutboxEvent{
			EventID: document.ID, EventType: document.EventType,
			AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
			Payload: append(json.RawMessage(nil), payload...), OccurredAt: document.OccurredAt.UTC(),
			Checkpoint: placementCheckpoint(document.OutboxSequence),
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate CirclePostPlacement outbox: %w", err)
	}
	return events, nil
}

func (store *MongoAggregateStore) LoadCheckpoint(ctx context.Context, consumer string) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("CirclePostPlacement projection consumer is required")
	}
	var document struct {
		Sequence int64 `bson:"sequence"`
	}
	err := store.checkpoints.FindOne(ctx, bson.M{"_id": placementCheckpointID(consumer)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("load CirclePostPlacement checkpoint: %w", err)
	}
	if document.Sequence <= 0 {
		return "", nil
	}
	return placementCheckpoint(document.Sequence), nil
}

func (store *MongoAggregateStore) SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return fmt.Errorf("CirclePostPlacement projection consumer is required")
	}
	sequence, err := parsePlacementCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	_, err = store.checkpoints.UpdateOne(ctx,
		bson.M{"_id": placementCheckpointID(consumer)},
		bson.M{"$max": bson.M{"sequence": sequence}, "$set": bson.M{"updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true))
	if err != nil {
		return fmt.Errorf("save CirclePostPlacement checkpoint: %w", err)
	}
	return nil
}

func placementCheckpointID(consumer string) string {
	return "circle-post-placement:" + consumer
}

func placementCheckpoint(sequence int64) string {
	return strconv.FormatInt(sequence, 10)
}

func parsePlacementCheckpoint(checkpoint string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, fmt.Errorf("invalid CirclePostPlacement checkpoint")
	}
	return sequence, nil
}

var (
	_ placementports.OutboxReader              = (*MongoAggregateStore)(nil)
	_ placementports.ProjectionCheckpointStore = (*MongoAggregateStore)(nil)
)
