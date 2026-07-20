package persistence

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/application"
	circlemodel "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

type MongoCircleDiscoveryFeedReader struct {
	circles     *mongo.Collection
	memberships *mongo.Collection
	feed        *MongoFeedStore
}

var _ application.CircleDiscoveryFeedReader = (*MongoCircleDiscoveryFeedReader)(nil)

func NewMongoCircleDiscoveryFeedReader(database *mongo.Database) *MongoCircleDiscoveryFeedReader {
	if database == nil {
		panic("circle discovery feed reader requires database")
	}
	return &MongoCircleDiscoveryFeedReader{
		circles:     database.Collection("circles"),
		memberships: database.Collection("circle_memberships"),
		feed:        NewMongoFeedStore(database),
	}
}

func (reader *MongoCircleDiscoveryFeedReader) EnsureIndexes(ctx context.Context) error {
	if _, err := reader.circles.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "status", Value: 1},
			{Key: "visibility", Value: 1},
			{Key: "category", Value: 1},
			{Key: "subCategory", Value: 1},
			{Key: "memberCount", Value: -1},
		},
		Options: options.Index().SetName("idx_circle_discovery_category"),
	}); err != nil {
		return fmt.Errorf("ensure circle discovery category index: %w", err)
	}
	if _, err := reader.memberships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "personaId", Value: 1},
			{Key: "state", Value: 1},
			{Key: "circleId", Value: 1},
		},
		Options: options.Index().SetName("idx_circle_discovery_membership"),
	}); err != nil {
		return fmt.Errorf("ensure circle discovery membership index: %w", err)
	}
	if _, err := reader.feed.posts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "status", Value: 1},
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
		},
		Options: options.Index().SetName("idx_circle_discovery_posts"),
	}); err != nil {
		return fmt.Errorf("ensure circle discovery post index: %w", err)
	}
	return nil
}

func (reader *MongoCircleDiscoveryFeedReader) ListCircleDiscoveryFeed(
	ctx context.Context,
	query application.CircleDiscoveryFeedQuery,
) (application.CircleDiscoveryFeedSlice, error) {
	memberCircleIDs, err := reader.activeMembershipCircleIDs(ctx, query.PersonaID)
	if err != nil {
		return application.CircleDiscoveryFeedSlice{}, err
	}
	if query.Scope == application.CircleDiscoveryFeedScopeMine && len(memberCircleIDs) == 0 {
		return application.CircleDiscoveryFeedSlice{
			Circles: []circlemodel.Circle{},
			Items:   []application.CircleFeedPost{},
		}, nil
	}

	filter := bson.M{"status": string(circlemodel.CircleStatusActive)}
	if category := strings.TrimSpace(query.Category); category != "" && category != "all" {
		filter["category"] = category
	}
	if subCategory := strings.TrimSpace(query.SubCategory); subCategory != "" && subCategory != "all" {
		filter["subCategory"] = subCategory
	}
	switch query.Scope {
	case application.CircleDiscoveryFeedScopeMine:
		filter["_id"] = bson.M{"$in": memberCircleIDs}
	default:
		filter["visibility"] = string(circlemodel.CircleVisibilityPublic)
		if len(memberCircleIDs) > 0 {
			filter["_id"] = bson.M{"$nin": memberCircleIDs}
		}
	}

	circleLimit := query.Limit
	if circleLimit > 50 {
		circleLimit = 50
	}
	findOptions := options.Find().
		SetSort(circleDiscoverySort(query.Sort)).
		SetLimit(int64(circleLimit))
	cursor, err := reader.circles.Find(ctx, filter, findOptions)
	if err != nil {
		return application.CircleDiscoveryFeedSlice{}, fmt.Errorf("list discovery circles: %w", err)
	}
	defer cursor.Close(ctx)

	var circles []circlemodel.Circle
	if err := cursor.All(ctx, &circles); err != nil {
		return application.CircleDiscoveryFeedSlice{}, fmt.Errorf("decode discovery circles: %w", err)
	}
	if len(circles) == 0 {
		return application.CircleDiscoveryFeedSlice{
			Circles: []circlemodel.Circle{},
			Items:   []application.CircleFeedPost{},
		}, nil
	}
	circleIDs := make([]string, 0, len(circles))
	for _, circle := range circles {
		circleIDs = append(circleIDs, circle.ID)
	}
	postSort := strings.TrimSpace(query.Sort)
	if postSort == "" || postSort == "recommended" || postSort == "active" {
		postSort = "latest"
	}
	items, nextCursor, err := reader.feed.listPostsForCircleIDs(ctx, circleIDs, application.ListCirclePostsQuery{
		Sort: postSort, Cursor: query.Cursor, Limit: query.Limit,
	})
	if err != nil {
		return application.CircleDiscoveryFeedSlice{}, err
	}
	return application.CircleDiscoveryFeedSlice{
		Circles: circles,
		Items:   items,
		Cursor:  nextCursor,
	}, nil
}

func (reader *MongoCircleDiscoveryFeedReader) activeMembershipCircleIDs(
	ctx context.Context,
	personaID string,
) ([]string, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return nil, nil
	}
	cursor, err := reader.memberships.Find(
		ctx,
		bson.M{"personaId": personaID, "state": "active"},
		options.Find().SetProjection(bson.M{"circleId": 1}),
	)
	if err != nil {
		return nil, fmt.Errorf("list active circle memberships: %w", err)
	}
	defer cursor.Close(ctx)
	var rows []struct {
		CircleID string `bson:"circleId"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, fmt.Errorf("decode active circle memberships: %w", err)
	}
	result := make([]string, 0, len(rows))
	for _, row := range rows {
		if circleID := strings.TrimSpace(row.CircleID); circleID != "" {
			result = append(result, circleID)
		}
	}
	return compactStrings(result), nil
}

func circleDiscoverySort(sortMode string) bson.D {
	switch strings.TrimSpace(sortMode) {
	case "latest":
		return bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}
	case "active":
		return bson.D{
			{Key: "weeklyActiveCount", Value: -1},
			{Key: "memberCount", Value: -1},
			{Key: "_id", Value: -1},
		}
	default:
		return bson.D{
			{Key: "memberCount", Value: -1},
			{Key: "weeklyActiveCount", Value: -1},
			{Key: "_id", Value: -1},
		}
	}
}
