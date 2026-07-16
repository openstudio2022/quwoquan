package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type mediaOriginalAccessFactDocument struct {
	AuditID        string    `bson:"_id"`
	AssetID        string    `bson:"assetId"`
	ViewerID       string    `bson:"viewerId"`
	Purpose        string    `bson:"purpose"`
	IdempotencyKey string    `bson:"idempotencyKey"`
	GrantedAt      time.Time `bson:"grantedAt"`
	ExpiresAt      time.Time `bson:"expiresAt"`
}

type mediaOriginalAccessReceiptDocument struct {
	ID            string                          `bson:"_id"`
	CommandDigest string                          `bson:"commandDigest"`
	Fact          mediaOriginalAccessFactDocument `bson:"fact"`
}

type mediaOriginalAccessOutboxDocument struct {
	EventID    string    `bson:"_id"`
	EventType  string    `bson:"eventType"`
	Payload    []byte    `bson:"payload"`
	OccurredAt time.Time `bson:"occurredAt"`
}

func (s *MongoMediaStore) AppendMediaOriginalAccess(
	ctx context.Context,
	request mediaports.MediaOriginalAccessAppendRequest,
) (mediaports.MediaOriginalAccessAppendResult, error) {
	if err := request.Fact.Validate(); err != nil {
		return mediaports.MediaOriginalAccessAppendResult{}, err
	}
	if strings.TrimSpace(request.CommandDigest) == "" ||
		request.Event.EventID != request.Fact.AuditID ||
		strings.TrimSpace(request.Event.EventType) == "" ||
		request.Event.OccurredAt.IsZero() {
		return mediaports.MediaOriginalAccessAppendResult{}, errors.New("media original access append requires matching command digest and event")
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
		factDocument := mediaOriginalAccessFactDocumentFrom(request.Fact)
		if _, insertErr := s.originalAccessFacts.InsertOne(txCtx, factDocument); insertErr != nil {
			return nil, insertErr
		}
		if _, insertErr := s.originalAccessOutbox.InsertOne(txCtx, mediaOriginalAccessOutboxDocument{
			EventID: request.Event.EventID, EventType: request.Event.EventType,
			Payload: append([]byte(nil), request.Event.Payload...), OccurredAt: request.Event.OccurredAt.UTC(),
		}); insertErr != nil {
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
	return mediaOriginalAccessFactDocument{
		AuditID: fact.AuditID, AssetID: fact.AssetID, ViewerID: fact.ViewerID,
		Purpose: fact.Purpose, IdempotencyKey: fact.IdempotencyKey,
		GrantedAt: fact.GrantedAt.UTC(), ExpiresAt: fact.ExpiresAt.UTC(),
	}
}

func mediaOriginalAccessFactFromDocument(document mediaOriginalAccessFactDocument) mediamodel.MediaOriginalAccessFact {
	return mediamodel.MediaOriginalAccessFact{
		AuditID: document.AuditID, AssetID: document.AssetID, ViewerID: document.ViewerID,
		Purpose: document.Purpose, IdempotencyKey: document.IdempotencyKey,
		GrantedAt: document.GrantedAt.UTC(), ExpiresAt: document.ExpiresAt.UTC(),
	}
}
