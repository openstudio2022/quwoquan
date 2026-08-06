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

const placementProjectionInboxCollection = "circle_post_placement_projection_inbox"

// MongoPostCountProjector is the sole writer of Circle.postCount. Its inbox
// makes replay safe when a process crashes after applying the projection but
// before the outbox relay saves its consumer checkpoint.
type MongoPostCountProjector struct {
	circles *mongo.Collection
	inbox   *mongo.Collection
	cache   circleports.CacheInvalidator
}

func NewMongoPostCountProjector(
	database *mongo.Database,
	cache circleports.CacheInvalidator,
) *MongoPostCountProjector {
	if database == nil || cache == nil {
		panic("CirclePostPlacement post-count projector requires MongoDB and cache invalidator")
	}
	return &MongoPostCountProjector{
		circles: database.Collection("circles"),
		inbox:   database.Collection(placementProjectionInboxCollection),
		cache:   cache,
	}
}

func (projector *MongoPostCountProjector) Apply(ctx context.Context, event circleapp.DerivedCountEvent) error {
	if projector == nil || projector.circles == nil || projector.inbox == nil || projector.cache == nil {
		return fmt.Errorf("CirclePostPlacement post-count projector is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || event.AggregateVersion <= 0 {
		return fmt.Errorf("CirclePostPlacement projection event identity is incomplete")
	}
	var payload struct {
		CircleID string `json:"circleId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode CirclePostPlacement projection payload: %w", err)
	}
	payload.CircleID = strings.TrimSpace(payload.CircleID)
	if payload.CircleID == "" {
		return fmt.Errorf("CirclePostPlacement projection has no circleId")
	}
	if applied, err := projector.alreadyApplied(ctx, event.EventID); err != nil {
		return err
	} else if applied {
		return projector.invalidateCircleCache(ctx, payload.CircleID)
	}
	delta := int64(0)
	switch strings.TrimSpace(event.EventType) {
	case "CirclePostPlaced":
		delta = 1
	case "CirclePostPlacementRemoved":
		delta = -1
	case "CirclePostPlacementPresentationChanged":
	default:
		return fmt.Errorf("unsupported CirclePostPlacement event type %q", event.EventType)
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
		if delta != 0 {
			result, updateErr := projector.circles.UpdateOne(txCtx, bson.M{"_id": payload.CircleID}, bson.M{
				"$inc": bson.M{"postCount": delta},
				"$set": bson.M{"updatedAt": time.Now().UTC()},
			})
			if updateErr != nil {
				return nil, updateErr
			}
			if result.MatchedCount != 1 {
				return nil, fmt.Errorf("Circle %q not found for placement projection", payload.CircleID)
			}
		}
		_, insertErr := projector.inbox.InsertOne(txCtx, bson.M{
			"_id": event.EventID, "aggregateId": event.AggregateID,
			"aggregateVersion": event.AggregateVersion, "appliedAt": time.Now().UTC(),
		})
		return nil, insertErr
	})
	if err == nil {
		return projector.invalidateCircleCache(ctx, payload.CircleID)
	}
	// Concurrent duplicate delivery can race before either transaction commits.
	// Only a durable inbox row converts duplicate-key/unknown-commit outcomes to success.
	if applied, findErr := projector.alreadyApplied(ctx, event.EventID); findErr == nil && applied {
		return projector.invalidateCircleCache(ctx, payload.CircleID)
	}
	return err
}

func (projector *MongoPostCountProjector) invalidateCircleCache(ctx context.Context, circleID string) error {
	if err := projector.cache.InvalidateCircle(ctx, strings.TrimSpace(circleID)); err != nil {
		return fmt.Errorf("invalidate Circle placement discovery cache: %w", err)
	}
	return nil
}

func (projector *MongoPostCountProjector) alreadyApplied(ctx context.Context, eventID string) (bool, error) {
	err := projector.inbox.FindOne(ctx, bson.M{"_id": strings.TrimSpace(eventID)}).Err()
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

var _ circleapp.DerivedCountProjection = (*MongoPostCountProjector)(nil)
