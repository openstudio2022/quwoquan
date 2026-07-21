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

	rtredis "quwoquan_service/runtime/redis"
	membershipports "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/ports"
	circlecache "quwoquan_service/services/circle-service/internal/infrastructure/cache"
)

const membershipProjectionInboxCollection = "circle_membership_projection_inbox"

// MongoMemberCountProjector is the sole writer of Circle.memberCount. The
// Circle update and durable inbox marker commit in one Mongo transaction.
// Cache invalidation remains retryable even when the event was already applied.
type MongoMemberCountProjector struct {
	circles *mongo.Collection
	inbox   *mongo.Collection
	redis   rtredis.Client
}

func NewMongoMemberCountProjector(database *mongo.Database, redis rtredis.Client) *MongoMemberCountProjector {
	if database == nil || redis == nil {
		panic("CircleMembership member-count projector requires MongoDB and Redis")
	}
	return &MongoMemberCountProjector{
		circles: database.Collection("circles"),
		inbox:   database.Collection(membershipProjectionInboxCollection),
		redis:   redis,
	}
}

func (projector *MongoMemberCountProjector) Publish(ctx context.Context, event membershipports.OutboxEvent) error {
	if projector == nil || projector.circles == nil || projector.inbox == nil || projector.redis == nil {
		return fmt.Errorf("CircleMembership member-count projector is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || event.AggregateVersion <= 0 {
		return fmt.Errorf("CircleMembership projection event identity is incomplete")
	}
	var payload struct {
		CircleID string `json:"circleId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode CircleMembership projection payload: %w", err)
	}
	payload.CircleID = strings.TrimSpace(payload.CircleID)
	if payload.CircleID == "" {
		return fmt.Errorf("CircleMembership projection has no circleId")
	}
	if applied, err := projector.alreadyApplied(ctx, event.EventID); err != nil {
		return err
	} else if !applied {
		if err := projector.apply(ctx, event, payload.CircleID); err != nil {
			if appliedAfterFailure, findErr := projector.alreadyApplied(ctx, event.EventID); findErr != nil || !appliedAfterFailure {
				return err
			}
		}
	}
	if err := projector.redis.Del(ctx, "cache:circle:"+payload.CircleID); err != nil {
		return fmt.Errorf("invalidate Circle member-count cache: %w", err)
	}
	if err := circlecache.InvalidateCircleDiscoveryFeed(ctx, projector.redis); err != nil {
		return fmt.Errorf("invalidate Circle membership discovery cache: %w", err)
	}
	return nil
}

func (projector *MongoMemberCountProjector) apply(ctx context.Context, event membershipports.OutboxEvent, circleID string) error {
	delta := int64(0)
	switch strings.TrimSpace(event.EventType) {
	case "CircleMembershipJoined", "CircleMembershipApproved":
		delta = 1
	case "CircleMembershipLeft":
		delta = -1
	case "CircleMembershipRoleChanged", "CircleMembershipRequested", "CircleMembershipRejected":
		// 审批生命周期事件不影响 memberCount（pending/rejected 不计数）。
	default:
		return fmt.Errorf("unsupported CircleMembership event type %q", event.EventType)
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
			filter := bson.M{"_id": circleID}
			if delta < 0 {
				filter["memberCount"] = bson.M{"$gte": int64(1)}
			}
			result, updateErr := projector.circles.UpdateOne(txCtx, filter, bson.M{
				"$inc": bson.M{"memberCount": delta},
				"$set": bson.M{"updatedAt": time.Now().UTC()},
			})
			if updateErr != nil {
				return nil, updateErr
			}
			if result.MatchedCount != 1 {
				return nil, fmt.Errorf("Circle %q missing or memberCount invariant violated", circleID)
			}
		}
		_, insertErr := projector.inbox.InsertOne(txCtx, bson.M{
			"_id": event.EventID, "aggregateId": event.AggregateID,
			"aggregateVersion": event.AggregateVersion, "appliedAt": time.Now().UTC(),
		})
		return nil, insertErr
	})
	return err
}

func (projector *MongoMemberCountProjector) alreadyApplied(ctx context.Context, eventID string) (bool, error) {
	err := projector.inbox.FindOne(ctx, bson.M{"_id": strings.TrimSpace(eventID)}).Err()
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

var _ membershipports.OutboxPublisher = (*MongoMemberCountProjector)(nil)
