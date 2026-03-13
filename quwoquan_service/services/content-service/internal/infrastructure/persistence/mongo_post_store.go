package persistence

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// MongoPostStore implements PostRepository backed by MongoDB.
// Used by L2 contract tests (testcontainers mongo:7) and production deployments.
type MongoPostStore struct {
	coll *mongo.Collection
}

func NewMongoPostStore(coll *mongo.Collection) *MongoPostStore {
	return &MongoPostStore{coll: coll}
}

func (s *MongoPostStore) Create(ctx context.Context, post *postmodel.Post) error {
	_, err := s.coll.InsertOne(ctx, post)
	return err
}

func (s *MongoPostStore) Update(ctx context.Context, id string, post *postmodel.Post) bool {
	result, err := s.coll.ReplaceOne(ctx, bson.M{"_id": id}, post)
	if err != nil {
		return false
	}
	return result.MatchedCount > 0
}

func (s *MongoPostStore) FindByID(ctx context.Context, id string) (*postmodel.Post, bool) {
	var post postmodel.Post
	err := s.coll.FindOne(ctx, bson.M{"_id": id}).Decode(&post)
	if err != nil {
		return nil, false
	}
	return &post, true
}

func (s *MongoPostStore) ListAll(ctx context.Context) []postmodel.Post {
	opts := options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}})
	cur, err := s.coll.Find(ctx, bson.M{}, opts)
	if err != nil {
		return nil
	}
	defer cur.Close(ctx)

	var posts []postmodel.Post
	if err := cur.All(ctx, &posts); err != nil {
		return nil
	}
	return posts
}

// ListPublished returns published/public posts in reverse-chronological order.
// cursor is the ID of the last item from the previous page; when set, only
// posts with createdAt earlier than the cursor document are returned.
func (s *MongoPostStore) ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post {
	if limit <= 0 {
		limit = 20
	}

	filter := bson.M{
		"status":     "published",
		"visibility": "public",
	}

	if cursor != "" {
		var cursorDoc postmodel.Post
		if err := s.coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
			filter["createdAt"] = bson.M{"$lt": cursorDoc.CreatedAt}
		}
	}

	opts := options.Find().
		SetSort(bson.D{{Key: "createdAt", Value: -1}}).
		SetLimit(int64(limit))

	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil
	}
	defer cur.Close(ctx)

	var posts []postmodel.Post
	if err := cur.All(ctx, &posts); err != nil {
		return nil
	}
	return posts
}

func (s *MongoPostStore) ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{
		"authorId": authorID,
		"status":   "published",
	}
	if cursor != "" {
		var cursorDoc postmodel.Post
		if err := s.coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
			filter["publishedAt"] = bson.M{"$lt": cursorDoc.PublishedAt}
		}
	}
	opts := options.Find().
		SetSort(bson.D{{Key: "publishedAt", Value: -1}}).
		SetLimit(int64(limit))

	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil
	}
	defer cur.Close(ctx)
	var posts []postmodel.Post
	if err := cur.All(ctx, &posts); err != nil {
		return nil
	}
	return posts
}
