package persistence

import (
	"context"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func (s *MongoMediaStore) EnsureIndexes(ctx context.Context) error {
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
		{
			Keys:    bson.D{{Key: "manualCoverAssetId", Value: 1}, {Key: "processingStatus", Value: 1}},
			Options: options.Index().SetName("idx_media_assets_manual_cover_status"),
		},
	}); err != nil {
		return fmt.Errorf("create media asset indexes: %w", err)
	}
	if err := ensureMediaReceiptIndexes(ctx, s.assetReceipts, "idx_media_asset_receipts"); err != nil {
		return err
	}
	if err := ensureMediaOutboxIndexes(ctx, s.assetOutbox, "idx_media_asset_outbox"); err != nil {
		return err
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
