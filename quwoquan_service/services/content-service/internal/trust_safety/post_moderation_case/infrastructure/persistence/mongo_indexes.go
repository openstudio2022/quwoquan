package persistence

import (
	"context"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func (s *MongoPostModerationCaseStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.cases.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "postVersion", Value: 1},
				{Key: "contentDigest", Value: 1},
			},
			Options: options.Index().
				SetName("idx_post_moderation_cases_post_revision").
				SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "createdAt", Value: 1}},
			Options: options.Index().SetName("idx_post_moderation_cases_queue"),
		},
		{
			Keys:    bson.D{{Key: "reviewerId", Value: 1}, {Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_post_moderation_cases_reviewer").SetSparse(true),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "postVersion", Value: 1},
				{Key: "contentDigest", Value: 1},
				{Key: "status", Value: 1},
			},
			Options: options.Index().SetName("idx_post_moderation_cases_eligibility"),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_post_moderation_cases_version").SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("create post moderation case indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName("idx_post_moderation_case_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_post_moderation_case_receipts_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("create post moderation receipt indexes: %w", err)
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().
				SetName("idx_post_moderation_case_outbox_aggregate_version").
				SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
			Options: options.Index().SetName("idx_post_moderation_case_outbox_replay"),
		},
	}); err != nil {
		return fmt.Errorf("create post moderation outbox indexes: %w", err)
	}
	if _, err := s.audit.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "caseId", Value: 1}, {Key: "occurredAt", Value: 1}},
			Options: options.Index().SetName("idx_post_moderation_case_audit_case_time"),
		},
		{
			Keys:    bson.D{{Key: "reviewerId", Value: 1}, {Key: "occurredAt", Value: -1}},
			Options: options.Index().SetName("idx_post_moderation_case_audit_reviewer_time").SetSparse(true),
		},
	}); err != nil {
		return fmt.Errorf("create post moderation audit indexes: %w", err)
	}
	return nil
}
