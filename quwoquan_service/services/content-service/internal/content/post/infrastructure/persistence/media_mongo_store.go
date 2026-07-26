package persistence

import (
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/content-service/internal/content/post/infrastructure/mediaobjectfence"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/mediareferencefence"
)

// MongoMediaStore owns the durable MediaAsset, original-access, processing,
// and media outbox adapters. MediaUploadSession has its own object store.
type MongoMediaStore struct {
	assets                   *mongo.Collection
	assetReceipts            *mongo.Collection
	sessionOutbox            *mongo.Collection
	assetOutbox              *mongo.Collection
	originalAccessFacts      *mongo.Collection
	originalAccessReceipts   *mongo.Collection
	originalAccessRateLimits *mongo.Collection
	checkpoints              *mongo.Collection
	processingDeadLetters    *mongo.Collection
	imageReprocessRuns       *mongo.Collection
	imageReprocessReceipts   *mongo.Collection
	imageReprocessLeases     *mongo.Collection
	objectFences             *mediaobjectfence.Manager
	referenceFences          *mediareferencefence.Manager
}

func NewMongoMediaStore(db *mongo.Database) *MongoMediaStore {
	if db == nil {
		panic("NewMongoMediaStore requires database")
	}
	objectFences, err := mediaobjectfence.New(db)
	if err != nil {
		panic(err)
	}
	referenceFences, err := mediareferencefence.New(db)
	if err != nil {
		panic(err)
	}
	return &MongoMediaStore{
		assets:                   db.Collection("media_assets"),
		assetReceipts:            db.Collection("media_asset_command_receipts"),
		sessionOutbox:            db.Collection("media_upload_session_outbox"),
		assetOutbox:              db.Collection("media_asset_outbox"),
		originalAccessFacts:      db.Collection("media_original_access_facts"),
		originalAccessReceipts:   db.Collection("media_original_access_receipts"),
		originalAccessRateLimits: db.Collection("media_original_access_rate_limits"),
		checkpoints:              db.Collection("media_projection_checkpoints"),
		processingDeadLetters:    db.Collection("media_processing_dead_letters"),
		imageReprocessRuns:       db.Collection("media_image_reprocess_runs"),
		imageReprocessReceipts:   db.Collection("media_image_reprocess_run_receipts"),
		imageReprocessLeases:     db.Collection("media_image_reprocess_run_leases"),
		objectFences:             objectFences,
		referenceFences:          referenceFences,
	}
}
