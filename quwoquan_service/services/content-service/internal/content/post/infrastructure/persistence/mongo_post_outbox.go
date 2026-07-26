package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type contentOutboxDocument struct {
	ID               string          `bson:"_id"`
	OutboxSequence   int64           `bson:"outboxSequence"`
	EventType        string          `bson:"eventType"`
	AggregateType    string          `bson:"aggregateType"`
	AggregateID      string          `bson:"aggregateId"`
	AggregateVersion int64           `bson:"aggregateVersion"`
	PayloadJSON      json.RawMessage `bson:"payloadJson"`
	OccurredAt       time.Time       `bson:"occurredAt"`
}

type projectionCheckpointDocument struct {
	ID        string    `bson:"_id"`
	Sequence  int64     `bson:"sequence"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

func (s *MongoPostStore) ensureOutboxIndexes(ctx context.Context) error {
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_content_outbox_sequence").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "aggregateType", Value: 1},
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().
				SetName("idx_content_outbox_aggregate_version").
				SetUnique(true),
		},
	}); err != nil {
		return err
	}
	// MongoDB creates a unique _id index for projection_checkpoints
	// automatically. Re-declaring it with index options is rejected by MongoDB
	// and would make production startup fail.
	return nil
}

// ReadAfter exposes a stable, replayable sequence for one Post projection
// consumer. The returned checkpoint is opaque: consumers must save the
// checkpoint attached to the last successfully applied event.
func (s *MongoPostStore) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]postports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}

	filter := bson.M{"aggregateType": "Post"}
	if strings.TrimSpace(checkpoint) != "" {
		sequence, err := ParsePostOutboxCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["outboxSequence"] = bson.M{"$gt": sequence}
	}

	cursor, err := s.outbox.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read post outbox: %w", err)
	}
	defer cursor.Close(ctx)

	events := make([]postports.OutboxEvent, 0, limit)
	for cursor.Next(ctx) {
		var document contentOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode post outbox: %w", err)
		}
		events = append(events, postports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateType:    document.AggregateType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append(json.RawMessage(nil), document.PayloadJSON...),
			OccurredAt:       document.OccurredAt,
			Checkpoint:       PostOutboxCheckpoint(document.OutboxSequence),
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate post outbox: %w", err)
	}
	return events, nil
}

func (s *MongoPostStore) LoadCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("post projection consumer is required")
	}
	var document projectionCheckpointDocument
	err := s.checkpoints.FindOne(
		ctx,
		bson.M{"_id": postCheckpointDocumentID(consumer)},
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("load post projection checkpoint: %w", err)
	}
	if document.Sequence <= 0 {
		return "", nil
	}
	return PostOutboxCheckpoint(document.Sequence), nil
}

func (s *MongoPostStore) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return fmt.Errorf("post projection consumer is required")
	}
	if strings.TrimSpace(checkpoint) == "" {
		return fmt.Errorf("post projection checkpoint is required")
	}
	sequence, err := ParsePostOutboxCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	_, err = s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": postCheckpointDocumentID(consumer)},
		bson.M{
			"$max": bson.M{"sequence": sequence},
			"$set": bson.M{"updatedAt": time.Now().UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("save post projection checkpoint: %w", err)
	}
	return nil
}

func postCheckpointDocumentID(consumer string) string {
	return "post:" + consumer
}

func PostOutboxCheckpoint(sequence int64) string {
	return strconv.FormatInt(sequence, 10)
}

func ParsePostOutboxCheckpoint(checkpoint string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, fmt.Errorf("invalid post outbox checkpoint")
	}
	return sequence, nil
}

var (
	_ postports.OutboxReader              = (*MongoPostStore)(nil)
	_ postports.ProjectionCheckpointStore = (*MongoPostStore)(nil)
)
