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

	fileports "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/ports"
)

func (store *MongoAggregateStore) ReadAfter(ctx context.Context, checkpoint string, limit int) ([]fileports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		sequence, err := parseFileCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["outboxSequence"] = bson.M{"$gt": sequence}
	}
	rows, err := store.outbox.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, fmt.Errorf("read CircleFile outbox: %w", err)
	}
	defer rows.Close(ctx)
	var events []fileports.OutboxEvent
	for rows.Next(ctx) {
		var document struct {
			ID               string    `bson:"_id"`
			OutboxSequence   int64     `bson:"outboxSequence"`
			EventType        string    `bson:"eventType"`
			AggregateID      string    `bson:"aggregateId"`
			AggregateVersion int64     `bson:"aggregateVersion"`
			PayloadJSON      string    `bson:"payloadJson"`
			OccurredAt       time.Time `bson:"occurredAt"`
		}
		if err := rows.Decode(&document); err != nil {
			return nil, err
		}
		payload := json.RawMessage(document.PayloadJSON)
		if !json.Valid(payload) {
			return nil, fmt.Errorf("CircleFile outbox %q contains invalid payload JSON", document.ID)
		}
		events = append(events, fileports.OutboxEvent{
			EventID: document.ID, EventType: document.EventType,
			AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
			Payload: append(json.RawMessage(nil), payload...), OccurredAt: document.OccurredAt.UTC(),
			Checkpoint: strconv.FormatInt(document.OutboxSequence, 10),
		})
	}
	return events, rows.Err()
}

func (store *MongoAggregateStore) LoadCheckpoint(ctx context.Context, consumer string) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("CircleFile consumer is required")
	}
	var document struct {
		Sequence int64 `bson:"sequence"`
	}
	err := store.checkpoints.FindOne(ctx, bson.M{"_id": "circle-file:" + consumer}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	if document.Sequence <= 0 {
		return "", nil
	}
	return strconv.FormatInt(document.Sequence, 10), nil
}

func (store *MongoAggregateStore) SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error {
	sequence, err := parseFileCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	if consumer = strings.TrimSpace(consumer); consumer == "" {
		return fmt.Errorf("CircleFile consumer is required")
	}
	_, err = store.checkpoints.UpdateOne(ctx, bson.M{"_id": "circle-file:" + consumer},
		bson.M{"$max": bson.M{"sequence": sequence}, "$set": bson.M{"updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true))
	return err
}

func parseFileCheckpoint(checkpoint string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, fmt.Errorf("invalid CircleFile checkpoint")
	}
	return sequence, nil
}

var (
	_ fileports.OutboxReader              = (*MongoAggregateStore)(nil)
	_ fileports.ProjectionCheckpointStore = (*MongoAggregateStore)(nil)
)
