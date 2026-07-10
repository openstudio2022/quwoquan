package persistence

import (
	"context"
	"log"
	"time"

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

func (s *MongoPostStore) AdjustCommentCount(ctx context.Context, id string, delta int64) (int64, bool, error) {
	var updated postmodel.Post
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": id},
		bson.M{
			"$inc": bson.M{"commentCount": delta},
			"$set": bson.M{"updatedAt": time.Now().UTC()},
		},
		options.FindOneAndUpdate().
			SetReturnDocument(options.After).
			SetProjection(bson.M{"commentCount": 1}),
	).Decode(&updated)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return 0, false, nil
		}
		return 0, false, err
	}
	return updated.CommentCount, true, nil
}

func (s *MongoPostStore) SetCommentCount(ctx context.Context, id string, count int64) (bool, error) {
	res, err := s.coll.UpdateOne(
		ctx,
		bson.M{"_id": id},
		bson.M{"$set": bson.M{"commentCount": count, "updatedAt": time.Now().UTC()}},
	)
	if err != nil {
		return false, err
	}
	return res.MatchedCount > 0, nil
}

func (s *MongoPostStore) ListAll(ctx context.Context) []postmodel.Post {
	opts := options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}})
	cur, err := s.coll.Find(ctx, bson.M{}, opts)
	if err != nil {
		log.Printf("WARN: post ListAll find: %v", err)
		return nil
	}
	defer cur.Close(ctx)

	// 逐条解码：单条脏文档（如 _id 非 string 的迁移前数据）不能让整批
	// 列表静默返回空，否则 search-backfill 等 reconcile 工具会误报 total=0。
	var posts []postmodel.Post
	skipped := 0
	for cur.Next(ctx) {
		var post postmodel.Post
		if err := cur.Decode(&post); err != nil {
			skipped++
			continue
		}
		posts = append(posts, post)
	}
	if err := cur.Err(); err != nil {
		log.Printf("WARN: post ListAll cursor: %v (decoded=%d)", err, len(posts))
	}
	if skipped > 0 {
		log.Printf("WARN: post ListAll skipped %d undecodable documents", skipped)
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
