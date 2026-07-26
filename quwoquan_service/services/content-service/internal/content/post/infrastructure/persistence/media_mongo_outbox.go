package persistence

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediaports "quwoquan_service/services/content-service/internal/content/post/domain/media/ports"
)

type mediaOutboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateType    string    `bson:"aggregateType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	Payload          []byte    `bson:"payload"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

func (s *MongoMediaStore) writeMediaOutbox(
	ctx context.Context,
	events []mediaports.OutboxEvent,
) error {
	for _, event := range events {
		collection, err := s.outboxCollection(event.AggregateType)
		if err != nil {
			return err
		}
		if _, err := collection.InsertOne(ctx, mediaOutboxDocument{
			ID:               event.EventID,
			EventType:        event.EventType,
			AggregateType:    event.AggregateType,
			AggregateID:      event.AggregateID,
			AggregateVersion: event.AggregateVersion,
			Payload:          append([]byte(nil), event.Payload...),
			OccurredAt:       event.OccurredAt.UTC(),
		}); err != nil {
			return err
		}
	}
	return nil
}

func (s *MongoMediaStore) ReadMediaOutboxAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]mediaports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	sessionEvents, err := readMediaOutboxCollection(
		ctx,
		s.sessionOutbox,
		checkpoint,
		limit,
	)
	if err != nil {
		return nil, err
	}
	assetEvents, err := readMediaOutboxCollection(
		ctx,
		s.assetOutbox,
		checkpoint,
		limit,
	)
	if err != nil {
		return nil, err
	}
	events := append(sessionEvents, assetEvents...)
	sort.Slice(events, func(left int, right int) bool {
		if events[left].OccurredAt.Equal(events[right].OccurredAt) {
			return events[left].EventID < events[right].EventID
		}
		return events[left].OccurredAt.Before(events[right].OccurredAt)
	})
	if len(events) > limit {
		events = events[:limit]
	}
	return events, nil
}

func readMediaOutboxCollection(
	ctx context.Context,
	collection *mongo.Collection,
	checkpoint string,
	limit int,
) ([]mediaports.OutboxEvent, error) {
	filter := bson.D{}
	if strings.TrimSpace(checkpoint) != "" {
		occurredAt, eventID, err := parseMediaOutboxCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter = bson.D{{
			Key: "$or",
			Value: bson.A{
				bson.D{{Key: "occurredAt", Value: bson.D{{Key: "$gt", Value: occurredAt}}}},
				bson.D{
					{Key: "occurredAt", Value: occurredAt},
					{Key: "_id", Value: bson.D{{Key: "$gt", Value: eventID}}},
				},
			},
		}}
	}
	cursor, err := collection.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read media outbox: %w", err)
	}
	defer cursor.Close(ctx)

	events := make([]mediaports.OutboxEvent, 0, limit)
	for cursor.Next(ctx) {
		var document mediaOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode media outbox: %w", err)
		}
		events = append(events, mediaports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateType:    document.AggregateType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append([]byte(nil), document.Payload...),
			OccurredAt:       document.OccurredAt,
			Checkpoint:       mediaOutboxCheckpoint(document.OccurredAt, document.ID),
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate media outbox: %w", err)
	}
	return events, nil
}

func (s *MongoMediaStore) outboxCollection(
	aggregateType string,
) (*mongo.Collection, error) {
	switch aggregateType {
	case "MediaUploadSession":
		return s.sessionOutbox, nil
	case "MediaAsset":
		return s.assetOutbox, nil
	default:
		return nil, contentgenerated.AppErrorFromVersionConflict(
			"unsupported media outbox aggregate type",
		)
	}
}

func mediaOutboxCheckpoint(occurredAt time.Time, eventID string) string {
	return occurredAt.UTC().Format(time.RFC3339Nano) + "|" + eventID
}

func parseMediaOutboxCheckpoint(checkpoint string) (time.Time, string, error) {
	occurredAtValue, eventID, ok := strings.Cut(strings.TrimSpace(checkpoint), "|")
	if !ok || strings.TrimSpace(eventID) == "" {
		return time.Time{}, "", fmt.Errorf("invalid media outbox checkpoint")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, occurredAtValue)
	if err != nil {
		return time.Time{}, "", fmt.Errorf("invalid media outbox checkpoint: %w", err)
	}
	return occurredAt.UTC(), eventID, nil
}

func cloneMediaTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
