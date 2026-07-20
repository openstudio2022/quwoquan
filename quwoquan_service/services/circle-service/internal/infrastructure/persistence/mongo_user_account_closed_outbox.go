package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/application"
)

func (projection *MongoUserAccountClosedProjection) mutateCircleGovernance(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	current circleClosureDocument,
	set bson.M,
	eventType string,
) (circleClosureDocument, error) {
	set["updatedAt"] = event.UpdatedAt.UTC()
	var updated circleClosureDocument
	err := projection.db.Collection("circles").FindOneAndUpdate(
		ctx,
		bson.M{"_id": current.ID, "version": current.Version},
		bson.M{
			"$set": set,
			"$inc": bson.M{"version": int64(1)},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&updated)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return circleClosureDocument{}, errors.New(
			"Circle changed during account-closure governance",
		)
	}
	if err != nil {
		return circleClosureDocument{},
			fmt.Errorf("mutate Circle account-closure governance: %w", err)
	}
	if err := projection.appendCircleOutbox(
		ctx,
		updated,
		eventType,
		event.UpdatedAt.UTC(),
	); err != nil {
		return circleClosureDocument{}, err
	}
	return updated, nil
}

func (projection *MongoUserAccountClosedProjection) appendCircleGovernanceUpdate(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	circleID string,
	eventType string,
) error {
	var current circleClosureDocument
	if err := projection.db.Collection("circles").FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(circleID)},
	).Decode(&current); err != nil {
		return fmt.Errorf(
			"read Circle for account-closure reconciliation event: %w",
			err,
		)
	}
	_, err := projection.mutateCircleGovernance(
		ctx,
		event,
		current,
		bson.M{},
		eventType,
	)
	return err
}

func (projection *MongoUserAccountClosedProjection) appendCircleOutbox(
	ctx context.Context,
	circle circleClosureDocument,
	eventType string,
	occurredAt time.Time,
) error {
	sequence, err := projection.nextOutboxSequence(
		ctx,
		"circle_outbox_sequences",
		"Circle",
	)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(map[string]any{
		"circleId":   circle.ID,
		"version":    circle.Version,
		"name":       circle.Name,
		"ownerId":    circle.OwnerID,
		"category":   circle.Category,
		"tags":       circle.Tags,
		"status":     circle.Status,
		"occurredAt": occurredAt.UTC(),
	})
	if err != nil {
		return fmt.Errorf("encode Circle account-closure event: %w", err)
	}
	eventID := circle.ID + ":" + eventType + ":" +
		strconv.FormatInt(circle.Version, 10)
	_, err = projection.db.Collection("circle_outbox").InsertOne(
		ctx,
		bson.M{
			"_id":              eventID,
			"outboxSequence":   sequence,
			"eventType":        eventType,
			"aggregateId":      circle.ID,
			"aggregateVersion": circle.Version,
			"payloadJson":      string(payload),
			"occurredAt":       occurredAt.UTC(),
		},
	)
	if err != nil {
		return fmt.Errorf("append Circle account-closure outbox: %w", err)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) promoteCircleOwner(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	candidate circleMembershipCandidate,
) error {
	var updated circleMembershipCandidate
	err := projection.db.Collection(
		"circle_memberships",
	).FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":       candidate.ID,
			"version":   candidate.Version,
			"personaId": candidate.PersonaID,
			"state":     "active",
			"role":      candidate.Role,
		},
		bson.M{
			"$set": bson.M{
				"role":      "owner",
				"updatedAt": event.UpdatedAt.UTC(),
			},
			"$inc": bson.M{"version": int64(1)},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&updated)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return errors.New(
			"Circle owner successor changed during account closure",
		)
	}
	if err != nil {
		return fmt.Errorf("promote Circle owner successor: %w", err)
	}
	sequence, err := projection.nextOutboxSequence(
		ctx,
		"circle_membership_outbox_sequences",
		"CircleMembership",
	)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(map[string]any{
		"id":                   updated.ID,
		"version":              updated.Version,
		"circleId":             updated.CircleID,
		"personaId":            updated.PersonaID,
		"role":                 updated.Role,
		"state":                updated.State,
		"joinedAt":             updated.JoinedAt.UTC(),
		"createdAt":            updated.CreatedAt.UTC(),
		"updatedAt":            event.UpdatedAt.UTC(),
		"circleOwnerPersonaId": updated.PersonaID,
	})
	if err != nil {
		return err
	}
	eventType := "CircleMembershipRoleChanged"
	eventID := updated.ID + ":" + eventType + ":" +
		strconv.FormatInt(updated.Version, 10)
	_, err = projection.db.Collection(
		"circle_membership_outbox",
	).InsertOne(ctx, bson.M{
		"_id": eventID, "outboxSequence": sequence,
		"eventType": eventType, "aggregateId": updated.ID,
		"aggregateVersion": updated.Version,
		"payloadJson":      string(payload), "occurredAt": event.UpdatedAt.UTC(),
	})
	if err != nil {
		return fmt.Errorf("append Circle owner succession outbox: %w", err)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) promoteGroupOwner(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	candidate groupMembershipCandidate,
) error {
	var updated groupMembershipCandidate
	err := projection.db.Collection(
		"circle_group_memberships",
	).FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":       candidate.ID,
			"version":   candidate.Version,
			"personaId": candidate.PersonaID,
			"state":     "active",
			"role":      candidate.Role,
		},
		bson.M{
			"$set": bson.M{
				"role":               "owner",
				"decidedAt":          event.UpdatedAt.UTC(),
				"decidedByPersonaId": candidate.PersonaID,
				"updatedAt":          event.UpdatedAt.UTC(),
			},
			"$inc": bson.M{"version": int64(1)},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&updated)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return errors.New(
			"CircleGroup owner successor changed during account closure",
		)
	}
	if err != nil {
		return fmt.Errorf("promote CircleGroup owner successor: %w", err)
	}
	sequence, err := projection.nextOutboxSequence(
		ctx,
		"circle_group_membership_outbox_sequences",
		"CircleGroupMembership",
	)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(map[string]any{
		"id":                  updated.ID,
		"version":             updated.Version,
		"groupId":             updated.GroupID,
		"circleId":            updated.CircleID,
		"personaId":           updated.PersonaID,
		"role":                updated.Role,
		"state":               updated.State,
		"joinedAt":            updated.JoinedAt.UTC(),
		"createdAt":           updated.CreatedAt.UTC(),
		"updatedAt":           event.UpdatedAt.UTC(),
		"groupOwnerPersonaId": updated.PersonaID,
	})
	if err != nil {
		return err
	}
	eventType := "CircleGroupMembershipRoleChanged"
	eventID := updated.ID + ":" + eventType + ":" +
		strconv.FormatInt(updated.Version, 10)
	_, err = projection.db.Collection(
		"circle_group_membership_outbox",
	).InsertOne(ctx, bson.M{
		"_id": eventID, "outboxSequence": sequence,
		"eventType": eventType, "aggregateId": updated.ID,
		"aggregateVersion": updated.Version,
		"payloadJson":      string(payload), "occurredAt": event.UpdatedAt.UTC(),
	})
	if err != nil {
		return fmt.Errorf(
			"append CircleGroup owner succession outbox: %w",
			err,
		)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) archiveGroupForAccountClosure(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	current groupClosureDocument,
) (groupClosureDocument, error) {
	var updated groupClosureDocument
	err := projection.db.Collection("circle_groups").FindOneAndUpdate(
		ctx,
		bson.M{"_id": current.ID, "version": current.Version, "status": "active"},
		bson.M{
			"$set": bson.M{
				"status":    "archived",
				"updatedAt": event.UpdatedAt.UTC(),
			},
			"$inc": bson.M{"version": int64(1)},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&updated)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupClosureDocument{}, errors.New(
			"CircleGroup changed during account-closure archive",
		)
	}
	if err != nil {
		return groupClosureDocument{},
			fmt.Errorf("archive ownerless CircleGroup: %w", err)
	}
	sequence, err := projection.nextOutboxSequence(
		ctx,
		"circle_group_outbox_sequences",
		"CircleGroup",
	)
	if err != nil {
		return groupClosureDocument{}, err
	}
	eventType := "CircleGroupArchived"
	payload, err := json.Marshal(map[string]any{
		"groupId":            updated.ID,
		"version":            updated.Version,
		"circleId":           updated.CircleID,
		"groupType":          updated.GroupType,
		"createdByPersonaId": updated.CreatedByPersonaID,
		"status":             updated.Status,
		"occurredAt":         event.UpdatedAt.UTC(),
	})
	if err != nil {
		return groupClosureDocument{}, err
	}
	eventID := updated.ID + ":" + eventType + ":" +
		strconv.FormatInt(updated.Version, 10)
	_, err = projection.db.Collection("circle_group_outbox").InsertOne(
		ctx,
		bson.M{
			"_id": eventID, "outboxSequence": sequence,
			"eventType": eventType, "aggregateId": updated.ID,
			"aggregateVersion": updated.Version,
			"payloadJson":      string(payload), "occurredAt": event.UpdatedAt.UTC(),
		},
	)
	if err != nil {
		return groupClosureDocument{},
			fmt.Errorf("append ownerless CircleGroup archive outbox: %w", err)
	}
	return updated, nil
}

func (projection *MongoUserAccountClosedProjection) nextOutboxSequence(
	ctx context.Context,
	collection string,
	sequenceID string,
) (int64, error) {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	err := projection.db.Collection(collection).FindOneAndUpdate(
		ctx,
		bson.M{"_id": sequenceID},
		bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&sequence)
	if err != nil {
		return 0, fmt.Errorf("allocate account-closure outbox sequence: %w", err)
	}
	return sequence.Value, nil
}
