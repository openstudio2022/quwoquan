package persistence

// This package is the ContentReaction object's Mongo adapter.

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

type contentReactionCheckpointDocument struct {
	ID        string    `bson:"_id"`
	Sequence  int64     `bson:"sequence"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

func (s *MongoContentReactionStore) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]reactionports.OutboxFact, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		sequence, err := parseReactionOutboxCheckpoint(checkpoint)
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
		return nil, fmt.Errorf("read ContentReaction outbox: %w", err)
	}
	defer cursor.Close(ctx)
	facts := make([]reactionports.OutboxFact, 0, limit)
	for cursor.Next(ctx) {
		var document contentReactionOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode ContentReaction outbox: %w", err)
		}
		facts = append(facts, reactionports.OutboxFact{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append([]byte(nil), document.PayloadJSON...),
			OccurredAt:       document.OccurredAt.UTC(),
			Checkpoint:       reactionOutboxCheckpoint(document.OutboxSequence),
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate ContentReaction outbox: %w", err)
	}
	return facts, nil
}

func (s *MongoContentReactionStore) LoadCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("ContentReaction projection consumer is required")
	}
	var document contentReactionCheckpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": consumer}).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("load ContentReaction checkpoint: %w", err)
	}
	if document.Sequence <= 0 {
		return "", nil
	}
	return reactionOutboxCheckpoint(document.Sequence), nil
}

func (s *MongoContentReactionStore) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return fmt.Errorf("ContentReaction projection consumer is required")
	}
	sequence, err := parseReactionOutboxCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	_, err = s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": consumer},
		bson.M{
			"$max": bson.M{"sequence": sequence},
			"$set": bson.M{"updatedAt": time.Now().UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("save ContentReaction checkpoint: %w", err)
	}
	return nil
}

func (s *MongoContentReactionStore) CountActiveReactions(
	ctx context.Context,
	postID string,
) (int64, error) {
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return 0, fmt.Errorf("Post id is required")
	}
	return s.aggregates.CountDocuments(ctx, bson.M{
		"targetKind": string(reactiondomain.TargetKindPost),
		"targetId":   postID,
		"reaction":   string(reactiondomain.ValueLike),
	})
}

func (s *MongoContentReactionStore) CountActiveReactionsForActor(
	ctx context.Context,
	actor reactiondomain.Actor,
) (int64, error) {
	if err := actor.Validate(); err != nil {
		return 0, fmt.Errorf("invalid ContentReaction actor: %w", err)
	}
	return s.aggregates.CountDocuments(ctx, bson.M{
		"actorDimension": string(actor.Dimension),
		"actorId":        actor.ID,
		"targetKind":     string(reactiondomain.TargetKindPost),
		"reaction":       string(reactiondomain.ValueLike),
	})
}

func reactionOutboxCheckpoint(sequence int64) string {
	return strconv.FormatInt(sequence, 10)
}

func parseReactionOutboxCheckpoint(checkpoint string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, fmt.Errorf("invalid ContentReaction outbox checkpoint")
	}
	return sequence, nil
}

var (
	_ reactionports.OutboxReader              = (*MongoContentReactionStore)(nil)
	_ reactionports.ProjectionCheckpointStore = (*MongoContentReactionStore)(nil)
)
