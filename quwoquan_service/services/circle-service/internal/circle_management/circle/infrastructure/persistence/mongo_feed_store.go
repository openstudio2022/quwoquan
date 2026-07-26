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

	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

// MongoFeedStore 通过 Post 本地投影与 CirclePostPlacement 聚合读模型的
// 联合查询实现圈子动态流。Post 可同时放入多个圈子，因此 pin/feature
// 必须以 placement 为粒度，禁止写回共享 Post 文档。
type MongoFeedStore struct {
	posts      *mongo.Collection
	placements *mongo.Collection
}

var _ application.CircleFeedStore = (*MongoFeedStore)(nil)

func NewMongoFeedStore(database *mongo.Database) *MongoFeedStore {
	if database == nil {
		panic("circle feed store requires database")
	}
	return &MongoFeedStore{
		posts:      database.Collection("posts"),
		placements: database.Collection("circle_post_placements"),
	}
}

func (s *MongoFeedStore) ListCirclePosts(
	ctx context.Context,
	circleID string,
	opts application.ListCirclePostsQuery,
) ([]application.CircleFeedPost, string, error) {
	return s.listPostsForCircleIDs(ctx, []string{strings.TrimSpace(circleID)}, opts)
}

func (s *MongoFeedStore) listPostsForCircleIDs(
	ctx context.Context,
	circleIDs []string,
	query application.ListCirclePostsQuery,
) ([]application.CircleFeedPost, string, error) {
	circleIDs = compactStrings(circleIDs)
	if len(circleIDs) == 0 {
		return []application.CircleFeedPost{}, "", nil
	}
	if query.Limit <= 0 {
		query.Limit = 20
	}
	if query.Limit > 200 {
		query.Limit = 200
	}

	postFilter := bson.M{"status": "published"}
	if identity := strings.TrimSpace(query.Identity); identity != "" {
		postFilter["contentIdentity"] = identity
	}
	if contentType := strings.TrimSpace(query.Type); contentType != "" {
		postFilter["contentType"] = contentType
	}
	pipeline := mongo.Pipeline{
		bson.D{{Key: "$match", Value: bson.M{
			"circleId": bson.M{"$in": circleIDs},
			"state":    "active",
		}}},
		bson.D{{Key: "$lookup", Value: bson.D{
			{Key: "from", Value: "posts"},
			{Key: "localField", Value: "postId"},
			{Key: "foreignField", Value: "_id"},
			{Key: "as", Value: "post"},
		}}},
		bson.D{{Key: "$unwind", Value: "$post"}},
		bson.D{{Key: "$replaceRoot", Value: bson.M{
			"newRoot": bson.M{"$mergeObjects": bson.A{
				"$post",
				bson.M{"circlePlacement": "$$ROOT"},
			}},
		}}},
		bson.D{{Key: "$match", Value: postFilter}},
	}
	if cursor := strings.TrimSpace(query.Cursor); cursor != "" {
		cursorFilter, err := decodeFeedCursorFilter(cursor, query.Sort)
		if err != nil {
			return nil, "", err
		}
		pipeline = append(pipeline, bson.D{{Key: "$match", Value: cursorFilter}})
	}
	pipeline = append(
		pipeline,
		bson.D{{Key: "$sort", Value: feedSortOrder(query.Sort)}},
		bson.D{{Key: "$limit", Value: int64(query.Limit)}},
	)
	cur, err := s.placements.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, "", fmt.Errorf("list circle feed posts: %w", err)
	}
	defer cur.Close(ctx)

	var docs []mongoCircleFeedPostDocument
	if err := cur.All(ctx, &docs); err != nil {
		return nil, "", fmt.Errorf("decode circle feed posts: %w", err)
	}
	items := make([]application.CircleFeedPost, 0, len(docs))
	for _, doc := range docs {
		items = append(items, doc.toProjection())
	}

	nextCursor := ""
	if len(docs) == query.Limit {
		nextCursor, err = encodeFeedCursor(docs[len(docs)-1], query.Sort)
		if err != nil {
			return nil, "", err
		}
	}
	return items, nextCursor, nil
}

type mongoCircleFeedIntersectionReason struct {
	Kind          string  `bson:"kind"`
	PrimaryText   string  `bson:"primaryText"`
	SecondaryText string  `bson:"secondaryText"`
	Strength      float64 `bson:"strength"`
	StrengthScore float64 `bson:"strengthScore"`
}

type mongoCircleFeedPlacementDocument struct {
	ID         string    `bson:"_id"`
	CircleID   string    `bson:"circleId"`
	Pinned     bool      `bson:"pinned"`
	Featured   bool      `bson:"featured"`
	PinnedAt   time.Time `bson:"pinnedAt"`
	FeaturedAt time.Time `bson:"featuredAt"`
}

type mongoCircleFeedPostDocument struct {
	ID                        string                              `bson:"_id"`
	ContentType               string                              `bson:"contentType"`
	ContentIdentity           string                              `bson:"contentIdentity"`
	AssistantUsePolicy        string                              `bson:"assistantUsePolicy"`
	AuthorID                  string                              `bson:"authorId"`
	AuthorDisplayName         string                              `bson:"authorDisplayName"`
	AuthorDisplayNameSnapshot string                              `bson:"authorDisplayNameSnapshot"`
	AuthorAvatarURL           string                              `bson:"authorAvatarUrl"`
	AuthorAvatarURLSnapshot   string                              `bson:"authorAvatarUrlSnapshot"`
	AuthorBackgroundURL       string                              `bson:"authorBackgroundUrl"`
	AuthorRoleLabel           string                              `bson:"authorRoleLabel"`
	AuthorIdentityTags        []string                            `bson:"authorIdentityTags"`
	AuthorVerified            bool                                `bson:"authorVerified"`
	Title                     string                              `bson:"title"`
	Body                      string                              `bson:"body"`
	Summary                   string                              `bson:"summary"`
	CoverURL                  string                              `bson:"coverUrl"`
	ImageURLs                 []string                            `bson:"imageUrls"`
	MediaURLs                 []string                            `bson:"mediaUrls"`
	VideoURL                  string                              `bson:"videoUrl"`
	ThumbnailURL              string                              `bson:"thumbnailUrl"`
	Width                     int64                               `bson:"width"`
	Height                    int64                               `bson:"height"`
	DurationMs                int64                               `bson:"durationMs"`
	LikeCount                 int64                               `bson:"likeCount"`
	CommentCount              int64                               `bson:"commentCount"`
	ShareCount                int64                               `bson:"shareCount"`
	CreatedAt                 time.Time                           `bson:"createdAt"`
	UpdatedAt                 time.Time                           `bson:"updatedAt"`
	PublishedAt               time.Time                           `bson:"publishedAt"`
	ContentVertical           string                              `bson:"contentVertical"`
	RecallPath                string                              `bson:"recallPath"`
	SupplySource              string                              `bson:"supplySource"`
	IntersectionReasons       []mongoCircleFeedIntersectionReason `bson:"intersectionReasons"`
	CirclePlacement           mongoCircleFeedPlacementDocument    `bson:"circlePlacement"`
}

func (doc mongoCircleFeedPostDocument) toProjection() application.CircleFeedPost {
	imageURLs := doc.ImageURLs
	if len(imageURLs) == 0 {
		imageURLs = doc.MediaURLs
	}
	displayName := strings.TrimSpace(doc.AuthorDisplayName)
	if displayName == "" {
		displayName = strings.TrimSpace(doc.AuthorDisplayNameSnapshot)
	}
	avatarURL := strings.TrimSpace(doc.AuthorAvatarURL)
	if avatarURL == "" {
		avatarURL = strings.TrimSpace(doc.AuthorAvatarURLSnapshot)
	}
	reasons := make([]application.CircleFeedIntersectionReason, 0, len(doc.IntersectionReasons))
	for _, reason := range doc.IntersectionReasons {
		strength := reason.Strength
		if strength == 0 {
			strength = reason.StrengthScore
		}
		reasons = append(reasons, application.CircleFeedIntersectionReason{
			Kind: reason.Kind, PrimaryText: reason.PrimaryText,
			SecondaryText: reason.SecondaryText, Strength: strength,
		})
	}
	return application.CircleFeedPost{
		CircleID: doc.CirclePlacement.CircleID, PlacementID: doc.CirclePlacement.ID,
		PostID:      doc.ID,
		ContentType: doc.ContentType, ContentIdentity: doc.ContentIdentity,
		AssistantUsePolicy: doc.AssistantUsePolicy,
		AuthorID:           doc.AuthorID, AuthorDisplayName: displayName,
		AuthorAvatarURL: avatarURL, AuthorBackgroundURL: doc.AuthorBackgroundURL,
		AuthorRoleLabel: doc.AuthorRoleLabel, AuthorIdentityTags: doc.AuthorIdentityTags,
		AuthorVerified: doc.AuthorVerified, Title: doc.Title, Body: doc.Body,
		Summary: doc.Summary, CoverURL: doc.CoverURL, ImageURLs: imageURLs,
		VideoURL: doc.VideoURL, ThumbnailURL: doc.ThumbnailURL,
		Width: doc.Width, Height: doc.Height, DurationMs: doc.DurationMs,
		LikeCount: doc.LikeCount, CommentCount: doc.CommentCount, ShareCount: doc.ShareCount,
		CreatedAt: timePointer(doc.CreatedAt), UpdatedAt: timePointer(doc.UpdatedAt),
		PublishedAt: timePointer(doc.PublishedAt), ContentVertical: doc.ContentVertical,
		RecallPath: doc.RecallPath, SupplySource: doc.SupplySource,
		IntersectionReasons: reasons,
		Pinned:              doc.CirclePlacement.Pinned,
		Featured:            doc.CirclePlacement.Featured,
		PinnedAt:            timePointer(doc.CirclePlacement.PinnedAt),
		FeaturedAt:          timePointer(doc.CirclePlacement.FeaturedAt),
	}
}

type circleFeedCursor struct {
	Sort        string     `json:"sort"`
	PostID      string     `json:"postId"`
	PlacementID string     `json:"placementId"`
	LikeCount   int64      `json:"likeCount,omitempty"`
	CreatedAt   *time.Time `json:"createdAt,omitempty"`
	PinnedAt    *time.Time `json:"pinnedAt,omitempty"`
	FeaturedAt  *time.Time `json:"featuredAt,omitempty"`
}

func encodeFeedCursor(doc mongoCircleFeedPostDocument, sortMode string) (string, error) {
	cursor := circleFeedCursor{
		Sort: strings.TrimSpace(sortMode), PostID: doc.ID,
		PlacementID: doc.CirclePlacement.ID, LikeCount: doc.LikeCount,
		CreatedAt:  timePointer(doc.CreatedAt),
		PinnedAt:   timePointer(doc.CirclePlacement.PinnedAt),
		FeaturedAt: timePointer(doc.CirclePlacement.FeaturedAt),
	}
	if cursor.Sort == "" {
		cursor.Sort = "latest"
	}
	payload, err := json.Marshal(cursor)
	if err != nil {
		return "", fmt.Errorf("encode circle feed cursor: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(payload), nil
}

func decodeFeedCursorFilter(raw string, sortMode string) (bson.M, error) {
	payload, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return nil, fmt.Errorf("%w: base64: %v", application.ErrInvalidCircleFeedCursor, err)
	}
	var cursor circleFeedCursor
	if err := json.Unmarshal(payload, &cursor); err != nil {
		return nil, fmt.Errorf("%w: payload: %v", application.ErrInvalidCircleFeedCursor, err)
	}
	expectedSort := strings.TrimSpace(sortMode)
	if expectedSort == "" {
		expectedSort = "latest"
	}
	if cursor.PostID == "" || cursor.PlacementID == "" || cursor.Sort != expectedSort {
		return nil, fmt.Errorf("%w: cursor does not match sort %q", application.ErrInvalidCircleFeedCursor, expectedSort)
	}
	switch expectedSort {
	case "hot":
		return bson.M{"$or": []bson.M{
			{"likeCount": bson.M{"$lt": cursor.LikeCount}},
			{"likeCount": cursor.LikeCount, "_id": bson.M{"$lt": cursor.PostID}},
			{
				"likeCount":           cursor.LikeCount,
				"_id":                 cursor.PostID,
				"circlePlacement._id": bson.M{"$lt": cursor.PlacementID},
			},
		}}, nil
	case "featured":
		return featuredCursorFilter(cursor), nil
	default:
		if cursor.CreatedAt == nil {
			return nil, fmt.Errorf("%w: missing createdAt", application.ErrInvalidCircleFeedCursor)
		}
		return bson.M{"$or": []bson.M{
			{"createdAt": bson.M{"$lt": *cursor.CreatedAt}},
			{"createdAt": *cursor.CreatedAt, "_id": bson.M{"$lt": cursor.PostID}},
			{
				"createdAt":           *cursor.CreatedAt,
				"_id":                 cursor.PostID,
				"circlePlacement._id": bson.M{"$lt": cursor.PlacementID},
			},
		}}, nil
	}
}

func featuredCursorFilter(cursor circleFeedCursor) bson.M {
	branches := make([]bson.M, 0, 6)
	pinnedEqual := bson.M{"circlePlacement.pinnedAt": nil}
	if cursor.PinnedAt != nil {
		branches = append(branches, bson.M{"$or": []bson.M{
			{"circlePlacement.pinnedAt": bson.M{"$lt": *cursor.PinnedAt}},
			{"circlePlacement.pinnedAt": nil},
		}})
		pinnedEqual = bson.M{"circlePlacement.pinnedAt": *cursor.PinnedAt}
	}
	featuredEqual := bson.M{"circlePlacement.featuredAt": nil}
	if cursor.FeaturedAt != nil {
		branches = append(branches, bson.M{"$and": []bson.M{
			pinnedEqual,
			{"$or": []bson.M{
				{"circlePlacement.featuredAt": bson.M{"$lt": *cursor.FeaturedAt}},
				{"circlePlacement.featuredAt": nil},
			}},
		}})
		featuredEqual = bson.M{"circlePlacement.featuredAt": *cursor.FeaturedAt}
	}
	if cursor.CreatedAt != nil {
		branches = append(branches, bson.M{"$and": []bson.M{
			pinnedEqual, featuredEqual,
			{"$or": []bson.M{
				{"createdAt": bson.M{"$lt": *cursor.CreatedAt}},
				{"createdAt": *cursor.CreatedAt, "_id": bson.M{"$lt": cursor.PostID}},
				{
					"createdAt":           *cursor.CreatedAt,
					"_id":                 cursor.PostID,
					"circlePlacement._id": bson.M{"$lt": cursor.PlacementID},
				},
			}},
		}})
	}
	return bson.M{"$or": branches}
}

func timePointer(value time.Time) *time.Time {
	if value.IsZero() {
		return nil
	}
	normalized := value.UTC()
	return &normalized
}

func compactStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func feedSortOrder(sort string) bson.D {
	switch sort {
	case "hot":
		return bson.D{
			{Key: "likeCount", Value: -1},
			{Key: "_id", Value: -1},
			{Key: "circlePlacement._id", Value: -1},
		}
	case "featured":
		return bson.D{
			{Key: "circlePlacement.pinnedAt", Value: -1},
			{Key: "circlePlacement.featuredAt", Value: -1},
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
			{Key: "circlePlacement._id", Value: -1},
		}
	default: // "latest", "recommended" or empty
		return bson.D{
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
			{Key: "circlePlacement._id", Value: -1},
		}
	}
}
