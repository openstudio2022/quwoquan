package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

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

func (s *MongoMediaStore) AppendMediaOriginalAccess(
	ctx context.Context,
	request mediaports.MediaOriginalAccessAppendRequest,
) (mediaports.MediaOriginalAccessAppendResult, error) {
	if err := request.Fact.Validate(); err != nil {
		return mediaports.MediaOriginalAccessAppendResult{}, err
	}
	if strings.TrimSpace(request.CommandDigest) == "" {
		return mediaports.MediaOriginalAccessAppendResult{}, errors.New(
			"media original access append requires command digest",
		)
	}
	if strings.EqualFold(request.Fact.Outcome, "granted") && !request.RateLimit.IsValid() {
		return mediaports.MediaOriginalAccessAppendResult{}, errors.New(
			"media original access append requires a valid rate limit policy",
		)
	}
	if replayed, found, err := s.findMediaOriginalAccessReceipt(ctx, request.Fact.IdempotencyKey, request.CommandDigest); err != nil || found {
		return replayed, err
	}
	session, err := s.originalAccessFacts.Database().Client().StartSession()
	if err != nil {
		return mediaports.MediaOriginalAccessAppendResult{}, err
	}
	defer session.EndSession(ctx)
	result := mediaports.MediaOriginalAccessAppendResult{Fact: request.Fact}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replayed, found, findErr := s.findMediaOriginalAccessReceipt(txCtx, request.Fact.IdempotencyKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			result = replayed
			return nil, nil
		}
		if strings.EqualFold(request.Fact.Outcome, "granted") {
			if rateLimitErr := s.reserveMediaOriginalAccessRateLimit(
				txCtx,
				request.Fact,
				request.RateLimit,
			); rateLimitErr != nil {
				return nil, rateLimitErr
			}
		}
		factDocument := mediaOriginalAccessFactDocumentFrom(request.Fact)
		if _, insertErr := s.originalAccessFacts.InsertOne(txCtx, factDocument); insertErr != nil {
			return nil, insertErr
		}
		_, insertErr := s.originalAccessReceipts.InsertOne(txCtx, mediaOriginalAccessReceiptDocument{
			ID: request.Fact.IdempotencyKey, CommandDigest: request.CommandDigest, Fact: factDocument,
		})
		return nil, insertErr
	})
	if err != nil {
		if replayed, found, replayErr := s.findMediaOriginalAccessReceipt(ctx, request.Fact.IdempotencyKey, request.CommandDigest); replayErr == nil && found {
			return replayed, nil
		}
		return mediaports.MediaOriginalAccessAppendResult{}, err
	}
	return result, nil
}

func (s *MongoMediaStore) reserveMediaOriginalAccessRateLimit(
	ctx context.Context,
	fact mediamodel.MediaOriginalAccessFact,
	limit mediaports.MediaOriginalAccessRateLimit,
) error {
	windowStart := fact.GrantedAt.UTC().Truncate(limit.Window)
	keyInput := strings.Join([]string{
		strings.TrimSpace(fact.ViewerID),
		strings.TrimSpace(fact.AssetID),
		strings.TrimSpace(fact.Purpose),
		windowStart.Format(time.RFC3339Nano),
	}, ":")
	digest := sha256.Sum256([]byte(keyInput))
	limitID := hex.EncodeToString(digest[:])
	_, err := s.originalAccessRateLimits.UpdateOne(
		ctx,
		bson.D{
			{Key: "_id", Value: limitID},
			{Key: "count", Value: bson.D{{Key: "$lt", Value: limit.MaxGrants}}},
		},
		bson.D{
			{Key: "$inc", Value: bson.D{{Key: "count", Value: 1}}},
			{Key: "$setOnInsert", Value: bson.D{
				{Key: "expiresAt", Value: windowStart.Add(limit.Window)},
			}},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if mongo.IsDuplicateKeyError(err) {
		return contentgenerated.AppErrorFromOriginalAccessRateLimited(
			"media original access rate limit exhausted",
		)
	}
	if err != nil {
		return err
	}
	return nil
}

func (s *MongoMediaStore) findMediaOriginalAccessReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandDigest string,
) (mediaports.MediaOriginalAccessAppendResult, bool, error) {
	var receipt mediaOriginalAccessReceiptDocument
	err := s.originalAccessReceipts.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaports.MediaOriginalAccessAppendResult{}, false, nil
	}
	if err != nil {
		return mediaports.MediaOriginalAccessAppendResult{}, false, err
	}
	if receipt.CommandDigest != commandDigest {
		return mediaports.MediaOriginalAccessAppendResult{}, false, contentgenerated.AppErrorFromIdempotencyConflict("media original access idempotency key reused with another command")
	}
	return mediaports.MediaOriginalAccessAppendResult{
		Fact: mediaOriginalAccessFactFromDocument(receipt.Fact), Replayed: true,
	}, true, nil
}

func mediaOriginalAccessFactDocumentFrom(fact mediamodel.MediaOriginalAccessFact) mediaOriginalAccessFactDocument {
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

func mediaOriginalAccessFactFromDocument(document mediaOriginalAccessFactDocument) mediamodel.MediaOriginalAccessFact {
	var expiresAt time.Time
	if document.ExpiresAt != nil {
		expiresAt = document.ExpiresAt.UTC()
	}
	return mediamodel.MediaOriginalAccessFact{
		AuditID: document.AuditID, AssetID: document.AssetID, ViewerID: document.ViewerID,
		Purpose: document.Purpose, Outcome: document.Outcome, Reason: document.Reason,
		IdempotencyKey: document.IdempotencyKey,
		GrantedAt:      document.GrantedAt.UTC(), ExpiresAt: expiresAt,
	}
}
