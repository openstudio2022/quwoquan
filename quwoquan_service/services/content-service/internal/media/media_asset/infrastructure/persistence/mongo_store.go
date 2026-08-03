package persistence

import (
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/mediaobjectfence"
	"quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/mediareferencefence"
)

// MongoMediaStore owns the durable MediaAsset, processing, and media outbox
// adapters. Sibling media objects have independent stores.
type MongoMediaStore struct {
	assets                *mongo.Collection
	assetReceipts         *mongo.Collection
	sessionOutbox         *mongo.Collection
	assetOutbox           *mongo.Collection
	checkpoints           *mongo.Collection
	processingDeadLetters *mongo.Collection
	objectFences          *mediaobjectfence.Manager
	referenceFences       *mediareferencefence.Manager
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
		assets:                db.Collection("media_assets"),
		assetReceipts:         db.Collection("media_asset_command_receipts"),
		sessionOutbox:         db.Collection("media_upload_session_outbox"),
		assetOutbox:           db.Collection("media_asset_outbox"),
		checkpoints:           db.Collection("media_projection_checkpoints"),
		processingDeadLetters: db.Collection("media_processing_dead_letters"),
		objectFences:          objectFences,
		referenceFences:       referenceFences,
	}
}
