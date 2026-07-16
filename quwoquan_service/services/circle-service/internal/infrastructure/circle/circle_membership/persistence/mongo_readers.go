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

	membershipmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/model"
	membershipports "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/ports"
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
	}, limit, cursor)
}

func (readers *MongoReaders) ListPersonaMemberships(ctx context.Context, personaID string, limit int, cursor string) (membershipports.MembershipSlice, error) {
	return readers.list(ctx, bson.M{
		"personaId": strings.TrimSpace(personaID), "state": membershipmodel.CircleMembershipStateActive,
	}, limit, cursor)
}

func (readers *MongoReaders) ReadCircleSummaries(ctx context.Context, circleIDs []string) ([]membershipports.CircleSummary, error) {
	cleaned := make([]string, 0, len(circleIDs))
	for _, circleID := range circleIDs {
		if circleID = strings.TrimSpace(circleID); circleID != "" {
			cleaned = append(cleaned, circleID)
		}
	}
	if len(cleaned) == 0 {
		return []membershipports.CircleSummary{}, nil
	}
	rows, err := readers.circles.Find(ctx, bson.M{"_id": bson.M{"$in": cleaned}})
	if err != nil {
		return nil, fmt.Errorf("read Circle summaries: %w", err)
	}
	defer rows.Close(ctx)
	type circleSummaryDocument struct {
		ID                       string    `bson:"_id"`
		Name                     string    `bson:"name"`
		Description              string    `bson:"description"`
		CoverURL                 string    `bson:"coverUrl"`
		IconURL                  string    `bson:"iconUrl"`
		OwnerPersonaID           string    `bson:"ownerId"`
		OwnerDisplayNameSnapshot string    `bson:"ownerDisplayNameSnapshot"`
		Category                 string    `bson:"category"`
		SubCategory              string    `bson:"subCategory"`
		Tags                     []string  `bson:"tags"`
		MemberCount              int64     `bson:"memberCount"`
		PostCount                int64     `bson:"postCount"`
		WeeklyActiveCount        int64     `bson:"weeklyActiveCount"`
		State                    string    `bson:"status"`
		Visibility               string    `bson:"visibility"`
		JoinPolicy               string    `bson:"joinPolicy"`
		Kind                     string    `bson:"kind"`
		DisplaySubjectType       string    `bson:"displaySubjectType"`
		FollowEnabled            bool      `bson:"followEnabled"`
		DefaultPublicGroupID     string    `bson:"defaultPublicGroupId"`
		LinkedHomepageID         string    `bson:"linkedHomepageId"`
		LinkedHomepageType       string    `bson:"linkedHomepageType"`
		LinkedHomepageTitle      string    `bson:"linkedHomepageTitle"`
		CreatedAt                time.Time `bson:"createdAt"`
		UpdatedAt                time.Time `bson:"updatedAt"`
	}
	byID := make(map[string]membershipports.CircleSummary, len(cleaned))
	for rows.Next(ctx) {
		var document circleSummaryDocument
		if err := rows.Decode(&document); err != nil {
			return nil, err
		}
		if document.Tags == nil {
			document.Tags = []string{}
		}
		byID[document.ID] = membershipports.CircleSummary{
			ID: document.ID, Name: document.Name, Description: document.Description,
			CoverURL: document.CoverURL, IconURL: document.IconURL, OwnerPersonaID: document.OwnerPersonaID,
			OwnerDisplayNameSnapshot: document.OwnerDisplayNameSnapshot, Category: document.Category,
			SubCategory: document.SubCategory, Tags: document.Tags, MemberCount: document.MemberCount,
			PostCount: document.PostCount, WeeklyActiveCount: document.WeeklyActiveCount, State: document.State,
			Visibility: document.Visibility, JoinPolicy: document.JoinPolicy, Kind: document.Kind,
			DisplaySubjectType: document.DisplaySubjectType, FollowEnabled: document.FollowEnabled,
			DefaultPublicGroupID: document.DefaultPublicGroupID, LinkedHomepageID: document.LinkedHomepageID,
			LinkedHomepageType: document.LinkedHomepageType, LinkedHomepageTitle: document.LinkedHomepageTitle,
			CreatedAt: document.CreatedAt.UTC(), UpdatedAt: document.UpdatedAt.UTC(),
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	result := make([]membershipports.CircleSummary, 0, len(byID))
	for _, circleID := range cleaned {
		if summary, exists := byID[circleID]; exists {
			result = append(result, summary)
		}
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
	_ membershipports.CircleSummaryReader = (*MongoReaders)(nil)
)
