package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	circleapp "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
)

const (
	behaviorFactCollection            = "circle_behavior_facts"
	behaviorProjectionInboxCollection = "circle_behavior_fact_projection_inbox"
)

type MongoWeeklyActiveProjector struct {
	facts   *mongo.Collection
	circles *mongo.Collection
	inbox   *mongo.Collection
	cache   circleports.CacheInvalidator
	now     func() time.Time
}

func NewMongoWeeklyActiveProjector(
	database *mongo.Database,
	cache circleports.CacheInvalidator,
) *MongoWeeklyActiveProjector {
	if database == nil || cache == nil {
		panic("CircleBehaviorFact weekly-active projector requires MongoDB and cache invalidator")
	}
	return &MongoWeeklyActiveProjector{
		facts: database.Collection(behaviorFactCollection), circles: database.Collection("circles"),
		inbox: database.Collection(behaviorProjectionInboxCollection), cache: cache, now: time.Now,
	}
}

func (projector *MongoWeeklyActiveProjector) Apply(ctx context.Context, event circleapp.DerivedCountEvent) error {
	if projector == nil || projector.facts == nil || projector.circles == nil || projector.inbox == nil || projector.cache == nil {
		return fmt.Errorf("CircleBehaviorFact weekly-active projector is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || event.EventType != "CircleBehaviorFactAppended" {
		return fmt.Errorf("invalid CircleBehaviorFact projection event")
	}
	var payload struct {
		CircleID string `json:"circleId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode CircleBehaviorFact projection payload: %w", err)
	}
	if strings.TrimSpace(payload.CircleID) == "" {
		return fmt.Errorf("CircleBehaviorFact projection payload has no circleId")
	}
	payload.CircleID = strings.TrimSpace(payload.CircleID)
	if applied, err := projector.alreadyApplied(ctx, event.EventID); err != nil {
		return err
	} else if !applied {
		if err := projector.apply(ctx, event, payload.CircleID); err != nil {
			if appliedAfterFailure, findErr := projector.alreadyApplied(ctx, event.EventID); findErr != nil || !appliedAfterFailure {
				return err
			}
		}
	}
	if err := projector.cache.InvalidateCircle(ctx, payload.CircleID); err != nil {
		return fmt.Errorf("invalidate Circle discovery feed after weekly-active projection: %w", err)
	}
	return nil
}

func (projector *MongoWeeklyActiveProjector) apply(ctx context.Context, event circleapp.DerivedCountEvent, circleID string) error {
	activeCount, err := projector.countActiveActors(ctx, circleID)
	if err != nil {
		return err
	}
	session, err := projector.circles.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if applied, findErr := projector.alreadyApplied(txCtx, event.EventID); findErr != nil || applied {
			return nil, findErr
		}
		result, updateErr := projector.circles.UpdateOne(txCtx, bson.M{"_id": circleID}, bson.M{
			"$set": bson.M{"weeklyActiveCount": activeCount, "updatedAt": projector.now().UTC()},
		})
		if updateErr != nil {
			return nil, updateErr
		}
		if result.MatchedCount != 1 {
			return nil, fmt.Errorf("Circle %q not found for weekly-active projection", circleID)
		}
		_, insertErr := projector.inbox.InsertOne(txCtx, bson.M{
			"_id": event.EventID, "aggregateId": event.AggregateID, "appliedAt": projector.now().UTC(),
		})
		return nil, insertErr
	})
	return err
}

func (projector *MongoWeeklyActiveProjector) countActiveActors(ctx context.Context, circleID string) (int64, error) {
	cutoff := projector.now().UTC().Add(-7 * 24 * time.Hour)
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: bson.M{"circleId": circleID, "occurredAt": bson.M{"$gte": cutoff}}}},
		{{Key: "$group", Value: bson.M{"_id": bson.M{
			"actorKind": "$actorKind", "actorId": bson.M{"$ifNull": bson.A{"$personaId", "$deviceActorId"}},
		}}}},
		{{Key: "$count", Value: "count"}},
	}
	rows, err := projector.facts.Aggregate(ctx, pipeline)
	if err != nil {
		return 0, err
	}
	defer rows.Close(ctx)
	var counts []struct {
		Count int64 `bson:"count"`
	}
	if err := rows.All(ctx, &counts); err != nil {
		return 0, err
	}
	if len(counts) == 0 {
		return 0, nil
	}
	return counts[0].Count, nil
}

func (projector *MongoWeeklyActiveProjector) alreadyApplied(ctx context.Context, eventID string) (bool, error) {
	err := projector.inbox.FindOne(ctx, bson.M{"_id": strings.TrimSpace(eventID)}).Err()
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

var _ circleapp.DerivedCountProjection = (*MongoWeeklyActiveProjector)(nil)
