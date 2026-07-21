package persistence

import (
	"context"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func (s *MongoMediaStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.uploadSessions.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "ownerId", Value: 1}, {Key: "status", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_media_upload_sessions_owner_status"),
		},
		{
			Keys:    bson.D{{Key: "objectKey", Value: 1}},
			Options: options.Index().SetName("idx_media_upload_sessions_object_key").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_media_upload_sessions_expire").SetExpireAfterSeconds(0),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_media_upload_sessions_version").SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("create media upload session indexes: %w", err)
	}
	if _, err := s.assets.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "ownerId", Value: 1}, {Key: "processingStatus", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_media_assets_owner_status"),
		},
		{
			Keys:    bson.D{{Key: "sourceSessionId", Value: 1}},
			Options: options.Index().SetName("idx_media_assets_source_session").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "objectKey", Value: 1}},
			Options: options.Index().SetName("idx_media_assets_object_key"),
		},
		{
			Keys:    bson.D{{Key: "sha256", Value: 1}},
			Options: options.Index().SetName("idx_media_assets_sha256"),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_media_assets_version").SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("create media asset indexes: %w", err)
	}
	if err := ensureMediaReceiptIndexes(ctx, s.sessionReceipts, "idx_media_upload_session_receipts"); err != nil {
		return err
	}
	if err := ensureMediaReceiptIndexes(ctx, s.assetReceipts, "idx_media_asset_receipts"); err != nil {
		return err
	}
	if err := ensureMediaOutboxIndexes(ctx, s.sessionOutbox, "idx_media_upload_session_outbox"); err != nil {
		return err
	}
	if err := ensureMediaOutboxIndexes(ctx, s.assetOutbox, "idx_media_asset_outbox"); err != nil {
		return err
	}
	if _, err := s.originalAccessFacts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "assetId", Value: 1}, {Key: "grantedAt", Value: -1}}, Options: options.Index().SetName("idx_media_original_access_asset_time")},
		{Keys: bson.D{{Key: "viewerId", Value: 1}, {Key: "assetId", Value: 1}, {Key: "purpose", Value: 1}, {Key: "grantedAt", Value: -1}}, Options: options.Index().SetName("idx_media_original_access_viewer_asset_purpose_time")},
		{Keys: bson.D{{Key: "viewerId", Value: 1}, {Key: "idempotencyKey", Value: 1}}, Options: options.Index().SetName("idx_media_original_access_dedupe").SetUnique(true)},
	}); err != nil {
		return fmt.Errorf("create media original access fact indexes: %w", err)
	}
	if _, err := s.originalAccessRateLimits.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_media_original_access_rate_limit_expire").SetExpireAfterSeconds(0),
	}); err != nil {
		return fmt.Errorf("create media original access rate limit indexes: %w", err)
	}
	if _, err := s.processingDeadLetters.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "consumer", Value: 1}, {Key: "quarantinedAt", Value: -1}},
			Options: options.Index().SetName(
				"idx_media_processing_dead_letters_consumer_time",
			),
		},
		{
			Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "quarantinedAt", Value: -1}},
			Options: options.Index().SetName(
				"idx_media_processing_dead_letters_aggregate_time",
			),
		},
	}); err != nil {
		return fmt.Errorf("create media processing dead-letter indexes: %w", err)
	}
	if _, err := s.imageReprocessRuns.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "updatedAt", Value: 1}}, Options: options.Index().SetName("idx_media_image_reprocess_run_status_updated")},
		{Keys: bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}}, Options: options.Index().SetName("idx_media_image_reprocess_run_version").SetUnique(true)},
	}); err != nil {
		return fmt.Errorf("create media image reprocess run indexes: %w", err)
	}
	if err := ensureMediaReceiptIndexes(ctx, s.imageReprocessReceipts, "idx_media_image_reprocess_run_receipts"); err != nil {
		return err
	}
	if _, err := s.imageReprocessLeases.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "leaseUntil", Value: 1}},
		Options: options.Index().SetName("idx_media_image_reprocess_run_lease_until"),
	}); err != nil {
		return fmt.Errorf("create media image reprocess run lease indexes: %w", err)
	}
	return nil
}

func ensureMediaReceiptIndexes(
	ctx context.Context,
	collection *mongo.Collection,
	prefix string,
) error {
	_, err := collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName(prefix + "_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName(prefix + "_expire").SetExpireAfterSeconds(0),
		},
	})
	if err != nil {
		return fmt.Errorf("create %s indexes: %w", prefix, err)
	}
	return nil
}

func ensureMediaOutboxIndexes(
	ctx context.Context,
	collection *mongo.Collection,
	prefix string,
) error {
	_, err := collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName(prefix + "_aggregate_version").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
			Options: options.Index().SetName(prefix + "_replay"),
		},
	})
	if err != nil {
		return fmt.Errorf("create %s indexes: %w", prefix, err)
	}
	return nil
}
