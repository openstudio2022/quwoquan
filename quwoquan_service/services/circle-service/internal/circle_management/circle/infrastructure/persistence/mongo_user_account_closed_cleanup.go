package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

const accountClosureMongoBatchSize = 500

type accountClosureCleanupSummary struct {
	affectedCircleIDs  map[string]struct{}
	circleEventWritten map[string]struct{}
	governedCircleIDs  map[string]struct{}
	governedGroupIDs   map[string]struct{}
}

func newAccountClosureCleanupSummary() accountClosureCleanupSummary {
	return accountClosureCleanupSummary{
		affectedCircleIDs:  map[string]struct{}{},
		circleEventWritten: map[string]struct{}{},
		governedCircleIDs:  map[string]struct{}{},
		governedGroupIDs:   map[string]struct{}{},
	}
}

func (projection *MongoUserAccountClosedProjection) applyAccountClosureCleanup(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (accountClosureCleanupSummary, error) {
	summary := newAccountClosureCleanupSummary()
	subjects := event.SubjectIDs()
	if err := projection.collectAccountClosureCircleIDs(
		ctx,
		subjects,
		summary.affectedCircleIDs,
	); err != nil {
		return summary, err
	}

	forceArchiveCircles, err := projection.governClosedGroupOwners(
		ctx,
		event,
		subjects,
		&summary,
	)
	if err != nil {
		return summary, err
	}
	if err := projection.governClosedCircleOwners(
		ctx,
		event,
		subjects,
		forceArchiveCircles,
		&summary,
	); err != nil {
		return summary, err
	}
	if err := projection.anonymizeCircleMemberships(
		ctx,
		event,
		subjects,
	); err != nil {
		return summary, err
	}
	if err := projection.anonymizeGroupMemberships(
		ctx,
		event,
		subjects,
	); err != nil {
		return summary, err
	}
	if err := projection.anonymizeGroupAndFileProvenance(
		ctx,
		event,
		subjects,
	); err != nil {
		return summary, err
	}
	if err := projection.deleteClosedAccountBehavior(
		ctx,
		subjects,
	); err != nil {
		return summary, err
	}
	if err := projection.removeClosedAccountPostState(
		ctx,
		event,
		subjects,
		&summary,
	); err != nil {
		return summary, err
	}
	if err := projection.anonymizeAccountClosureOutboxes(
		ctx,
		subjects,
	); err != nil {
		return summary, err
	}
	if err := projection.reconcileAccountClosureCircles(
		ctx,
		event,
		&summary,
	); err != nil {
		return summary, err
	}
	if err := projection.validateGovernedOwnerInvariants(
		ctx,
		event,
		summary,
	); err != nil {
		return summary, err
	}
	return summary, nil
}

func (projection *MongoUserAccountClosedProjection) collectAccountClosureCircleIDs(
	ctx context.Context,
	subjects []string,
	target map[string]struct{},
) error {
	queries := []struct {
		collection string
		filter     bson.M
	}{
		{"circles", bson.M{"ownerId": bson.M{"$in": subjects}}},
		{"circle_memberships", bson.M{"personaId": bson.M{"$in": subjects}}},
		{"circle_group_memberships", bson.M{"$or": bson.A{
			bson.M{"personaId": bson.M{"$in": subjects}},
			bson.M{"decidedByPersonaId": bson.M{"$in": subjects}},
		}}},
		{"circle_groups", bson.M{"createdByPersonaId": bson.M{"$in": subjects}}},
		{"circle_files", bson.M{"uploaderPersonaId": bson.M{"$in": subjects}}},
		{"circle_behavior_facts", bson.M{"$or": bson.A{
			bson.M{"personaId": bson.M{"$in": subjects}},
			bson.M{"deviceActorId": bson.M{"$in": subjects}},
		}}},
		{"circle_post_placements", bson.M{"ownerPersonaId": bson.M{"$in": subjects}}},
	}
	for _, query := range queries {
		if err := collectCircleIDs(
			ctx,
			projection.db.Collection(query.collection),
			query.filter,
			target,
		); err != nil {
			return fmt.Errorf(
				"collect circle account-closure scope from %s: %w",
				query.collection,
				err,
			)
		}
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) anonymizeCircleMemberships(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	subjects []string,
) error {
	collection := projection.db.Collection("circle_memberships")
	receipts := projection.db.Collection(
		"circle_membership_command_receipts",
	)
	for _, subject := range subjects {
		anonymousID := closedCircleAnonymousID(subject)
		membershipIDs, err := collectStringValues(
			ctx,
			collection,
			bson.M{"personaId": subject},
			"_id",
		)
		if err != nil {
			return fmt.Errorf(
				"scan closed circle memberships: %w",
				err,
			)
		}
		if _, err := collection.UpdateMany(
			ctx,
			bson.M{"personaId": subject},
			bson.M{
				"$set": bson.M{
					"personaId":    anonymousID,
					"role":         "member",
					"state":        "removed",
					"leftAt":       event.UpdatedAt.UTC(),
					"updatedAt":    event.UpdatedAt.UTC(),
					"contribution": int64(0),
				},
				"$unset": bson.M{"lastActiveAt": ""},
			},
		); err != nil {
			return fmt.Errorf(
				"anonymize closed circle memberships: %w",
				err,
			)
		}
		if err := updateReceiptsByAggregateIDs(
			ctx,
			receipts,
			"membershipId",
			membershipIDs,
			bson.M{"state": "removed", "role": "member"},
		); err != nil {
			return fmt.Errorf(
				"reconcile closed circle membership receipts: %w",
				err,
			)
		}
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) anonymizeGroupMemberships(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	subjects []string,
) error {
	collection := projection.db.Collection("circle_group_memberships")
	receipts := projection.db.Collection(
		"circle_group_membership_command_receipts",
	)
	for _, subject := range subjects {
		anonymousID := closedCircleAnonymousID(subject)
		if _, err := collection.UpdateMany(
			ctx,
			bson.M{"decidedByPersonaId": subject},
			bson.M{"$set": bson.M{
				"decidedByPersonaId": anonymousID,
			}},
		); err != nil {
			return fmt.Errorf(
				"anonymize closed group decision actor: %w",
				err,
			)
		}
		membershipIDs, err := collectStringValues(
			ctx,
			collection,
			bson.M{"personaId": subject},
			"_id",
		)
		if err != nil {
			return fmt.Errorf(
				"scan closed group memberships: %w",
				err,
			)
		}
		if _, err := collection.UpdateMany(
			ctx,
			bson.M{"personaId": subject},
			bson.M{
				"$set": bson.M{
					"personaId":          anonymousID,
					"role":               "member",
					"state":              "removed",
					"leftAt":             event.UpdatedAt.UTC(),
					"decidedAt":          event.UpdatedAt.UTC(),
					"decidedByPersonaId": anonymousID,
					"updatedAt":          event.UpdatedAt.UTC(),
				},
			},
		); err != nil {
			return fmt.Errorf(
				"anonymize closed group memberships: %w",
				err,
			)
		}
		if err := updateReceiptsByAggregateIDs(
			ctx,
			receipts,
			"membershipId",
			membershipIDs,
			bson.M{"state": "removed", "role": "member"},
		); err != nil {
			return fmt.Errorf(
				"reconcile closed group membership receipts: %w",
				err,
			)
		}
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) anonymizeGroupAndFileProvenance(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	subjects []string,
) error {
	groups := projection.db.Collection("circle_groups")
	files := projection.db.Collection("circle_files")
	for _, subject := range subjects {
		anonymousID := closedCircleAnonymousID(subject)
		if _, err := groups.UpdateMany(
			ctx,
			bson.M{"createdByPersonaId": subject},
			bson.M{"$set": bson.M{
				"createdByPersonaId": anonymousID,
				"updatedAt":          event.UpdatedAt.UTC(),
			}},
		); err != nil {
			return fmt.Errorf(
				"anonymize closed group creator: %w",
				err,
			)
		}
		if _, err := files.UpdateMany(
			ctx,
			bson.M{"uploaderPersonaId": subject},
			bson.M{"$set": bson.M{
				"uploaderPersonaId": anonymousID,
				"updatedAt":         event.UpdatedAt.UTC(),
			}},
		); err != nil {
			return fmt.Errorf(
				"anonymize closed circle file uploader: %w",
				err,
			)
		}
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) deleteClosedAccountBehavior(
	ctx context.Context,
	subjects []string,
) error {
	facts := projection.db.Collection("circle_behavior_facts")
	outbox := projection.db.Collection("circle_behavior_fact_outbox")
	factIDs, err := collectStringValues(
		ctx,
		facts,
		bson.M{"$or": bson.A{
			bson.M{"personaId": bson.M{"$in": subjects}},
			bson.M{"deviceActorId": bson.M{"$in": subjects}},
		}},
		"_id",
	)
	if err != nil {
		return fmt.Errorf("scan closed circle behavior facts: %w", err)
	}
	if err := deleteByStringValues(
		ctx,
		facts,
		"_id",
		factIDs,
	); err != nil {
		return fmt.Errorf("delete closed circle behavior facts: %w", err)
	}
	if err := deleteByStringValues(
		ctx,
		outbox,
		"aggregateId",
		factIDs,
	); err != nil {
		return fmt.Errorf(
			"delete closed circle behavior outbox facts: %w",
			err,
		)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) reconcileAccountClosureCircles(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	summary *accountClosureCleanupSummary,
) error {
	for _, circleID := range sortedStringSet(summary.affectedCircleIDs) {
		memberCount, err := projection.db.Collection(
			"circle_memberships",
		).CountDocuments(
			ctx,
			bson.M{"circleId": circleID, "state": "active"},
		)
		if err != nil {
			return fmt.Errorf(
				"recount circle memberships after account closure: %w",
				err,
			)
		}
		activeCount, err := projection.countWeeklyCircleActors(
			ctx,
			circleID,
			projection.now().UTC().Add(-7*24*time.Hour),
		)
		if err != nil {
			return err
		}
		result, err := projection.db.Collection("circles").UpdateOne(
			ctx,
			bson.M{"_id": circleID},
			bson.M{"$set": bson.M{
				"memberCount":       memberCount,
				"weeklyActiveCount": activeCount,
				"updatedAt":         event.UpdatedAt.UTC(),
			}},
		)
		if err != nil {
			return fmt.Errorf(
				"reconcile circle counters after account closure: %w",
				err,
			)
		}
		if result.MatchedCount == 0 {
			continue
		}
		if _, exists := summary.circleEventWritten[circleID]; !exists {
			if err := projection.appendCircleGovernanceUpdate(
				ctx,
				event,
				circleID,
				"CircleUpdated",
			); err != nil {
				return err
			}
			summary.circleEventWritten[circleID] = struct{}{}
		}
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) countWeeklyCircleActors(
	ctx context.Context,
	circleID string,
	cutoff time.Time,
) (int64, error) {
	rows, err := projection.db.Collection(
		"circle_behavior_facts",
	).Aggregate(ctx, mongo.Pipeline{
		{{Key: "$match", Value: bson.M{
			"circleId":   circleID,
			"occurredAt": bson.M{"$gte": cutoff.UTC()},
		}}},
		{{Key: "$group", Value: bson.M{"_id": bson.M{
			"actorKind": "$actorKind",
			"actorId": bson.M{
				"$ifNull": bson.A{"$personaId", "$deviceActorId"},
			},
		}}}},
		{{Key: "$count", Value: "count"}},
	})
	if err != nil {
		return 0, fmt.Errorf(
			"recount circle weekly actors after account closure: %w",
			err,
		)
	}
	defer rows.Close(ctx)
	var result []struct {
		Count int64 `bson:"count"`
	}
	if err := rows.All(ctx, &result); err != nil {
		return 0, err
	}
	if len(result) == 0 {
		return 0, nil
	}
	return result[0].Count, nil
}
