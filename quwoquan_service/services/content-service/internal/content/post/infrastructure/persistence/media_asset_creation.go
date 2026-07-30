package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	assetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

// AppendCreated implements the MediaAsset-owned append port inside the Mongo
// transaction opened by MediaUploadSession completion.
func (s *MongoMediaStore) AppendCreated(
	ctx context.Context,
	commit assetports.CreateCommit,
) error {
	if err := validateMediaAssetCreationCommit(commit); err != nil {
		return err
	}
	if err := s.ensureNoLiveAssetReceipt(ctx, commit.IdempotencyKey); err != nil {
		return err
	}
	if s.objectFences == nil {
		return errors.New("media object deletion fence is not configured")
	}
	if err := s.objectFences.AllowReference(ctx, commit.Asset.ObjectKey); err != nil {
		return fmt.Errorf("authorize media object reference: %w", err)
	}
	document := mediaAssetDocument{
		ID:               commit.Asset.ID,
		Version:          commit.Asset.Version,
		OwnerID:          commit.Asset.OwnerID,
		SourceSessionID:  commit.Asset.SourceSessionID,
		ObjectKey:        commit.Asset.ObjectKey,
		SHA256:           commit.Asset.SHA256,
		MediaType:        commit.Asset.MediaType,
		MimeType:         commit.Asset.MimeType,
		FileSize:         commit.Asset.FileSize,
		AccessPolicy:     mediamodel.AccessPolicy(commit.Asset.AccessPolicy),
		ProcessingStatus: mediamodel.ProcessingStatus(commit.Asset.ProcessingStatus),
		CoverStrategy:    commit.Asset.CoverStrategy,
		CreatedAt:        commit.Asset.CreatedAt.UTC(),
		UpdatedAt:        commit.Asset.UpdatedAt.UTC(),
	}
	if _, err := s.assets.InsertOne(ctx, document); err != nil {
		return err
	}
	if _, err := s.assetOutbox.InsertOne(ctx, mediaOutboxDocument{
		ID:               commit.Event.ID,
		EventType:        commit.Event.Type,
		AggregateType:    "MediaAsset",
		AggregateID:      commit.Event.AggregateID,
		AggregateVersion: commit.Event.AggregateVersion,
		Payload:          append([]byte(nil), commit.Event.Payload...),
		OccurredAt:       commit.Event.OccurredAt.UTC(),
	}); err != nil {
		return err
	}
	_, err := s.assetReceipts.InsertOne(ctx, mediaAssetReceiptDocument{
		ID:               commit.IdempotencyKey,
		AggregateID:      document.ID,
		AggregateVersion: document.Version,
		CommandName:      commit.CommandName,
		CommandDigest:    commit.CommandDigest,
		Result:           document,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        normalizedMediaReceiptExpiry(commit.ReceiptExpiresAt),
	})
	return err
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

func validateMediaAssetCreationCommit(commit assetports.CreateCommit) error {
	asset := commit.Asset
	event := commit.Event
	if strings.TrimSpace(asset.ID) == "" ||
		asset.Version != 1 ||
		strings.TrimSpace(asset.OwnerID) == "" ||
		strings.TrimSpace(asset.SourceSessionID) == "" ||
		strings.TrimSpace(asset.ObjectKey) == "" ||
		strings.TrimSpace(asset.SHA256) == "" ||
		strings.TrimSpace(asset.MediaType) == "" ||
		strings.TrimSpace(asset.MimeType) == "" ||
		asset.FileSize <= 0 ||
		strings.TrimSpace(asset.AccessPolicy) == "" ||
		strings.TrimSpace(asset.ProcessingStatus) == "" ||
		strings.TrimSpace(asset.CoverStrategy) == "" ||
		asset.CreatedAt.IsZero() ||
		asset.UpdatedAt.IsZero() ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" ||
		event.Type != "content.media_asset.created" ||
		event.AggregateID != asset.ID ||
		event.AggregateVersion != asset.Version ||
		strings.TrimSpace(event.ID) == "" ||
		event.OccurredAt.IsZero() {
		return contentgenerated.AppErrorFromVersionConflict(
			"invalid media asset creation commit",
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

var _ assetports.CreationAppender = (*MongoMediaStore)(nil)
