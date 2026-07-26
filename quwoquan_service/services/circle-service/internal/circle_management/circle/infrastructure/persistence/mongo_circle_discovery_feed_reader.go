package persistence

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
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
			{Key: "weeklyActiveCount", Value: -1},
			{Key: "_id", Value: -1},
		},
		Options: options.Index().SetName("idx_circle_discovery_recommended_page"),
	}); err != nil {
		return fmt.Errorf("ensure circle discovery recommended page index: %w", err)
	}
	if _, err := reader.circles.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "status", Value: 1},
			{Key: "visibility", Value: 1},
			{Key: "category", Value: 1},
			{Key: "subCategory", Value: 1},
			{Key: "weeklyActiveCount", Value: -1},
			{Key: "memberCount", Value: -1},
			{Key: "_id", Value: -1},
		},
		Options: options.Index().SetName("idx_circle_discovery_active_page"),
	}); err != nil {
		return fmt.Errorf("ensure circle discovery active page index: %w", err)
	}
	if _, err := reader.circles.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "status", Value: 1},
			{Key: "visibility", Value: 1},
			{Key: "category", Value: 1},
			{Key: "subCategory", Value: 1},
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
		},
		Options: options.Index().SetName("idx_circle_discovery_latest_page"),
	}); err != nil {
		return fmt.Errorf("ensure circle discovery latest page index: %w", err)
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
	// 动态流从 placement 起始并按 postId 关联 Post；对应的 placement 索引由
	// CirclePostPlacement 聚合维护。这里不得复用旧 circleIds Post 索引名，
	// 否则升级后会因持久库中的同名旧索引而阻断整个服务启动。
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

	if cursor := strings.TrimSpace(query.Cursor); cursor != "" {
		cursorFilter, err := decodeCircleDiscoveryCursorFilter(cursor, query.Sort)
		if err != nil {
			return application.CircleDiscoveryFeedSlice{}, err
		}
		filter = bson.M{"$and": []bson.M{filter, cursorFilter}}
	}
	findOptions := options.Find().
		SetSort(circleDiscoverySort(query.Sort)).
		SetLimit(int64(query.Limit))
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
	items, _, err := reader.feed.listPostsForCircleIDs(ctx, circleIDs, application.ListCirclePostsQuery{
		Sort: "latest", Limit: query.Limit,
	})
	if err != nil {
		return application.CircleDiscoveryFeedSlice{}, err
	}
	nextCursor := ""
	if len(circles) == query.Limit {
		nextCursor, err = encodeCircleDiscoveryCursor(circles[len(circles)-1], query.Sort)
		if err != nil {
			return application.CircleDiscoveryFeedSlice{}, err
		}
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

type circleDiscoveryCursor struct {
	Sort              string     `json:"sort"`
	CircleID          string     `json:"circleId"`
	MemberCount       int64      `json:"memberCount,omitempty"`
	WeeklyActiveCount int64      `json:"weeklyActiveCount,omitempty"`
	CreatedAt         *time.Time `json:"createdAt,omitempty"`
}

func encodeCircleDiscoveryCursor(circle circlemodel.Circle, sortMode string) (string, error) {
	sortMode = normalizedCircleDiscoverySort(sortMode)
	cursor := circleDiscoveryCursor{
		Sort:              sortMode,
		CircleID:          circle.ID,
		MemberCount:       circle.MemberCount,
		WeeklyActiveCount: circle.WeeklyActiveCount,
	}
	if sortMode == "latest" {
		createdAt := circle.CreatedAt.UTC()
		cursor.CreatedAt = &createdAt
	}
	payload, err := json.Marshal(cursor)
	if err != nil {
		return "", fmt.Errorf("encode circle discovery cursor: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(payload), nil
}

func decodeCircleDiscoveryCursorFilter(raw, sortMode string) (bson.M, error) {
	payload, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(raw))
	if err != nil {
		return nil, fmt.Errorf("%w: discovery cursor base64: %v", application.ErrInvalidCircleFeedCursor, err)
	}
	var cursor circleDiscoveryCursor
	if err := json.Unmarshal(payload, &cursor); err != nil {
		return nil, fmt.Errorf("%w: discovery cursor payload: %v", application.ErrInvalidCircleFeedCursor, err)
	}
	expectedSort := normalizedCircleDiscoverySort(sortMode)
	if cursor.Sort != expectedSort || strings.TrimSpace(cursor.CircleID) == "" {
		return nil, fmt.Errorf("%w: discovery cursor does not match sort %q", application.ErrInvalidCircleFeedCursor, expectedSort)
	}
	switch expectedSort {
	case "latest":
		if cursor.CreatedAt == nil {
			return nil, fmt.Errorf("%w: discovery cursor missing createdAt", application.ErrInvalidCircleFeedCursor)
		}
		return bson.M{"$or": []bson.M{
			{"createdAt": bson.M{"$lt": cursor.CreatedAt.UTC()}},
			{"createdAt": cursor.CreatedAt.UTC(), "_id": bson.M{"$lt": cursor.CircleID}},
		}}, nil
	case "active":
		return bson.M{"$or": []bson.M{
			{"weeklyActiveCount": bson.M{"$lt": cursor.WeeklyActiveCount}},
			{"weeklyActiveCount": cursor.WeeklyActiveCount, "memberCount": bson.M{"$lt": cursor.MemberCount}},
			{"weeklyActiveCount": cursor.WeeklyActiveCount, "memberCount": cursor.MemberCount, "_id": bson.M{"$lt": cursor.CircleID}},
		}}, nil
	default:
		return bson.M{"$or": []bson.M{
			{"memberCount": bson.M{"$lt": cursor.MemberCount}},
			{"memberCount": cursor.MemberCount, "weeklyActiveCount": bson.M{"$lt": cursor.WeeklyActiveCount}},
			{"memberCount": cursor.MemberCount, "weeklyActiveCount": cursor.WeeklyActiveCount, "_id": bson.M{"$lt": cursor.CircleID}},
		}}, nil
	}
}

func normalizedCircleDiscoverySort(sortMode string) string {
	switch strings.TrimSpace(sortMode) {
	case "latest", "active":
		return strings.TrimSpace(sortMode)
	default:
		return "recommended"
	}
}
