package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

func (store *MongoAggregateStore) ReadPublicationOutboxAfter(
	ctx context.Context,
	after int64,
	limit int,
) ([]ports.OutboxEvent, error) {
	if store == nil || store.outbox == nil || after < 0 {
		return nil, model.ErrInvalidArgument
	}
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	cursor, err := store.outbox.Find(
		ctx,
		bson.M{"outboxSequence": bson.M{"$gt": after}},
		options.Find().SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	type outboxRecord struct {
		EventID          string    `bson:"_id"`
		Sequence         int64     `bson:"outboxSequence"`
		EventType        string    `bson:"eventType"`
		AggregateID      string    `bson:"aggregateId"`
		AggregateVersion int64     `bson:"aggregateVersion"`
		Payload          string    `bson:"payloadJson"`
		OccurredAt       time.Time `bson:"occurredAt"`
	}
	events := make([]ports.OutboxEvent, 0)
	for cursor.Next(ctx) {
		var record outboxRecord
		if err := cursor.Decode(&record); err != nil {
			return nil, err
		}
		events = append(events, ports.OutboxEvent{
			EventID: record.EventID, EventType: record.EventType,
			AggregateID: record.AggregateID, AggregateVersion: record.AggregateVersion,
			Payload: []byte(record.Payload), OccurredAt: record.OccurredAt,
			Sequence: record.Sequence,
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return events, nil
}

func (store *MongoAggregateStore) LoadPublicationCheckpoint(
	ctx context.Context,
	consumer string,
) (int64, error) {
	consumer = strings.TrimSpace(consumer)
	if store == nil || store.publicationCheckpoints == nil || consumer == "" {
		return 0, model.ErrInvalidArgument
	}
	var checkpoint struct {
		Sequence int64 `bson:"sequence"`
	}
	err := store.publicationCheckpoints.FindOne(ctx, bson.M{"_id": consumer}).Decode(&checkpoint)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	return checkpoint.Sequence, nil
}

func (store *MongoAggregateStore) SavePublicationCheckpoint(
	ctx context.Context,
	consumer string,
	sequence int64,
	updatedAt time.Time,
) error {
	consumer = strings.TrimSpace(consumer)
	if store == nil || store.publicationCheckpoints == nil || consumer == "" ||
		sequence <= 0 || updatedAt.IsZero() {
		return model.ErrInvalidArgument
	}
	_, err := store.publicationCheckpoints.UpdateOne(
		ctx,
		bson.M{"_id": consumer},
		bson.M{
			"$max": bson.M{"sequence": sequence},
			"$set": bson.M{"updatedAt": updatedAt.UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}
