package persistence

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
)

const (
	filterCatalogReleaseCollection = "filter_catalog_releases"
	filterCatalogReceiptCollection = "filter_catalog_command_receipts"
)

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.releases.Indexes().CreateMany(ctx, filterCatalogReleaseIndexes()); err != nil {
		return err
	}
	_, err := store.receipts.Indexes().CreateMany(ctx, filterCatalogReceiptIndexes())
	return err
}

func filterCatalogReleaseIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "releaseId", Value: 1}},
			Options: options.Index().
				SetName("idx_filter_catalog_release_id").
				SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "canonicalDigest", Value: 1}},
			Options: options.Index().
				SetName("idx_filter_catalog_digest").
				SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "status", Value: 1}},
			Options: options.Index().
				SetName("idx_filter_catalog_single_active").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"status": string(model.StatusActive)}),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "importedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_filter_catalog_status_imported"),
		},
		{
			Keys: bson.D{
				{Key: "releaseId", Value: 1},
				{Key: "version", Value: 1},
			},
			Options: options.Index().
				SetName("idx_filter_catalog_version").
				SetUnique(true),
		},
	}
}

func filterCatalogReceiptIndexes() []mongo.IndexModel {
	// receipt key 使用 Mongo 内建唯一 _id 索引；另建同 key 索引会被 Mongo
	// 判定为 IndexKeySpecsConflict。以下只创建 storage.yaml 中额外声明的索引。
	return []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: -1},
			},
			Options: options.Index().SetName("idx_filter_catalog_receipts_aggregate"),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().
				SetName("idx_filter_catalog_receipts_expire").
				SetExpireAfterSeconds(0),
		},
	}
}
