package persistence

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	outboundshareapp "quwoquan_service/services/content-service/internal/application/content/outbound_share_fact/command"
)

// MongoDiscoveryFeedShareCountWriter 把 OutboundShareFact 权威计数投影到
// 推荐召回读模型。公开已发布 Post 的 feed row 尚未建立时返回 false，
// relay 保留 checkpoint 重试；非公开/已删除 Post 的缺失视为已收敛。
type MongoDiscoveryFeedShareCountWriter struct {
	collection *mongo.Collection
	posts      *mongo.Collection
}

func NewMongoDiscoveryFeedShareCountWriter(
	db *mongo.Database,
) *MongoDiscoveryFeedShareCountWriter {
	return &MongoDiscoveryFeedShareCountWriter{
		collection: db.Collection("rm_discovery_feed"),
		posts:      db.Collection("posts"),
	}
}

func (w *MongoDiscoveryFeedShareCountWriter) SetShareCount(
	ctx context.Context,
	postID string,
	count int64,
) (bool, error) {
	if w == nil || w.collection == nil || w.posts == nil {
		return false, fmt.Errorf("DiscoveryFeed share-count writer is not configured")
	}
	postID = strings.TrimSpace(postID)
	if postID == "" || count < 0 {
		return false, fmt.Errorf("DiscoveryFeed share-count projection is invalid")
	}
	result, err := w.collection.UpdateOne(
		ctx,
		bson.M{"postId": postID},
		bson.M{"$set": bson.M{"shareCount": count}},
	)
	if err != nil {
		return false, err
	}
	if result.MatchedCount == 1 {
		return true, nil
	}
	return discoveryFeedCountTargetConverged(ctx, w.posts, postID)
}

var (
	_ outboundshareapp.ShareCountProjectionWriter = (*MongoPostStore)(nil)
	_ outboundshareapp.ShareCountProjectionWriter = (*MongoDiscoveryFeedShareCountWriter)(nil)
)
