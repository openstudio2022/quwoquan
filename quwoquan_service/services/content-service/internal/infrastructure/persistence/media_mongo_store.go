package persistence

import "go.mongodb.org/mongo-driver/v2/mongo"

// MongoMediaStore is the sole production persistence adapter for
// MediaUploadSession and MediaAsset. It has no process-memory fallback.
type MongoMediaStore struct {
	uploadSessions           *mongo.Collection
	assets                   *mongo.Collection
	sessionReceipts          *mongo.Collection
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
}

func NewMongoMediaStore(uploadSessions *mongo.Collection) *MongoMediaStore {
	if uploadSessions == nil {
		panic("NewMongoMediaStore requires media_upload_sessions collection")
	}
	db := uploadSessions.Database()
	return &MongoMediaStore{
		uploadSessions:           uploadSessions,
		assets:                   db.Collection("media_assets"),
		sessionReceipts:          db.Collection("media_upload_session_command_receipts"),
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
	}
}
