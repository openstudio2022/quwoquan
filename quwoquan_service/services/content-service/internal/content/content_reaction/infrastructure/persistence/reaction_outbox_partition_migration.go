package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

// MigrateOutboxPartitions backfills unpartitioned global-sequence rows before unique
// partition indexes are created. It is idempotent and preserves eventId.
func (s *MongoContentReactionStore) MigrateOutboxPartitions(ctx context.Context) error {
	cursor, err := s.outbox.Find(
		ctx,
		bson.M{"$or": []bson.M{
			{"partitionId": bson.M{"$exists": false}},
			{"partitionSequence": bson.M{"$exists": false}},
		}},
		options.Find().SetSort(bson.D{{Key: "outboxSequence", Value: 1}, {Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}),
	)
	if err != nil {
		return fmt.Errorf("scan unpartitioned ContentReaction outbox: %w", err)
	}
	defer cursor.Close(ctx)
	sequences := make(map[int]int64, reactionports.ContentReactionOutboxPartitionCount)
	for cursor.Next(ctx) {
		var document contentReactionOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return fmt.Errorf("decode unpartitioned ContentReaction outbox: %w", err)
		}
		partitionKey := document.AggregateID
		partitionID := reactionports.OutboxPartitionForKey(partitionKey)
		sequences[partitionID]++
		if _, err := s.outbox.UpdateOne(ctx, bson.M{
			"_id": document.ID,
			"$or": []bson.M{
				{"partitionId": bson.M{"$exists": false}},
				{"partitionSequence": bson.M{"$exists": false}},
			},
		}, bson.M{"$set": bson.M{
			"partitionKey": partitionKey, "partitionId": partitionID,
			"partitionSequence": sequences[partitionID],
		}}); err != nil {
			return fmt.Errorf("backfill ContentReaction outbox partition: %w", err)
		}
	}
	if err := cursor.Err(); err != nil {
		return fmt.Errorf("iterate unpartitioned ContentReaction outbox: %w", err)
	}
	for partitionID, sequence := range sequences {
		if _, err := s.sequences.UpdateOne(
			ctx, bson.M{"_id": partitionID},
			bson.M{"$max": bson.M{"value": sequence}, "$set": bson.M{"updatedAt": time.Now().UTC()}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return fmt.Errorf("seed ContentReaction partition sequence: %w", err)
		}
	}
	return nil
}

func (s *MongoContentReactionStore) DropUnpartitionedGlobalSequence(ctx context.Context) error {
	unpartitioned := s.outbox.Database().Collection("content_reaction_outbox_sequences")
	_, err := unpartitioned.DeleteOne(ctx, bson.M{"_id": "ContentReaction"})
	if err != nil && err != mongo.ErrNoDocuments {
		return fmt.Errorf("drop unpartitioned ContentReaction global sequence: %w", err)
	}
	return nil
}
