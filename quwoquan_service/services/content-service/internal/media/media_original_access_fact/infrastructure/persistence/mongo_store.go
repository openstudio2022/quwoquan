package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
	originalaccessports "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/ports"
)

// MongoStore exclusively owns the immutable decision facts and idempotency
// receipts of MediaOriginalAccessFact. Quota rows belong to OriginalAccessQuota.
type MongoStore struct {
	facts    *mongo.Collection
	receipts *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("MediaOriginalAccessFact MongoStore requires database")
	}
	return &MongoStore{
		facts:    database.Collection("media_original_access_facts"),
		receipts: database.Collection("media_original_access_receipts"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.facts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "assetId", Value: 1}, {Key: "grantedAt", Value: -1}}, Options: options.Index().SetName("idx_media_original_access_asset_time")},
		{Keys: bson.D{{Key: "viewerId", Value: 1}, {Key: "assetId", Value: 1}, {Key: "purpose", Value: 1}, {Key: "grantedAt", Value: -1}}, Options: options.Index().SetName("idx_media_original_access_viewer_asset_purpose_time")},
		{Keys: bson.D{{Key: "viewerId", Value: 1}, {Key: "idempotencyKey", Value: 1}}, Options: options.Index().SetName("idx_media_original_access_dedupe").SetUnique(true)},
	})
	return err
}

type mediaOriginalAccessFactDocument struct {
	AuditID        string     `bson:"_id"`
	AssetID        string     `bson:"assetId"`
	ViewerID       string     `bson:"viewerId"`
	Purpose        string     `bson:"purpose"`
	Outcome        string     `bson:"outcome"`
	Reason         string     `bson:"reason"`
	IdempotencyKey string     `bson:"idempotencyKey"`
	GrantedAt      time.Time  `bson:"grantedAt"`
	ExpiresAt      *time.Time `bson:"expiresAt,omitempty"`
}

type mediaOriginalAccessReceiptDocument struct {
	ID            string                          `bson:"_id"`
	CommandDigest string                          `bson:"commandDigest"`
	Fact          mediaOriginalAccessFactDocument `bson:"fact"`
}

func (s *MongoStore) Append(
	ctx context.Context,
	request originalaccessports.AppendRequest,
) (originalaccessports.AppendResult, error) {
	if err := request.Fact.Validate(); err != nil {
		return originalaccessports.AppendResult{}, err
	}
	if strings.TrimSpace(request.CommandDigest) == "" {
		return originalaccessports.AppendResult{}, errors.New(
			"media original access append requires command digest",
		)
	}
	if replayed, found, err := s.findMediaOriginalAccessReceipt(ctx, request.Fact.IdempotencyKey, request.CommandDigest); err != nil || found {
		return replayed, err
	}
	session, err := s.facts.Database().Client().StartSession()
	if err != nil {
		return originalaccessports.AppendResult{}, err
	}
	defer session.EndSession(ctx)
	result := originalaccessports.AppendResult{Fact: request.Fact}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replayed, found, findErr := s.findMediaOriginalAccessReceipt(txCtx, request.Fact.IdempotencyKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			result = replayed
			return nil, nil
		}
		factDocument := mediaOriginalAccessFactDocumentFrom(request.Fact)
		if _, insertErr := s.facts.InsertOne(txCtx, factDocument); insertErr != nil {
			return nil, insertErr
		}
		_, insertErr := s.receipts.InsertOne(txCtx, mediaOriginalAccessReceiptDocument{
			ID: request.Fact.IdempotencyKey, CommandDigest: request.CommandDigest, Fact: factDocument,
		})
		return nil, insertErr
	})
	if err != nil {
		if replayed, found, replayErr := s.findMediaOriginalAccessReceipt(ctx, request.Fact.IdempotencyKey, request.CommandDigest); replayErr == nil && found {
			return replayed, nil
		}
		return originalaccessports.AppendResult{}, err
	}
	return result, nil
}

// FindFact reads one immutable audit fact by its audit identity. It never
// widens the lookup beyond the primary key; ownership checks belong to the
// consuming query facade.
func (s *MongoStore) FindFact(
	ctx context.Context,
	auditID string,
) (originalaccessmodel.Fact, bool, error) {
	auditID = strings.TrimSpace(auditID)
	if auditID == "" {
		return originalaccessmodel.Fact{}, false, nil
	}
	var document mediaOriginalAccessFactDocument
	err := s.facts.FindOne(ctx, bson.D{{Key: "_id", Value: auditID}}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return originalaccessmodel.Fact{}, false, nil
	}
	if err != nil {
		return originalaccessmodel.Fact{}, false, err
	}
	return mediaOriginalAccessFactFromDocument(document), true, nil
}

func (s *MongoStore) findMediaOriginalAccessReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandDigest string,
) (originalaccessports.AppendResult, bool, error) {
	var receipt mediaOriginalAccessReceiptDocument
	err := s.receipts.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return originalaccessports.AppendResult{}, false, nil
	}
	if err != nil {
		return originalaccessports.AppendResult{}, false, err
	}
	if receipt.CommandDigest != commandDigest {
		return originalaccessports.AppendResult{}, false, contentgenerated.AppErrorFromIdempotencyConflict("media original access idempotency key reused with another command")
	}
	return originalaccessports.AppendResult{
		Fact: mediaOriginalAccessFactFromDocument(receipt.Fact), Replayed: true,
	}, true, nil
}

func mediaOriginalAccessFactDocumentFrom(fact originalaccessmodel.Fact) mediaOriginalAccessFactDocument {
	var expiresAt *time.Time
	if !fact.ExpiresAt.IsZero() {
		value := fact.ExpiresAt.UTC()
		expiresAt = &value
	}
	return mediaOriginalAccessFactDocument{
		AuditID: fact.AuditID, AssetID: fact.AssetID, ViewerID: fact.ViewerID,
		Purpose: fact.Purpose, Outcome: fact.Outcome, Reason: fact.Reason,
		IdempotencyKey: fact.IdempotencyKey,
		GrantedAt:      fact.GrantedAt.UTC(), ExpiresAt: expiresAt,
	}
}

func mediaOriginalAccessFactFromDocument(document mediaOriginalAccessFactDocument) originalaccessmodel.Fact {
	var expiresAt time.Time
	if document.ExpiresAt != nil {
		expiresAt = document.ExpiresAt.UTC()
	}
	return originalaccessmodel.Fact{
		AuditID: document.AuditID, AssetID: document.AssetID, ViewerID: document.ViewerID,
		Purpose: document.Purpose, Outcome: document.Outcome, Reason: document.Reason,
		IdempotencyKey: document.IdempotencyKey,
		GrantedAt:      document.GrantedAt.UTC(), ExpiresAt: expiresAt,
	}
}
