package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

type circleClosureDocument struct {
	ID                       string    `bson:"_id"`
	Version                  int64     `bson:"version"`
	Name                     string    `bson:"name"`
	OwnerID                  string    `bson:"ownerId"`
	OwnerDisplayNameSnapshot string    `bson:"ownerDisplayNameSnapshot"`
	Category                 string    `bson:"category"`
	Tags                     []string  `bson:"tags"`
	Status                   string    `bson:"status"`
	DefaultPublicGroupID     string    `bson:"defaultPublicGroupId"`
	UpdatedAt                time.Time `bson:"updatedAt"`
}

type circleMembershipCandidate struct {
	ID        string    `bson:"_id"`
	Version   int64     `bson:"version"`
	CircleID  string    `bson:"circleId"`
	PersonaID string    `bson:"personaId"`
	Role      string    `bson:"role"`
	State     string    `bson:"state"`
	JoinedAt  time.Time `bson:"joinedAt"`
	CreatedAt time.Time `bson:"createdAt"`
}

type groupClosureDocument struct {
	ID                   string    `bson:"_id"`
	Version              int64     `bson:"version"`
	CircleID             string    `bson:"circleId"`
	GroupType            string    `bson:"groupType"`
	CreatedByPersonaID   string    `bson:"createdByPersonaId"`
	Status               string    `bson:"status"`
	IsDefaultPublicGroup bool      `bson:"isDefaultPublicGroup"`
	UpdatedAt            time.Time `bson:"updatedAt"`
}

type groupMembershipCandidate struct {
	ID        string    `bson:"_id"`
	Version   int64     `bson:"version"`
	GroupID   string    `bson:"groupId"`
	CircleID  string    `bson:"circleId"`
	PersonaID string    `bson:"personaId"`
	Role      string    `bson:"role"`
	State     string    `bson:"state"`
	JoinedAt  time.Time `bson:"joinedAt"`
	CreatedAt time.Time `bson:"createdAt"`
}

func (projection *MongoUserAccountClosedProjection) governClosedGroupOwners(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	subjects []string,
	summary *accountClosureCleanupSummary,
) (map[string]struct{}, error) {
	memberships := projection.db.Collection("circle_group_memberships")
	rows, err := memberships.Find(
		ctx,
		bson.M{
			"personaId": bson.M{"$in": subjects},
			"role":      "owner",
			"state":     "active",
		},
		options.Find().
			SetProjection(bson.M{"groupId": 1}).
			SetSort(bson.D{{Key: "groupId", Value: 1}}),
	)
	if err != nil {
		return nil, fmt.Errorf("scan closed CircleGroup owners: %w", err)
	}
	defer rows.Close(ctx)
	groupIDs := map[string]struct{}{}
	for rows.Next(ctx) {
		var document struct {
			GroupID string `bson:"groupId"`
		}
		if err := rows.Decode(&document); err != nil {
			return nil, err
		}
		if document.GroupID = strings.TrimSpace(document.GroupID); document.GroupID != "" {
			groupIDs[document.GroupID] = struct{}{}
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	forceArchiveCircles := map[string]struct{}{}
	for _, groupID := range sortedStringSet(groupIDs) {
		var group groupClosureDocument
		err := projection.db.Collection("circle_groups").FindOne(
			ctx,
			bson.M{"_id": groupID},
		).Decode(&group)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, errors.New(
				"active closed-owner group has no CircleGroup aggregate",
			)
		}
		if err != nil {
			return nil, fmt.Errorf("read closed-owner CircleGroup: %w", err)
		}
		summary.affectedCircleIDs[group.CircleID] = struct{}{}
		summary.governedGroupIDs[group.ID] = struct{}{}
		if group.Status != "active" {
			continue
		}
		candidate, found, err := findGroupOwnerSuccessor(
			ctx,
			memberships,
			group.ID,
			subjects,
		)
		if err != nil {
			return nil, err
		}
		if found {
			if err := projection.promoteGroupOwner(
				ctx,
				event,
				candidate,
			); err != nil {
				return nil, err
			}
			continue
		}
		archived, err := projection.archiveGroupForAccountClosure(
			ctx,
			event,
			group,
		)
		if err != nil {
			return nil, err
		}
		if archived.IsDefaultPublicGroup {
			forceArchiveCircles[archived.CircleID] = struct{}{}
		}
	}
	return forceArchiveCircles, nil
}

func (projection *MongoUserAccountClosedProjection) governClosedCircleOwners(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	subjects []string,
	forceArchiveCircles map[string]struct{},
	summary *accountClosureCleanupSummary,
) error {
	circles := projection.db.Collection("circles")
	ownedCircleIDs, err := collectStringValues(
		ctx,
		circles,
		bson.M{"ownerId": bson.M{"$in": subjects}},
		"_id",
	)
	if err != nil {
		return fmt.Errorf("scan closed Circle owners: %w", err)
	}
	circleIDs := make(map[string]struct{}, len(ownedCircleIDs)+len(forceArchiveCircles))
	for _, circleID := range ownedCircleIDs {
		circleIDs[circleID] = struct{}{}
	}
	for circleID := range forceArchiveCircles {
		circleIDs[circleID] = struct{}{}
	}
	for _, circleID := range sortedStringSet(circleIDs) {
		var circle circleClosureDocument
		err := circles.FindOne(ctx, bson.M{"_id": circleID}).Decode(&circle)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return errors.New(
				"account-closure governance Circle does not exist",
			)
		}
		if err != nil {
			return fmt.Errorf("read closed-owner Circle: %w", err)
		}
		summary.affectedCircleIDs[circle.ID] = struct{}{}
		summary.governedCircleIDs[circle.ID] = struct{}{}
		_, forcedArchive := forceArchiveCircles[circle.ID]
		ownerClosed := stringSliceContains(subjects, circle.OwnerID)
		if circle.Status != "active" || forcedArchive {
			eventType := "CircleUpdated"
			set := bson.M{}
			if circle.Status == "active" {
				set["status"] = "archived"
				eventType = "CircleArchived"
			}
			if ownerClosed {
				set["ownerId"] = closedCircleAnonymousID(circle.OwnerID)
				set["ownerDisplayNameSnapshot"] = closedAccountDisplayName
			}
			if len(set) == 0 {
				continue
			}
			if _, err := projection.mutateCircleGovernance(
				ctx,
				event,
				circle,
				set,
				eventType,
			); err != nil {
				return err
			}
			summary.circleEventWritten[circle.ID] = struct{}{}
			continue
		}

		candidate, found, err := findCircleOwnerSuccessor(
			ctx,
			projection.db.Collection("circle_memberships"),
			circle.ID,
			subjects,
		)
		if err != nil {
			return err
		}
		if !found {
			if _, err := projection.mutateCircleGovernance(
				ctx,
				event,
				circle,
				bson.M{
					"status":                   "archived",
					"ownerId":                  closedCircleAnonymousID(circle.OwnerID),
					"ownerDisplayNameSnapshot": closedAccountDisplayName,
				},
				"CircleArchived",
			); err != nil {
				return err
			}
			summary.circleEventWritten[circle.ID] = struct{}{}
			continue
		}
		if err := projection.promoteCircleOwner(
			ctx,
			event,
			candidate,
		); err != nil {
			return err
		}
		if _, err := projection.mutateCircleGovernance(
			ctx,
			event,
			circle,
			bson.M{
				"ownerId":                  candidate.PersonaID,
				"ownerDisplayNameSnapshot": "",
			},
			"CircleUpdated",
		); err != nil {
			return err
		}
		summary.circleEventWritten[circle.ID] = struct{}{}
	}
	return nil
}

func findCircleOwnerSuccessor(
	ctx context.Context,
	memberships *mongo.Collection,
	circleID string,
	excludedSubjects []string,
) (circleMembershipCandidate, bool, error) {
	var candidate circleMembershipCandidate
	err := memberships.FindOne(
		ctx,
		bson.M{
			"circleId":  circleID,
			"personaId": bson.M{"$nin": excludedSubjects},
			"state":     "active",
			"role":      bson.M{"$in": bson.A{"admin", "member"}},
		},
		options.FindOne().SetSort(bson.D{
			{Key: "role", Value: 1},
			{Key: "joinedAt", Value: 1},
			{Key: "personaId", Value: 1},
			{Key: "_id", Value: 1},
		}),
	).Decode(&candidate)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return circleMembershipCandidate{}, false, nil
	}
	if err != nil {
		return circleMembershipCandidate{}, false,
			fmt.Errorf("select deterministic Circle owner successor: %w", err)
	}
	return candidate, true, nil
}

func findGroupOwnerSuccessor(
	ctx context.Context,
	memberships *mongo.Collection,
	groupID string,
	excludedSubjects []string,
) (groupMembershipCandidate, bool, error) {
	var candidate groupMembershipCandidate
	err := memberships.FindOne(
		ctx,
		bson.M{
			"groupId":   groupID,
			"personaId": bson.M{"$nin": excludedSubjects},
			"state":     "active",
			"role":      bson.M{"$in": bson.A{"manager", "member"}},
		},
		options.FindOne().SetSort(bson.D{
			{Key: "role", Value: 1},
			{Key: "joinedAt", Value: 1},
			{Key: "personaId", Value: 1},
			{Key: "_id", Value: 1},
		}),
	).Decode(&candidate)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupMembershipCandidate{}, false, nil
	}
	if err != nil {
		return groupMembershipCandidate{}, false,
			fmt.Errorf(
				"select deterministic CircleGroup owner successor: %w",
				err,
			)
	}
	return candidate, true, nil
}

func (projection *MongoUserAccountClosedProjection) validateGovernedOwnerInvariants(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	summary accountClosureCleanupSummary,
) error {
	subjects := event.SubjectIDs()
	for circleID := range summary.governedCircleIDs {
		var circle circleClosureDocument
		if err := projection.db.Collection("circles").FindOne(
			ctx,
			bson.M{"_id": circleID},
		).Decode(&circle); err != nil {
			return fmt.Errorf("validate governed Circle owner: %w", err)
		}
		if circle.Status != "active" {
			continue
		}
		if strings.TrimSpace(circle.OwnerID) == "" ||
			stringSliceContains(subjects, circle.OwnerID) {
			return errors.New(
				"active Circle retained a closed or empty owner",
			)
		}
		totalOwners, err := projection.db.Collection(
			"circle_memberships",
		).CountDocuments(ctx, bson.M{
			"circleId": circle.ID,
			"state":    "active",
			"role":     "owner",
		})
		if err != nil {
			return err
		}
		matchingOwner, err := projection.db.Collection(
			"circle_memberships",
		).CountDocuments(ctx, bson.M{
			"circleId":  circle.ID,
			"personaId": circle.OwnerID,
			"state":     "active",
			"role":      "owner",
		})
		if err != nil {
			return err
		}
		if totalOwners != 1 || matchingOwner != 1 {
			return errors.New(
				"active Circle owner invariant would be violated",
			)
		}
	}
	for groupID := range summary.governedGroupIDs {
		var group groupClosureDocument
		if err := projection.db.Collection("circle_groups").FindOne(
			ctx,
			bson.M{"_id": groupID},
		).Decode(&group); err != nil {
			return fmt.Errorf("validate governed CircleGroup owner: %w", err)
		}
		if group.Status != "active" {
			continue
		}
		ownerCount, err := projection.db.Collection(
			"circle_group_memberships",
		).CountDocuments(ctx, bson.M{
			"groupId": group.ID,
			"state":   "active",
			"role":    "owner",
		})
		if err != nil {
			return err
		}
		if ownerCount != 1 {
			return errors.New(
				"active CircleGroup owner invariant would be violated",
			)
		}
	}
	return nil
}

func stringSliceContains(values []string, target string) bool {
	target = strings.TrimSpace(target)
	for _, value := range values {
		if strings.TrimSpace(value) == target {
			return true
		}
	}
	return false
}
