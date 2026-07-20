package persistence

import (
	"context"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// EnsureIndexes creates exactly the named indexes declared by
// contracts/metadata/content/comment/storage.yaml.
func (s *MongoCommentDataAdapter) EnsureIndexes(ctx context.Context) error {
	if _, err := s.comments.Indexes().CreateMany(ctx, commentMongoIndexes()); err != nil {
		return fmt.Errorf("create comment aggregate indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, commentReceiptMongoIndexes()); err != nil {
		return fmt.Errorf("create comment receipt indexes: %w", err)
	}
	if _, err := s.rateLocks.Indexes().CreateMany(
		ctx,
		commentRateLockMongoIndexes(),
	); err != nil {
		return fmt.Errorf("create comment author rate-limit lock indexes: %w", err)
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, commentOutboxMongoIndexes()); err != nil {
		return fmt.Errorf("create comment outbox indexes: %w", err)
	}
	if _, err := s.checkpoints.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "updatedAt", Value: -1}},
		Options: options.Index().SetName("idx_comment_projection_checkpoint_updated"),
	}); err != nil {
		return fmt.Errorf("create comment checkpoint indexes: %w", err)
	}
	return nil
}

func commentMongoIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "parentCommentId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "isPinned", Value: -1},
				{Key: "pinnedAt", Value: -1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_post_page"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "parentCommentId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "isPinned", Value: -1},
				{Key: "pinnedAt", Value: -1},
				{Key: "hotScore", Value: -1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_post_hot_page"),
		},
		{
			Keys: bson.D{
				{Key: "authorId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_author_rate_window"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "_id", Value: 1},
			},
			Options: options.Index().SetName("idx_comments_post_status"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "parentCommentId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_reply_page"),
		},
		{
			Keys: bson.D{
				{Key: "parentCommentId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_parent_summary"),
		},
		{
			Keys: bson.D{
				{Key: "authorId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_author_page"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "createdAt", Value: 1},
			},
			Options: options.Index().SetName("idx_comments_post_created_at"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "deletedAt", Value: 1},
			},
			Options: options.Index().SetName("idx_comments_post_deleted_at"),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_comments_version").SetUnique(true),
		},
	}
}

func commentReceiptMongoIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName("idx_comment_command_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_comment_command_receipts_expire").SetExpireAfterSeconds(0),
		},
	}
}

func commentRateLockMongoIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{{
		Keys: bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().
			SetName("idx_comment_author_rate_limit_locks_expire").
			SetExpireAfterSeconds(0),
	}}
}

func commentOutboxMongoIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
			Options: options.Index().SetName("idx_comment_outbox_replay"),
		},
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().
				SetName("idx_comment_outbox_aggregate_version").
				SetUnique(true),
		},
	}
}
