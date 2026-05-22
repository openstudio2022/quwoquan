package recommendation

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

// MongoCandidateSource reads candidates from the rm_discovery_feed projection.
// Aligned with contracts/metadata/_projections/discovery_feed.yaml.
type MongoCandidateSource struct {
	coll *mongo.Collection
}

func NewMongoCandidateSource(db *mongo.Database) *MongoCandidateSource {
	return &MongoCandidateSource{coll: db.Collection("rm_discovery_feed")}
}

func (s *MongoCandidateSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 60
	}

	filter := bson.M{}
	if len(req.Tags) > 0 {
		filter["tags"] = bson.M{"$in": req.Tags}
	}

	opts := options.Find().
		SetSort(bson.D{{Key: "recScore", Value: -1}, {Key: "publishedAt", Value: -1}}).
		SetLimit(int64(limit))

	if req.Cursor != "" {
		filter["_id"] = bson.M{"$lt": req.Cursor}
	}

	cursor, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var results []discoveryFeedDoc
	if err := cursor.All(ctx, &results); err != nil {
		return nil, err
	}

	out := make([]rtrec.ContentCandidate, 0, len(results))
	for _, doc := range results {
		out = append(out, rtrec.ContentCandidate{
			ContentID:    doc.PostID,
			ContentType:  doc.ContentType,
			AuthorID:     doc.AuthorID,
			Title:        doc.Title,
			Tags:         doc.Tags,
			EntityRefs:   doc.EntityRefs,
			PublishedAt:  doc.PublishedAt,
			ViewCount:    doc.ViewCount,
			LikeCount:    doc.LikeCount,
			CommentCount: doc.CommentCount,
			ShareCount:   doc.ShareCount,
			RecallPath:   "mongo_discovery",
		})
	}
	return out, nil
}

type discoveryFeedDoc struct {
	PostID        string    `bson:"postId"`
	ContentType   string    `bson:"contentType"`
	AuthorID      string    `bson:"authorId"`
	Title         string    `bson:"title"`
	Tags          []string  `bson:"tags"`
	EntityRefs    []string  `bson:"entityRefs"`
	CoverURL      string    `bson:"coverUrl"`
	LikeCount     int64     `bson:"likeCount"`
	CommentCount  int64     `bson:"commentCount"`
	ShareCount    int64     `bson:"shareCount"`
	FavoriteCount int64     `bson:"favoriteCount"`
	ViewCount     int64     `bson:"viewCount"`
	PublishedAt   time.Time `bson:"publishedAt"`
	RecScore      float64   `bson:"recScore"`
}
