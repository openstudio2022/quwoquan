package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

const actorLifecycleFenceBuckets = 16

var ErrActorLifecycleClosed = errors.New("content reaction actor lifecycle is closed")

type actorLifecycleFenceDocument struct {
	ID             string    `bson:"_id"`
	ActorDimension string    `bson:"actorDimension"`
	ActorID        string    `bson:"actorId"`
	Bucket         int       `bson:"bucket"`
	Closed         bool      `bson:"closed"`
	CloseSource    string    `bson:"closeSource,omitempty"`
	CommitMark     int64     `bson:"commitMark"`
	UpdatedAt      time.Time `bson:"updatedAt"`
}

func actorLifecycleFenceID(actor reactiondomain.Actor, bucket int) string {
	return fmt.Sprintf("%s|%s|%d", actor.Dimension, actor.ID, bucket)
}

func actorLifecycleFenceBucketFor(aggregateID string) int {
	digest := sha256.Sum256([]byte(aggregateID))
	return int(binary.BigEndian.Uint32(digest[:4]) % uint32(actorLifecycleFenceBuckets))
}

func markActorLifecycleFenceOpen(ctx context.Context, fences *mongo.Collection, actor reactiondomain.Actor, aggregateID string, now time.Time) error {
	bucket := actorLifecycleFenceBucketFor(aggregateID)
	result, err := fences.UpdateOne(
		ctx,
		bson.D{{Key: "_id", Value: actorLifecycleFenceID(actor, bucket)}, {Key: "closed", Value: false}},
		bson.D{
			{Key: "$inc", Value: bson.D{{Key: "commitMark", Value: int64(1)}}},
			{Key: "$set", Value: bson.D{{Key: "updatedAt", Value: now}}},
			{Key: "$setOnInsert", Value: bson.D{
				{Key: "actorDimension", Value: string(actor.Dimension)}, {Key: "actorId", Value: actor.ID},
				{Key: "bucket", Value: bucket}, {Key: "closed", Value: false},
			}},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return ErrActorLifecycleClosed
		}
		return fmt.Errorf("mark ContentReaction actor lifecycle fence: %w", err)
	}
	if result.MatchedCount == 0 && result.UpsertedCount == 0 {
		return ErrActorLifecycleClosed
	}
	return nil
}

func closeActorLifecycleFences(ctx context.Context, fences *mongo.Collection, actor reactiondomain.Actor, closeSource string, now time.Time) error {
	models := make([]mongo.WriteModel, 0, actorLifecycleFenceBuckets)
	for bucket := 0; bucket < actorLifecycleFenceBuckets; bucket++ {
		models = append(models, mongo.NewUpdateOneModel().
			SetFilter(bson.D{{Key: "_id", Value: actorLifecycleFenceID(actor, bucket)}}).
			SetUpsert(true).
			SetUpdate(bson.D{
				{Key: "$set", Value: bson.D{{Key: "closed", Value: true}, {Key: "closeSource", Value: closeSource}, {Key: "updatedAt", Value: now}}},
				{Key: "$setOnInsert", Value: bson.D{{Key: "actorDimension", Value: string(actor.Dimension)}, {Key: "actorId", Value: actor.ID}, {Key: "bucket", Value: bucket}, {Key: "commitMark", Value: int64(0)}}},
			}))
	}
	if _, err := fences.BulkWrite(ctx, models, options.BulkWrite().SetOrdered(false)); err != nil {
		return fmt.Errorf("close ContentReaction actor lifecycle fences: %w", err)
	}
	return nil
}
