package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/application"
)

type placementClosureDocument struct {
	ID             string    `bson:"_id"`
	Version        int64     `bson:"version"`
	PostID         string    `bson:"postId"`
	OwnerPersonaID string    `bson:"ownerPersonaId"`
	CircleID       string    `bson:"circleId"`
	GroupID        string    `bson:"groupId"`
	State          string    `bson:"state"`
	CreatedAt      time.Time `bson:"createdAt"`
}

func (projection *MongoUserAccountClosedProjection) removeClosedAccountPostState(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	subjects []string,
	summary *accountClosureCleanupSummary,
) error {
	placements := projection.db.Collection("circle_post_placements")
	rows, err := placements.Find(
		ctx,
		bson.M{"ownerPersonaId": bson.M{"$in": subjects}},
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}),
	)
	if err != nil {
		return fmt.Errorf("scan closed CirclePostPlacements: %w", err)
	}
	var documents []placementClosureDocument
	if err := rows.All(ctx, &documents); err != nil {
		rows.Close(ctx)
		return err
	}
	rows.Close(ctx)
	for _, current := range documents {
		summary.affectedCircleIDs[current.CircleID] = struct{}{}
		anonymousID := closedCircleAnonymousID(current.OwnerPersonaID)
		if current.State == "removed" {
			if _, err := placements.UpdateOne(
				ctx,
				bson.M{"_id": current.ID},
				bson.M{"$set": bson.M{
					"ownerPersonaId": anonymousID,
					"pinned":         false,
					"featured":       false,
					"updatedAt":      event.UpdatedAt.UTC(),
				}, "$unset": bson.M{
					"pinnedAt":   "",
					"featuredAt": "",
				}},
			); err != nil {
				return err
			}
			continue
		}
		var updated placementClosureDocument
		err := placements.FindOneAndUpdate(
			ctx,
			bson.M{"_id": current.ID, "version": current.Version},
			bson.M{
				"$set": bson.M{
					"ownerPersonaId": anonymousID,
					"state":          "removed",
					"pinned":         false,
					"featured":       false,
					"updatedAt":      event.UpdatedAt.UTC(),
				},
				"$unset": bson.M{"pinnedAt": "", "featuredAt": ""},
				"$inc":   bson.M{"version": int64(1)},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&updated)
		if err != nil {
			return fmt.Errorf(
				"remove closed CirclePostPlacement: %w",
				err,
			)
		}
		if err := projection.appendPlacementRemovalOutbox(
			ctx,
			event,
			updated,
		); err != nil {
			return err
		}
		if _, err := projection.db.Collection(
			"circle_post_placement_command_receipts",
		).UpdateMany(
			ctx,
			bson.M{"placementId": updated.ID},
			bson.M{"$set": bson.M{"state": "removed"}},
		); err != nil {
			return err
		}
	}
	if _, err := projection.db.Collection("posts").DeleteMany(
		ctx,
		bson.M{"authorId": bson.M{"$in": subjects}},
	); err != nil {
		return fmt.Errorf("delete closed Circle Post read models: %w", err)
	}
	if _, err := projection.db.Collection(
		"circle_post_owner_views",
	).DeleteMany(
		ctx,
		bson.M{"ownerPersonaId": bson.M{"$in": subjects}},
	); err != nil {
		return fmt.Errorf("delete closed Circle Post owner views: %w", err)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) appendPlacementRemovalOutbox(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	placement placementClosureDocument,
) error {
	sequence, err := projection.nextOutboxSequence(
		ctx,
		"circle_post_placement_outbox_sequences",
		"CirclePostPlacement",
	)
	if err != nil {
		return err
	}
	eventType := "CirclePostPlacementRemoved"
	payload, err := json.Marshal(map[string]any{
		"_id":            placement.ID,
		"version":        placement.Version,
		"postId":         placement.PostID,
		"ownerPersonaId": placement.OwnerPersonaID,
		"circleId":       placement.CircleID,
		"groupId":        placement.GroupID,
		"state":          placement.State,
		"pinned":         false,
		"featured":       false,
		"createdAt":      placement.CreatedAt.UTC(),
		"updatedAt":      event.UpdatedAt.UTC(),
		"lastActiveAt":   event.UpdatedAt.UTC(),
	})
	if err != nil {
		return err
	}
	eventID := placement.ID + ":" + eventType + ":" +
		strconv.FormatInt(placement.Version, 10)
	_, err = projection.db.Collection(
		"circle_post_placement_outbox",
	).InsertOne(ctx, bson.M{
		"_id": eventID, "outboxSequence": sequence,
		"eventType": eventType, "aggregateId": placement.ID,
		"aggregateVersion": placement.Version,
		"payloadJson":      string(payload), "occurredAt": event.UpdatedAt.UTC(),
	})
	if err != nil {
		return fmt.Errorf(
			"append closed CirclePostPlacement removal outbox: %w",
			err,
		)
	}
	return nil
}
