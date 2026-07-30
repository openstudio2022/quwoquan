package persistence

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
	membershipports "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/ports"
)

type MongoReaders struct {
	circles     *mongo.Collection
	memberships *mongo.Collection
}

func NewMongoReaders(database *mongo.Database) *MongoReaders {
	if database == nil {
		panic("CircleMembership MongoReaders requires database")
	}
	return &MongoReaders{
		circles:     database.Collection("circles"),
		memberships: database.Collection(membershipCollection),
	}
}

func (readers *MongoReaders) ReadCirclePolicy(ctx context.Context, circleID string) (membershipports.CirclePolicySlice, bool, error) {
	var document struct {
		ID             string `bson:"_id"`
		OwnerPersonaID string `bson:"ownerId"`
		State          string `bson:"status"`
		JoinPolicy     string `bson:"joinPolicy"`
	}
	err := readers.circles.FindOne(ctx, bson.M{"_id": strings.TrimSpace(circleID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return membershipports.CirclePolicySlice{}, false, nil
	}
	if err != nil {
		return membershipports.CirclePolicySlice{}, false, err
	}
	return membershipports.CirclePolicySlice{
		CircleID: document.ID, OwnerPersonaID: document.OwnerPersonaID,
		State: document.State, JoinPolicy: document.JoinPolicy,
	}, true, nil
}

func (readers *MongoReaders) ReadCircleMembership(ctx context.Context, circleID, personaID string) (membershipmodel.CircleMembership, bool, error) {
	var document membershipDocument
	err := readers.memberships.FindOne(ctx, bson.M{
		"circleId": strings.TrimSpace(circleID), "personaId": strings.TrimSpace(personaID),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return membershipmodel.CircleMembership{}, false, nil
	}
	if err != nil {
		return membershipmodel.CircleMembership{}, false, err
	}
	return document.toModel(), true, nil
}

func (readers *MongoReaders) ListCircleMemberships(ctx context.Context, circleID string, limit int, cursor string) (membershipports.MembershipSlice, error) {
	return readers.list(ctx, bson.M{
		"circleId": strings.TrimSpace(circleID), "state": membershipmodel.CircleMembershipStateActive,
		"accountRestricted": bson.M{"$ne": true},
	}, limit, cursor)
}

func (readers *MongoReaders) ListPendingCircleMemberships(ctx context.Context, circleID string, limit int, cursor string) (membershipports.MembershipSlice, error) {
	return readers.list(ctx, bson.M{
		"circleId": strings.TrimSpace(circleID), "state": membershipmodel.CircleMembershipStatePending,
		"accountRestricted": bson.M{"$ne": true},
	}, limit, cursor)
}

func (readers *MongoReaders) ListPersonaCircles(
	ctx context.Context,
	query membershipports.PersonaCircleQuery,
) (membershipports.PersonaCircleSlice, error) {
	limit := query.Limit
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	personaID := strings.TrimSpace(query.PersonaID)
	match := bson.D{
		{Key: "personaId", Value: personaID},
		{Key: "state", Value: membershipmodel.CircleMembershipStateActive},
		{Key: "accountRestricted", Value: bson.M{"$ne": true}},
	}
	if cursor := strings.TrimSpace(query.Cursor); cursor != "" {
		match = append(match, bson.E{Key: "_id", Value: bson.M{"$gt": cursor}})
	}
	circleMatch := bson.D{{Key: "circle.status", Value: "active"}}
	if strings.TrimSpace(query.ViewerPersonaID) != personaID {
		circleMatch = append(
			circleMatch,
			bson.E{Key: "circle.visibility", Value: "public"},
		)
	}
	if normalizedQuery := strings.TrimSpace(query.Query); normalizedQuery != "" {
		pattern := bson.Regex{
			Pattern: regexp.QuoteMeta(normalizedQuery),
			Options: "i",
		}
		circleMatch = append(circleMatch, bson.E{
			Key: "$or",
			Value: bson.A{
				bson.D{{Key: "circle.name", Value: pattern}},
				bson.D{{Key: "circle.description", Value: pattern}},
			},
		})
	}
	pipeline := mongo.Pipeline{
		bson.D{{Key: "$match", Value: match}},
		bson.D{{Key: "$sort", Value: bson.D{{Key: "_id", Value: 1}}}},
		bson.D{{Key: "$lookup", Value: bson.D{
			{Key: "from", Value: "circles"},
			{Key: "localField", Value: "circleId"},
			{Key: "foreignField", Value: "_id"},
			{Key: "as", Value: "circle"},
		}}},
		bson.D{{Key: "$unwind", Value: "$circle"}},
		bson.D{{Key: "$match", Value: circleMatch}},
		bson.D{{Key: "$limit", Value: int64(limit + 1)}},
		bson.D{{Key: "$project", Value: bson.D{
			{Key: "_id", Value: 0},
			{Key: "membershipId", Value: "$_id"},
			{Key: "circle", Value: "$circle"},
		}}},
	}
	rows, err := readers.memberships.Aggregate(ctx, pipeline)
	if err != nil {
		return membershipports.PersonaCircleSlice{}, fmt.Errorf(
			"list Persona Circles: %w",
			err,
		)
	}
	defer rows.Close(ctx)
	type circleSummaryDocument struct {
		ID                       string                               `bson:"_id"`
		Name                     string                               `bson:"name"`
		Description              string                               `bson:"description"`
		CoverURL                 string                               `bson:"coverUrl"`
		IconURL                  string                               `bson:"iconUrl"`
		OwnerPersonaID           string                               `bson:"ownerId"`
		OwnerDisplayNameSnapshot string                               `bson:"ownerDisplayNameSnapshot"`
		Category                 string                               `bson:"category"`
		SubCategory              string                               `bson:"subCategory"`
		Tags                     []string                             `bson:"tags"`
		MemberCount              int64                                `bson:"memberCount"`
		PostCount                int64                                `bson:"postCount"`
		WeeklyActiveCount        int64                                `bson:"weeklyActiveCount"`
		Status                   circlemodel.CircleStatus             `bson:"status"`
		Visibility               circlemodel.CircleVisibility         `bson:"visibility"`
		JoinPolicy               circlemodel.CircleJoinPolicy         `bson:"joinPolicy"`
		Kind                     circlemodel.CircleKind               `bson:"kind"`
		DisplaySubjectType       circlemodel.CircleDisplaySubjectType `bson:"displaySubjectType"`
		FollowEnabled            bool                                 `bson:"followEnabled"`
		DefaultPublicGroupID     string                               `bson:"defaultPublicGroupId"`
		LinkedHomepageID         string                               `bson:"linkedHomepageId"`
		LinkedHomepageType       circlemodel.HomepageType             `bson:"linkedHomepageType"`
		LinkedHomepageTitle      string                               `bson:"linkedHomepageTitle"`
		CreatedAt                time.Time                            `bson:"createdAt"`
		UpdatedAt                time.Time                            `bson:"updatedAt"`
	}
	var documents []struct {
		MembershipID string                `bson:"membershipId"`
		Circle       circleSummaryDocument `bson:"circle"`
	}
	if err := rows.All(ctx, &documents); err != nil {
		return membershipports.PersonaCircleSlice{}, fmt.Errorf(
			"decode Persona Circles: %w",
			err,
		)
	}
	result := membershipports.PersonaCircleSlice{
		Items: make([]membershipports.CircleSummary, 0, min(limit, len(documents))),
	}
	for index, row := range documents {
		if index >= limit {
			result.Cursor = documents[index-1].MembershipID
			break
		}
		document := row.Circle
		if document.Tags == nil {
			document.Tags = []string{}
		}
		result.Items = append(result.Items, membershipports.CircleSummary{
			ID: document.ID, Name: document.Name, Description: document.Description,
			CoverURL: document.CoverURL, IconURL: document.IconURL, OwnerPersonaID: document.OwnerPersonaID,
			OwnerDisplayNameSnapshot: document.OwnerDisplayNameSnapshot, Category: document.Category,
			SubCategory: document.SubCategory, Tags: document.Tags, MemberCount: document.MemberCount,
			PostCount: document.PostCount, WeeklyActiveCount: document.WeeklyActiveCount, Status: document.Status,
			Visibility: document.Visibility, JoinPolicy: document.JoinPolicy, Kind: document.Kind,
			DisplaySubjectType: document.DisplaySubjectType, FollowEnabled: document.FollowEnabled,
			DefaultPublicGroupID: document.DefaultPublicGroupID, LinkedHomepageID: document.LinkedHomepageID,
			LinkedHomepageType: document.LinkedHomepageType, LinkedHomepageTitle: document.LinkedHomepageTitle,
			CreatedAt: document.CreatedAt.UTC(), UpdatedAt: document.UpdatedAt.UTC(),
		})
	}
	return result, nil
}

func (readers *MongoReaders) list(ctx context.Context, filter bson.M, limit int, cursor string) (membershipports.MembershipSlice, error) {
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	if cursor = strings.TrimSpace(cursor); cursor != "" {
		filter["_id"] = bson.M{"$gt": cursor}
	}
	queryLimit := int64(limit + 1)
	cursorRows, err := readers.memberships.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(queryLimit))
	if err != nil {
		return membershipports.MembershipSlice{}, fmt.Errorf("list CircleMemberships: %w", err)
	}
	defer cursorRows.Close(ctx)
	var documents []membershipDocument
	if err := cursorRows.All(ctx, &documents); err != nil {
		return membershipports.MembershipSlice{}, fmt.Errorf("decode CircleMemberships: %w", err)
	}
	result := membershipports.MembershipSlice{Items: make([]membershipmodel.CircleMembership, 0, min(limit, len(documents)))}
	for index, document := range documents {
		if index >= limit {
			result.Cursor = documents[index-1].ID
			break
		}
		result.Items = append(result.Items, document.toModel())
	}
	return result, nil
}

var (
	_ membershipports.CirclePolicyReader  = (*MongoReaders)(nil)
	_ membershipports.MembershipReader    = (*MongoReaders)(nil)
	_ membershipports.PersonaCircleReader = (*MongoReaders)(nil)
)
