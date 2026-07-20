package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
)

// MongoDiscoveryFeedLikeCountWriter 只更新已由 Post 投影建立的 feed row。
// 未建立时返回 false，relay 保留 checkpoint 并重试，禁止凭 reaction 事件伪造 Post。
type MongoDiscoveryFeedLikeCountWriter struct {
	collection *mongo.Collection
	posts      *mongo.Collection
}

func NewMongoDiscoveryFeedLikeCountWriter(db *mongo.Database) *MongoDiscoveryFeedLikeCountWriter {
	return &MongoDiscoveryFeedLikeCountWriter{
		collection: db.Collection("rm_discovery_feed"),
		posts:      db.Collection("posts"),
	}
}

func (w *MongoDiscoveryFeedLikeCountWriter) SetLikeCount(
	ctx context.Context,
	postID string,
	count int64,
) (bool, error) {
	if w == nil || w.collection == nil || w.posts == nil {
		return false, fmt.Errorf("DiscoveryFeed like-count writer is not configured")
	}
	postID = strings.TrimSpace(postID)
	if postID == "" || count < 0 {
		return false, fmt.Errorf("DiscoveryFeed like-count projection is invalid")
	}
	result, err := w.collection.UpdateOne(
		ctx,
		bson.M{"postId": postID},
		bson.M{"$set": bson.M{"likeCount": count}},
	)
	if err != nil {
		return false, err
	}
	if result.MatchedCount == 1 {
		return true, nil
	}
	// Post 投影与 ContentReaction 投影拥有独立 checkpoint。若公开已发布
	// Post 的 feed row 尚未建立，必须保留 reaction checkpoint 等待重试；
	// 对已删除或私有 Post，feed row 本就不存在，缺失是已收敛状态。
	return discoveryFeedCountTargetConverged(ctx, w.posts, postID)
}

// MongoDiscoveryFeedCommentCountWriter 把 Comment 权威计数投影到召回读模型
// （N3-3 计数保鲜：此前 comment count 只刷 posts，rm_discovery_feed 的候选
// commentCount 长期陈旧，训练/排序特征失真）。语义与 like-count writer 同构。
type MongoDiscoveryFeedCommentCountWriter struct {
	collection *mongo.Collection
	posts      *mongo.Collection
}

func NewMongoDiscoveryFeedCommentCountWriter(db *mongo.Database) *MongoDiscoveryFeedCommentCountWriter {
	return &MongoDiscoveryFeedCommentCountWriter{
		collection: db.Collection("rm_discovery_feed"),
		posts:      db.Collection("posts"),
	}
}

func (w *MongoDiscoveryFeedCommentCountWriter) SetCommentCount(
	ctx context.Context,
	postID string,
	count int64,
) (bool, error) {
	if w == nil || w.collection == nil || w.posts == nil {
		return false, fmt.Errorf("DiscoveryFeed comment-count writer is not configured")
	}
	postID = strings.TrimSpace(postID)
	if postID == "" || count < 0 {
		return false, fmt.Errorf("DiscoveryFeed comment-count projection is invalid")
	}
	result, err := w.collection.UpdateOne(
		ctx,
		bson.M{"postId": postID},
		bson.M{"$set": bson.M{"commentCount": count}},
	)
	if err != nil {
		return false, err
	}
	if result.MatchedCount == 1 {
		return true, nil
	}
	// 与 like-count writer 同语义：公开已发布 Post 的 feed row 未建立时保留
	// checkpoint 等待重试；已删除/私有 Post 的缺失是收敛状态。
	return discoveryFeedCountTargetConverged(ctx, w.posts, postID)
}

func discoveryFeedCountTargetConverged(
	ctx context.Context,
	posts *mongo.Collection,
	postID string,
) (bool, error) {
	eligiblePosts, err := posts.CountDocuments(
		ctx,
		discoveryFeedEligiblePostFilter(postID),
		options.Count().SetLimit(1),
	)
	if err != nil {
		return false, err
	}
	return eligiblePosts == 0, nil
}

func discoveryFeedEligiblePostFilter(postID string) bson.M {
	return bson.M{
		"_id":              postID,
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
	}
}

// MongoRecommendFeatureLikeCountWriter 只写 ContentReaction 派生的精确计数。
// $max 避免旧事件重放使宽表 updatedAt 倒退。
type MongoRecommendFeatureLikeCountWriter struct {
	collection *mongo.Collection
}

func NewMongoRecommendFeatureLikeCountWriter(db *mongo.Database) *MongoRecommendFeatureLikeCountWriter {
	return &MongoRecommendFeatureLikeCountWriter{collection: db.Collection("rm_recommend_feature")}
}

func (w *MongoRecommendFeatureLikeCountWriter) SetPersonaLikeCount(
	ctx context.Context,
	personaID string,
	count int64,
	occurredAt time.Time,
) error {
	if w == nil || w.collection == nil {
		return fmt.Errorf("RecommendFeature like-count writer is not configured")
	}
	personaID = strings.TrimSpace(personaID)
	if personaID == "" || count < 0 || occurredAt.IsZero() {
		return fmt.Errorf("RecommendFeature like-count projection is invalid")
	}
	_, err := w.collection.UpdateOne(
		ctx,
		bson.M{"userId": personaID},
		bson.M{
			"$set": bson.M{
				"userId":                  personaID,
				"userFeatures.totalLikes": count,
			},
			"$max": bson.M{"updatedAt": occurredAt.UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

var (
	_ commentapp.CommentCountProjectionWriter      = (*MongoDiscoveryFeedCommentCountWriter)(nil)
	_ reactionapp.LikeCountProjectionWriter        = (*MongoDiscoveryFeedLikeCountWriter)(nil)
	_ reactionapp.PersonaLikeCountProjectionWriter = (*MongoRecommendFeatureLikeCountWriter)(nil)
)
