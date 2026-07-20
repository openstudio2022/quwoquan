package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type mediaUploadSessionDocument struct {
	ID             string                         `bson:"_id"`
	Version        int64                          `bson:"version"`
	OwnerID        string                         `bson:"ownerId"`
	ObjectKey      string                         `bson:"objectKey"`
	MediaType      string                         `bson:"mediaType"`
	ContentType    string                         `bson:"contentType"`
	FileSize       int64                          `bson:"fileSize"`
	ExpectedSHA256 string                         `bson:"expectedSha256"`
	AssetID        string                         `bson:"assetId,omitempty"`
	Status         mediamodel.UploadSessionStatus `bson:"status"`
	CreatedAt      time.Time                      `bson:"createdAt"`
	UpdatedAt      time.Time                      `bson:"updatedAt"`
	ExpiresAt      time.Time                      `bson:"expiresAt"`
	CompletedAt    *time.Time                     `bson:"completedAt,omitempty"`
	AbortedAt      *time.Time                     `bson:"abortedAt,omitempty"`
}

type mediaUploadSessionReceiptDocument struct {
	ID               string                     `bson:"_id"`
	AggregateID      string                     `bson:"aggregateId"`
	AggregateVersion int64                      `bson:"aggregateVersion"`
	CommandName      string                     `bson:"commandName"`
	CommandDigest    string                     `bson:"commandDigest"`
	Result           mediaUploadSessionDocument `bson:"result"`
	Asset            *mediaAssetDocument        `bson:"asset,omitempty"`
	CreatedAt        time.Time                  `bson:"createdAt"`
	ExpiresAt        time.Time                  `bson:"expiresAt"`
}

func (s *MongoMediaStore) LoadUploadSession(
	ctx context.Context,
	sessionID string,
) (*mediamodel.MediaUploadSession, bool, error) {
	var document mediaUploadSessionDocument
	err := s.uploadSessions.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(sessionID)}},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load media upload session: %w", err)
	}
	session, err := mediaUploadSessionFromDocument(document)
	if err != nil {
		return nil, false, err
	}
	return session, true, nil
}

func (s *MongoMediaStore) FindUploadSessionForOwner(
	ctx context.Context,
	sessionID string,
	ownerID string,
) (mediaapp.MediaUploadSessionSlice, bool, error) {
	var document mediaUploadSessionDocument
	err := s.uploadSessions.FindOne(
		ctx,
		bson.D{
			{Key: "_id", Value: strings.TrimSpace(sessionID)},
			{Key: "ownerId", Value: strings.TrimSpace(ownerID)},
		},
		options.FindOne().SetProjection(bson.D{
			{Key: "_id", Value: 1},
			{Key: "version", Value: 1},
			{Key: "assetId", Value: 1},
			{Key: "objectKey", Value: 1},
			{Key: "mediaType", Value: 1},
			{Key: "contentType", Value: 1},
			{Key: "fileSize", Value: 1},
			{Key: "status", Value: 1},
			{Key: "createdAt", Value: 1},
			{Key: "updatedAt", Value: 1},
			{Key: "expiresAt", Value: 1},
		}),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaapp.MediaUploadSessionSlice{}, false, nil
	}
	if err != nil {
		return mediaapp.MediaUploadSessionSlice{}, false, fmt.Errorf(
			"find media upload session owner projection: %w",
			err,
		)
	}
	return mediaapp.MediaUploadSessionSlice{
		SessionID:   document.ID,
		Version:     document.Version,
		AssetID:     document.AssetID,
		ObjectKey:   document.ObjectKey,
		MediaType:   document.MediaType,
		ContentType: document.ContentType,
		FileSize:    document.FileSize,
		Status:      document.Status,
		CreatedAt:   document.CreatedAt,
		UpdatedAt:   document.UpdatedAt,
		ExpiresAt:   document.ExpiresAt,
	}, true, nil
}

func (s *MongoMediaStore) FindUploadSessionReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (mediaports.UploadSessionCommitResult, bool, error) {
	var receipt mediaUploadSessionReceiptDocument
	err := s.sessionReceipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaports.UploadSessionCommitResult{}, false, nil
	}
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, false, fmt.Errorf(
			"find media upload receipt: %w",
			err,
		)
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		return mediaports.UploadSessionCommitResult{}, false, nil
	}
	if err := validateMediaReceiptCommand(
		receipt.CommandName,
		receipt.CommandDigest,
		commandName,
		commandDigest,
	); err != nil {
		return mediaports.UploadSessionCommitResult{}, false, err
	}
	session, err := mediaUploadSessionFromDocument(receipt.Result)
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, false, err
	}
	return mediaports.UploadSessionCommitResult{
		Aggregate: session,
		Replayed:  true,
	}, true, nil
}

func (s *MongoMediaStore) CommitUploadSession(
	ctx context.Context,
	commit mediaports.UploadSessionCommit,
) (mediaports.UploadSessionCommitResult, error) {
	if err := validateUploadSessionCommit(commit); err != nil {
		return mediaports.UploadSessionCommitResult{}, err
	}
	session, err := s.uploadSessions.Database().Client().StartSession()
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, fmt.Errorf(
			"start media upload session transaction: %w",
			err,
		)
	}
	defer session.EndSession(ctx)

	var result mediaports.UploadSessionCommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replayed, found, err := s.findUploadSessionReceiptTx(
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
		next := mediaUploadSessionDocumentFromModel(commit.Aggregate)
		if err := s.writeUploadSessionVersion(txCtx, next, commit.ExpectedVersion); err != nil {
			return nil, err
		}
		if err := s.writeMediaOutbox(txCtx, commit.Events); err != nil {
			return nil, err
		}
		if _, err := s.sessionReceipts.InsertOne(txCtx, mediaUploadSessionReceiptDocument{
			ID:               commit.IdempotencyKey,
			AggregateID:      next.ID,
			AggregateVersion: next.Version,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			Result:           next,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        normalizedMediaReceiptExpiry(commit.ReceiptExpiresAt),
		}); err != nil {
			return nil, err
		}
		persisted, err := mediaUploadSessionFromDocument(next)
		if err != nil {
			return nil, err
		}
		result = mediaports.UploadSessionCommitResult{Aggregate: persisted}
		return nil, nil
	})
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, err
	}
	return result, nil
}

func (s *MongoMediaStore) findUploadSessionReceiptTx(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (mediaports.UploadSessionCommitResult, bool, error) {
	var receipt mediaUploadSessionReceiptDocument
	err := s.sessionReceipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaports.UploadSessionCommitResult{}, false, nil
	}
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, false, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.sessionReceipts.DeleteOne(
			ctx,
			bson.D{{Key: "_id", Value: receipt.ID}},
		); err != nil {
			return mediaports.UploadSessionCommitResult{}, false, err
		}
		return mediaports.UploadSessionCommitResult{}, false, nil
	}
	if err := validateMediaReceiptCommand(
		receipt.CommandName,
		receipt.CommandDigest,
		commandName,
		commandDigest,
	); err != nil {
		return mediaports.UploadSessionCommitResult{}, false, err
	}
	session, err := mediaUploadSessionFromDocument(receipt.Result)
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, false, err
	}
	return mediaports.UploadSessionCommitResult{
		Aggregate: session,
		Replayed:  true,
	}, true, nil
}

func (s *MongoMediaStore) writeUploadSessionVersion(
	ctx context.Context,
	next mediaUploadSessionDocument,
	expectedVersion int64,
) error {
	if expectedVersion == 0 {
		if _, err := s.uploadSessions.InsertOne(ctx, next); err != nil {
			return err
		}
		return nil
	}
	result, err := s.uploadSessions.ReplaceOne(
		ctx,
		bson.D{
			{Key: "_id", Value: next.ID},
			{Key: "version", Value: expectedVersion},
		},
		next,
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"media upload session version changed before commit",
		)
	}
	return nil
}

func validateUploadSessionCommit(commit mediaports.UploadSessionCommit) error {
	if commit.Aggregate == nil ||
		strings.TrimSpace(commit.Aggregate.ID()) == "" ||
		commit.ExpectedVersion < 0 ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" ||
		len(commit.Events) != 1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"invalid media upload session commit",
		)
	}
	event := commit.Events[0]
	if event.AggregateType != "MediaUploadSession" ||
		event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() ||
		strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.EventType) == "" ||
		event.OccurredAt.IsZero() {
		return contentgenerated.AppErrorFromVersionConflict(
			"media upload session outbox does not match aggregate commit",
		)
	}
	return nil
}

func validateMediaReceiptCommand(
	actualName string,
	actualDigest string,
	expectedName string,
	expectedDigest string,
) error {
	if actualName != expectedName || actualDigest != expectedDigest {
		return contentgenerated.AppErrorFromIdempotencyConflict(
			"idempotency key was reused with a different media command",
		)
	}
	return nil
}

func normalizedMediaReceiptExpiry(value time.Time) time.Time {
	if value.IsZero() {
		return time.Now().UTC().Add(24 * time.Hour)
	}
	return value.UTC()
}

func mediaUploadSessionDocumentFromModel(
	session *mediamodel.MediaUploadSession,
) mediaUploadSessionDocument {
	snapshot := session.Snapshot()
	return mediaUploadSessionDocument{
		ID:             snapshot.ID,
		Version:        snapshot.Version,
		OwnerID:        snapshot.OwnerID,
		ObjectKey:      snapshot.ObjectKey,
		MediaType:      snapshot.MediaType,
		ContentType:    snapshot.ContentType,
		FileSize:       snapshot.FileSize,
		ExpectedSHA256: snapshot.ExpectedSHA256,
		AssetID:        snapshot.AssetID,
		Status:         snapshot.Status,
		CreatedAt:      snapshot.CreatedAt,
		UpdatedAt:      snapshot.UpdatedAt,
		ExpiresAt:      snapshot.ExpiresAt,
		CompletedAt:    cloneMediaTime(snapshot.CompletedAt),
		AbortedAt:      cloneMediaTime(snapshot.AbortedAt),
	}
}

func mediaUploadSessionFromDocument(
	document mediaUploadSessionDocument,
) (*mediamodel.MediaUploadSession, error) {
	session, err := mediamodel.RestoreUploadSession(mediamodel.UploadSessionSnapshot{
		ID:             document.ID,
		Version:        document.Version,
		OwnerID:        document.OwnerID,
		ObjectKey:      document.ObjectKey,
		MediaType:      document.MediaType,
		ContentType:    document.ContentType,
		FileSize:       document.FileSize,
		ExpectedSHA256: document.ExpectedSHA256,
		AssetID:        document.AssetID,
		Status:         document.Status,
		CreatedAt:      document.CreatedAt,
		UpdatedAt:      document.UpdatedAt,
		ExpiresAt:      document.ExpiresAt,
		CompletedAt:    cloneMediaTime(document.CompletedAt),
		AbortedAt:      cloneMediaTime(document.AbortedAt),
	})
	if err != nil {
		return nil, fmt.Errorf("restore media upload session: %w", err)
	}
	return session, nil
}
