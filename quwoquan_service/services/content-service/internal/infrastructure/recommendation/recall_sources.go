package recommendation

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

// TagRecallSource retrieves candidates matching user interest tags.
type TagRecallSource struct {
	coll *mongo.Collection
}

func NewTagRecallSource(db *mongo.Database) *TagRecallSource {
	return &TagRecallSource{coll: db.Collection("rm_discovery_feed")}
}

func (s *TagRecallSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	if len(req.Tags) == 0 {
		return nil, nil
	}
	limit := req.Limit
	if limit <= 0 {
		limit = 30
	}

	filter := bson.M{"tags": bson.M{"$in": req.Tags}}
	opts := options.Find().
		SetSort(bson.D{{Key: "recScore", Value: -1}, {Key: "publishedAt", Value: -1}}).
		SetLimit(int64(limit))

	return queryDiscoveryFeed(ctx, s.coll, filter, opts, "tag_recall")
}

// HotRecallSource retrieves trending content by engagement score.
type HotRecallSource struct {
	coll    *mongo.Collection
	maxAge  time.Duration
}

func NewHotRecallSource(db *mongo.Database, maxAge time.Duration) *HotRecallSource {
	if maxAge <= 0 {
		maxAge = 48 * time.Hour
	}
	return &HotRecallSource{coll: db.Collection("rm_discovery_feed"), maxAge: maxAge}
}

func (s *HotRecallSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 30
	}

	cutoff := time.Now().Add(-s.maxAge)
	filter := bson.M{
		"publishedAt": bson.M{"$gte": cutoff},
	}

	opts := options.Find().
		SetSort(bson.D{
			{Key: "likeCount", Value: -1},
			{Key: "viewCount", Value: -1},
			{Key: "publishedAt", Value: -1},
		}).
		SetLimit(int64(limit))

	return queryDiscoveryFeed(ctx, s.coll, filter, opts, "hot_recall")
}

// ExploreRecallSource retrieves random/fresh content for exploration.
type ExploreRecallSource struct {
	coll *mongo.Collection
}

func NewExploreRecallSource(db *mongo.Database) *ExploreRecallSource {
	return &ExploreRecallSource{coll: db.Collection("rm_discovery_feed")}
}

func (s *ExploreRecallSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 10
	}

	pipeline := bson.A{
		bson.M{"$sample": bson.M{"size": limit}},
	}

	cursor, err := s.coll.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var docs []discoveryFeedDoc
	if err := cursor.All(ctx, &docs); err != nil {
		return nil, err
	}

	out := make([]rtrec.ContentCandidate, 0, len(docs))
	for _, doc := range docs {
		out = append(out, rtrec.ContentCandidate{
			ContentID:    doc.PostID,
			ContentType:  doc.ContentType,
			AuthorID:     doc.AuthorID,
			Title:        doc.Title,
			Tags:         doc.Tags,
			PublishedAt:  doc.PublishedAt,
			ViewCount:    doc.ViewCount,
			LikeCount:    doc.LikeCount,
			CommentCount: doc.CommentCount,
			RecallPath:   "explore_recall",
		})
	}
	return out, nil
}

// AuthorRecallSource retrieves content from authors the user follows.
type AuthorRecallSource struct {
	feedColl   *mongo.Collection
	followColl *mongo.Collection
}

func NewAuthorRecallSource(db *mongo.Database) *AuthorRecallSource {
	return &AuthorRecallSource{
		feedColl:   db.Collection("rm_discovery_feed"),
		followColl: db.Collection("follow_edges"),
	}
}

func (s *AuthorRecallSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	if req.UserID == "" || req.UserID == "guest" {
		return nil, nil
	}

	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}

	// Fetch followed author IDs
	cursor, err := s.followColl.Find(ctx,
		bson.M{"followerId": req.UserID},
		options.Find().SetProjection(bson.M{"followeeId": 1}).SetLimit(200),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var followDocs []struct {
		FolloweeID string `bson:"followeeId"`
	}
	if err := cursor.All(ctx, &followDocs); err != nil {
		return nil, err
	}
	if len(followDocs) == 0 {
		return nil, nil
	}

	authorIDs := make([]string, 0, len(followDocs))
	for _, f := range followDocs {
		authorIDs = append(authorIDs, f.FolloweeID)
	}

	filter := bson.M{"authorId": bson.M{"$in": authorIDs}}
	opts := options.Find().
		SetSort(bson.D{{Key: "publishedAt", Value: -1}}).
		SetLimit(int64(limit))

	return queryDiscoveryFeed(ctx, s.feedColl, filter, opts, "author_recall")
}

func queryDiscoveryFeed(
	ctx context.Context,
	coll *mongo.Collection,
	filter bson.M,
	opts *options.FindOptionsBuilder,
	recallPath string,
) ([]rtrec.ContentCandidate, error) {
	cursor, err := coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var docs []discoveryFeedDoc
	if err := cursor.All(ctx, &docs); err != nil {
		return nil, err
	}

	out := make([]rtrec.ContentCandidate, 0, len(docs))
	for _, doc := range docs {
		out = append(out, rtrec.ContentCandidate{
			ContentID:    doc.PostID,
			ContentType:  doc.ContentType,
			AuthorID:     doc.AuthorID,
			Title:        doc.Title,
			Tags:         doc.Tags,
			PublishedAt:  doc.PublishedAt,
			ViewCount:    doc.ViewCount,
			LikeCount:    doc.LikeCount,
			CommentCount: doc.CommentCount,
			RecallPath:   recallPath,
		})
	}
	return out, nil
}
