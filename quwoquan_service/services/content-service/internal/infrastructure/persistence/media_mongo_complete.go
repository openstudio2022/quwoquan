package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func (s *MongoMediaStore) FindCompleteUploadReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (mediaports.CompleteUploadResult, bool, error) {
	var receipt mediaUploadSessionReceiptDocument
	err := s.sessionReceipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaports.CompleteUploadResult{}, false, nil
	}
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, fmt.Errorf(
			"find complete media upload receipt: %w",
			err,
		)
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		return mediaports.CompleteUploadResult{}, false, nil
	}
	if err := validateMediaReceiptCommand(
		receipt.CommandName,
		receipt.CommandDigest,
		commandName,
		commandDigest,
	); err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	if receipt.Asset == nil {
		return mediaports.CompleteUploadResult{}, false,
			contentgenerated.AppErrorFromIdempotencyConflict(
				"idempotency key belongs to non-complete media command",
			)
	}
	session, err := mediaUploadSessionFromDocument(receipt.Result)
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	asset, err := mediaAssetFromDocument(*receipt.Asset)
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	return mediaports.CompleteUploadResult{
		Session:  session,
		Asset:    asset,
		Replayed: true,
	}, true, nil
}

func (s *MongoMediaStore) CompleteUpload(
	ctx context.Context,
	commit mediaports.CompleteUploadCommit,
) (mediaports.CompleteUploadResult, error) {
	if err := validateCompleteUploadCommit(commit); err != nil {
		return mediaports.CompleteUploadResult{}, err
	}
	session, err := s.uploadSessions.Database().Client().StartSession()
	if err != nil {
		return mediaports.CompleteUploadResult{}, fmt.Errorf(
			"start complete media upload transaction: %w",
			err,
		)
	}
	defer session.EndSession(ctx)

	var result mediaports.CompleteUploadResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replayed, found, err := s.findCompleteUploadReceiptTx(
			txCtx,
			commit.IdempotencyKey,
			commit.CommandName,
			commit.CommandDigest,
		)
		if err != nil {
			return nil, err
		}
		if found {
			result = replayed
			return nil, nil
		}
		if err := s.ensureNoLiveAssetReceipt(txCtx, commit.IdempotencyKey); err != nil {
			return nil, err
		}

		nextSession := mediaUploadSessionDocumentFromModel(commit.Session)
		if err := s.writeUploadSessionVersion(
			txCtx,
			nextSession,
			commit.ExpectedVersion,
		); err != nil {
			return nil, err
		}
		nextAsset := mediaAssetDocumentFromModel(commit.Asset)
		if _, err := s.assets.InsertOne(txCtx, nextAsset); err != nil {
			return nil, err
		}
		if err := s.writeMediaOutbox(txCtx, commit.Events); err != nil {
			return nil, err
		}
		expiresAt := normalizedMediaReceiptExpiry(commit.ReceiptExpiresAt)
		if _, err := s.sessionReceipts.InsertOne(txCtx, mediaUploadSessionReceiptDocument{
			ID:               commit.IdempotencyKey,
			AggregateID:      nextSession.ID,
			AggregateVersion: nextSession.Version,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			Result:           nextSession,
			Asset:            &nextAsset,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        expiresAt,
		}); err != nil {
			return nil, err
		}
		if _, err := s.assetReceipts.InsertOne(txCtx, mediaAssetReceiptDocument{
			ID:               commit.IdempotencyKey,
			AggregateID:      nextAsset.ID,
			AggregateVersion: nextAsset.Version,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			Result:           nextAsset,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        expiresAt,
		}); err != nil {
			return nil, err
		}
		persistedSession, err := mediaUploadSessionFromDocument(nextSession)
		if err != nil {
			return nil, err
		}
		persistedAsset, err := mediaAssetFromDocument(nextAsset)
		if err != nil {
			return nil, err
		}
		result = mediaports.CompleteUploadResult{
			Session: persistedSession,
			Asset:   persistedAsset,
		}
		return nil, nil
	})
	if err != nil {
		return mediaports.CompleteUploadResult{}, err
	}
	return result, nil
}

func (s *MongoMediaStore) findCompleteUploadReceiptTx(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (mediaports.CompleteUploadResult, bool, error) {
	var receipt mediaUploadSessionReceiptDocument
	err := s.sessionReceipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaports.CompleteUploadResult{}, false, nil
	}
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.sessionReceipts.DeleteOne(
			ctx,
			bson.D{{Key: "_id", Value: receipt.ID}},
		); err != nil {
			return mediaports.CompleteUploadResult{}, false, err
		}
		return mediaports.CompleteUploadResult{}, false, nil
	}
	if err := validateMediaReceiptCommand(
		receipt.CommandName,
		receipt.CommandDigest,
		commandName,
		commandDigest,
	); err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	if receipt.Asset == nil {
		return mediaports.CompleteUploadResult{}, false,
			contentgenerated.AppErrorFromIdempotencyConflict(
				"idempotency key belongs to non-complete media command",
			)
	}
	session, err := mediaUploadSessionFromDocument(receipt.Result)
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	asset, err := mediaAssetFromDocument(*receipt.Asset)
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	return mediaports.CompleteUploadResult{
		Session:  session,
		Asset:    asset,
		Replayed: true,
	}, true, nil
}

func (s *MongoMediaStore) ensureNoLiveAssetReceipt(
	ctx context.Context,
	idempotencyKey string,
) error {
	var receipt mediaAssetReceiptDocument
	err := s.assetReceipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil
	}
	if err != nil {
		return err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		_, err := s.assetReceipts.DeleteOne(
			ctx,
			bson.D{{Key: "_id", Value: receipt.ID}},
		)
		return err
	}
	return contentgenerated.AppErrorFromIdempotencyConflict(
		"idempotency key already belongs to a media asset command",
	)
}

func validateCompleteUploadCommit(commit mediaports.CompleteUploadCommit) error {
	if commit.Session == nil ||
		commit.Asset == nil ||
		strings.TrimSpace(commit.Session.ID()) == "" ||
		strings.TrimSpace(commit.Asset.ID()) == "" ||
		commit.ExpectedVersion < 1 ||
		commit.Session.Version() != commit.ExpectedVersion+1 ||
		commit.Asset.Version() != 1 ||
		commit.Asset.SourceSessionID() != commit.Session.ID() ||
		commit.Asset.OwnerID() != commit.Session.OwnerID() ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" ||
		len(commit.Events) != 2 {
		return contentgenerated.AppErrorFromVersionConflict(
			"invalid complete media upload commit",
		)
	}
	hasSessionEvent := false
	hasAssetEvent := false
	for _, event := range commit.Events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.EventType) == "" ||
			event.OccurredAt.IsZero() {
			return contentgenerated.AppErrorFromVersionConflict(
				"complete media upload outbox event is invalid",
			)
		}
		switch event.AggregateType {
		case "MediaUploadSession":
			hasSessionEvent = event.AggregateID == commit.Session.ID() &&
				event.AggregateVersion == commit.Session.Version()
		case "MediaAsset":
			hasAssetEvent = event.AggregateID == commit.Asset.ID() &&
				event.AggregateVersion == commit.Asset.Version()
		}
	}
	if !hasSessionEvent || !hasAssetEvent {
		return contentgenerated.AppErrorFromVersionConflict(
			"complete media upload outbox does not match aggregate commits",
		)
	}
	return nil
}
