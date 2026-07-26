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

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediaerrors "quwoquan_service/services/content-service/generated/media/media_asset"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/content/post/domain/media/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/mediareferencefence"
)

type mediaAssetDocument struct {
	ID                            string                               `bson:"_id"`
	Version                       int64                                `bson:"version"`
	OwnerID                       string                               `bson:"ownerId"`
	SourceSessionID               string                               `bson:"sourceSessionId"`
	ObjectKey                     string                               `bson:"objectKey"`
	SHA256                        string                               `bson:"sha256"`
	MediaType                     string                               `bson:"mediaType"`
	ContentType                   string                               `bson:"contentType"`
	FileSize                      int64                                `bson:"fileSize"`
	AccessPolicy                  mediamodel.AccessPolicy              `bson:"accessPolicy"`
	ProcessingStatus              mediamodel.ProcessingStatus          `bson:"processingStatus"`
	ProcessingVersion             int64                                `bson:"processingVersion,omitempty"`
	ProcessingFailureReason       string                               `bson:"processingFailureReason,omitempty"`
	ProcessorProfile              string                               `bson:"processorProfile,omitempty"`
	ImageWidth                    int                                  `bson:"imageWidth,omitempty"`
	ImageHeight                   int                                  `bson:"imageHeight,omitempty"`
	ImageDeliveryContentType      string                               `bson:"imageDeliveryContentType,omitempty"`
	ImageNormalizedObjectKey      string                               `bson:"imageNormalizedObjectKey,omitempty"`
	ImagePublicSliceKey           string                               `bson:"imagePublicSliceKey,omitempty"`
	ImageDominantColor            string                               `bson:"imageDominantColor,omitempty"`
	ImageLQIP                     string                               `bson:"imageLqip,omitempty"`
	ImageContentProfile           string                               `bson:"imageContentProfile,omitempty"`
	ImageDerivativePolicyVersion  int                                  `bson:"imageDerivativePolicyVersion,omitempty"`
	ActiveImageDescriptorRevision int                                  `bson:"activeImageDescriptorRevision,omitempty"`
	ImageDescriptorRevisions      []mediamodel.ImageDescriptorRevision `bson:"imageDescriptorRevisions,omitempty"`
	VerifiedDurationMs            int64                                `bson:"verifiedDurationMs,omitempty"`
	VideoWidth                    int                                  `bson:"videoWidth,omitempty"`
	VideoHeight                   int                                  `bson:"videoHeight,omitempty"`
	VideoCodec                    string                               `bson:"videoCodec,omitempty"`
	VideoContainer                string                               `bson:"videoContainer,omitempty"`
	VideoAudioCodec               string                               `bson:"videoAudioCodec,omitempty"`
	VideoKeyframeIntervalMs       int                                  `bson:"videoKeyframeIntervalMs,omitempty"`
	VideoFastStart                bool                                 `bson:"videoFastStart,omitempty"`
	VideoPublicSliceKey           string                               `bson:"videoPublicSliceKey,omitempty"`
	CoverPublicSliceKey           string                               `bson:"coverPublicSliceKey,omitempty"`
	PreviewTrackVersion           int                                  `bson:"previewTrackVersion,omitempty"`
	PreviewTrackManifestSliceKey  string                               `bson:"previewTrackManifestSliceKey,omitempty"`
	CoverStrategy                 string                               `bson:"coverStrategy"`
	ManualCoverAssetID            string                               `bson:"manualCoverAssetId,omitempty"`
	CoverFrameTimeMs              int64                                `bson:"coverFrameTimeMs"`
	CreatedAt                     time.Time                            `bson:"createdAt"`
	UpdatedAt                     time.Time                            `bson:"updatedAt"`
	ProcessedAt                   *time.Time                           `bson:"processedAt,omitempty"`
	ArtifactsDeletedAt            *time.Time                           `bson:"artifactsDeletedAt,omitempty"`
}

type mediaAssetReceiptDocument struct {
	ID               string             `bson:"_id"`
	AggregateID      string             `bson:"aggregateId"`
	AggregateVersion int64              `bson:"aggregateVersion"`
	CommandName      string             `bson:"commandName"`
	CommandDigest    string             `bson:"commandDigest"`
	Result           mediaAssetDocument `bson:"result"`
	CreatedAt        time.Time          `bson:"createdAt"`
	ExpiresAt        time.Time          `bson:"expiresAt"`
}

func (s *MongoMediaStore) LoadMediaAsset(
	ctx context.Context,
	assetID string,
) (*mediamodel.MediaAsset, bool, error) {
	var document mediaAssetDocument
	err := s.assets.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(assetID)}},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load media asset: %w", err)
	}
	asset, err := mediaAssetFromDocument(document)
	if err != nil {
		return nil, false, err
	}
	return asset, true, nil
}

func (s *MongoMediaStore) FindMediaAssetForOwner(
	ctx context.Context,
	assetID string,
	ownerID string,
) (mediaapp.MediaAssetSlice, bool, error) {
	var document mediaAssetDocument
	err := s.assets.FindOne(
		ctx,
		bson.D{
			{Key: "_id", Value: strings.TrimSpace(assetID)},
			{Key: "ownerId", Value: strings.TrimSpace(ownerID)},
			{Key: "processingStatus", Value: bson.M{"$ne": "deleted"}},
		},
		options.FindOne().SetProjection(mediaAssetReadProjection()),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaapp.MediaAssetSlice{}, false, nil
	}
	if err != nil {
		return mediaapp.MediaAssetSlice{}, false, fmt.Errorf(
			"find media asset owner projection: %w",
			err,
		)
	}
	return mediaAssetSliceFromDocument(document), true, nil
}

func (s *MongoMediaStore) FindMediaAssetForOriginalAccess(
	ctx context.Context,
	assetID string,
) (mediaapp.MediaAssetSlice, bool, error) {
	var document mediaAssetDocument
	err := s.assets.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(assetID)}},
		options.FindOne().SetProjection(mediaAssetReadProjection()),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaapp.MediaAssetSlice{}, false, nil
	}
	if err != nil {
		return mediaapp.MediaAssetSlice{}, false, fmt.Errorf(
			"find media asset original access projection: %w",
			err,
		)
	}
	return mediaAssetSliceFromDocument(document), true, nil
}

func mediaAssetReadProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "version", Value: 1},
		{Key: "ownerId", Value: 1},
		{Key: "sourceSessionId", Value: 1},
		{Key: "objectKey", Value: 1},
		{Key: "sha256", Value: 1},
		{Key: "mediaType", Value: 1},
		{Key: "contentType", Value: 1},
		{Key: "fileSize", Value: 1},
		{Key: "accessPolicy", Value: 1},
		{Key: "processingStatus", Value: 1},
		{Key: "processorProfile", Value: 1},
		{Key: "imageWidth", Value: 1},
		{Key: "imageHeight", Value: 1},
		{Key: "imageDeliveryContentType", Value: 1},
		{Key: "imageNormalizedObjectKey", Value: 1},
		{Key: "imagePublicSliceKey", Value: 1},
		{Key: "imageDominantColor", Value: 1},
		{Key: "imageLqip", Value: 1},
		{Key: "imageContentProfile", Value: 1},
		{Key: "imageDerivativePolicyVersion", Value: 1},
		{Key: "verifiedDurationMs", Value: 1},
		{Key: "videoWidth", Value: 1},
		{Key: "videoHeight", Value: 1},
		{Key: "videoCodec", Value: 1},
		{Key: "videoContainer", Value: 1},
		{Key: "videoAudioCodec", Value: 1},
		{Key: "videoKeyframeIntervalMs", Value: 1},
		{Key: "videoFastStart", Value: 1},
		{Key: "videoPublicSliceKey", Value: 1},
		{Key: "coverPublicSliceKey", Value: 1},
		{Key: "previewTrackVersion", Value: 1},
		{Key: "previewTrackManifestSliceKey", Value: 1},
		{Key: "coverStrategy", Value: 1},
		{Key: "manualCoverAssetId", Value: 1},
		{Key: "coverFrameTimeMs", Value: 1},
		{Key: "createdAt", Value: 1},
		{Key: "updatedAt", Value: 1},
		{Key: "processedAt", Value: 1},
	}
}

func (s *MongoMediaStore) FindMediaAssetsByIDs(
	ctx context.Context,
	assetIDs []string,
) (map[string]mediaapp.MediaAssetSlice, error) {
	ids := make([]string, 0, len(assetIDs))
	seen := make(map[string]struct{}, len(assetIDs))
	for _, rawID := range assetIDs {
		assetID := strings.TrimSpace(rawID)
		if assetID == "" {
			continue
		}
		if _, exists := seen[assetID]; exists {
			continue
		}
		seen[assetID] = struct{}{}
		ids = append(ids, assetID)
	}
	if len(ids) == 0 {
		return map[string]mediaapp.MediaAssetSlice{}, nil
	}
	cursor, err := s.assets.Find(ctx, bson.D{{Key: "_id", Value: bson.D{{Key: "$in", Value: ids}}}})
	if err != nil {
		return nil, fmt.Errorf("find media assets by ids: %w", err)
	}
	defer cursor.Close(ctx)
	result := make(map[string]mediaapp.MediaAssetSlice, len(ids))
	for cursor.Next(ctx) {
		var document mediaAssetDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode media asset projection: %w", err)
		}
		result[document.ID] = mediaAssetSliceFromDocument(document)
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate media asset projections: %w", err)
	}
	return result, nil
}

func (s *MongoMediaStore) FindPublicMediaAsset(
	ctx context.Context,
	assetID string,
) (mediaapp.MediaAssetSlice, bool, error) {
	var document mediaAssetDocument
	err := s.assets.FindOne(ctx, bson.D{
		{Key: "_id", Value: strings.TrimSpace(assetID)},
		{Key: "accessPolicy", Value: mediamodel.AccessPolicyPublic},
		{Key: "processingStatus", Value: mediamodel.ProcessingStatusReady},
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaapp.MediaAssetSlice{}, false, nil
	}
	if err != nil {
		return mediaapp.MediaAssetSlice{}, false, fmt.Errorf("find public media asset: %w", err)
	}
	return mediaAssetSliceFromDocument(document), true, nil
}

func mediaAssetSliceFromDocument(document mediaAssetDocument) mediaapp.MediaAssetSlice {
	return mediaapp.MediaAssetSlice{
		AssetID:                      document.ID,
		Version:                      document.Version,
		OwnerID:                      document.OwnerID,
		SourceSessionID:              document.SourceSessionID,
		ObjectKey:                    document.ObjectKey,
		SHA256:                       document.SHA256,
		MediaType:                    document.MediaType,
		ContentType:                  document.ContentType,
		FileSize:                     document.FileSize,
		AccessPolicy:                 document.AccessPolicy,
		ProcessingStatus:             document.ProcessingStatus,
		ProcessorProfile:             document.ProcessorProfile,
		ImageWidth:                   document.ImageWidth,
		ImageHeight:                  document.ImageHeight,
		ImageDeliveryContentType:     document.ImageDeliveryContentType,
		ImageNormalizedObjectKey:     document.ImageNormalizedObjectKey,
		ImagePublicSliceKey:          document.ImagePublicSliceKey,
		ImageDominantColor:           document.ImageDominantColor,
		ImageLQIP:                    document.ImageLQIP,
		ImageContentProfile:          document.ImageContentProfile,
		ImageDerivativePolicyVersion: document.ImageDerivativePolicyVersion,
		VerifiedDurationMs:           document.VerifiedDurationMs,
		VideoWidth:                   document.VideoWidth,
		VideoHeight:                  document.VideoHeight,
		VideoCodec:                   document.VideoCodec,
		VideoContainer:               document.VideoContainer,
		VideoAudioCodec:              document.VideoAudioCodec,
		VideoKeyframeIntervalMs:      document.VideoKeyframeIntervalMs,
		VideoFastStart:               document.VideoFastStart,
		VideoPublicSliceKey:          document.VideoPublicSliceKey,
		CoverPublicSliceKey:          document.CoverPublicSliceKey,
		PreviewTrackVersion:          document.PreviewTrackVersion,
		PreviewTrackManifestSliceKey: document.PreviewTrackManifestSliceKey,
		CreatedAt:                    document.CreatedAt,
		UpdatedAt:                    document.UpdatedAt,
		ProcessedAt:                  cloneMediaTime(document.ProcessedAt),
		CoverStrategy:                document.CoverStrategy,
		ManualCoverAssetID:           document.ManualCoverAssetID,
		CoverFrameTimeMs:             document.CoverFrameTimeMs,
	}
}

func (s *MongoMediaStore) FindMediaAssetReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (mediaports.MediaAssetCommitResult, bool, error) {
	var receipt mediaAssetReceiptDocument
	err := s.assetReceipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaports.MediaAssetCommitResult{}, false, nil
	}
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, false, fmt.Errorf(
			"find media asset receipt: %w",
			err,
		)
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		return mediaports.MediaAssetCommitResult{}, false, nil
	}
	if err := validateMediaReceiptCommand(
		receipt.CommandName,
		receipt.CommandDigest,
		commandName,
		commandDigest,
	); err != nil {
		return mediaports.MediaAssetCommitResult{}, false, err
	}
	asset, err := mediaAssetFromDocument(receipt.Result)
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, false, err
	}
	return mediaports.MediaAssetCommitResult{
		Aggregate: asset,
		Replayed:  true,
	}, true, nil
}

// RecordMediaAssetNoopReceipt 持久化目标状态已满足的命名 set 回执：
// 不递增 aggregate version、不写 outbox；并发首插以先者为准并回放先者结果。
func (s *MongoMediaStore) RecordMediaAssetNoopReceipt(
	ctx context.Context,
	noop mediaports.MediaAssetNoopReceipt,
) (mediaports.MediaAssetCommitResult, error) {
	if noop.Aggregate == nil ||
		strings.TrimSpace(noop.IdempotencyKey) == "" ||
		strings.TrimSpace(noop.CommandName) == "" ||
		strings.TrimSpace(noop.CommandDigest) == "" {
		return mediaports.MediaAssetCommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"media asset no-op receipt is incomplete",
			)
	}
	if replayed, found, err := s.FindMediaAssetReceipt(
		ctx,
		noop.IdempotencyKey,
		noop.CommandName,
		noop.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	record := mediaAssetDocumentFromModel(noop.Aggregate)
	expiresAt := noop.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	_, err := s.assetReceipts.InsertOne(ctx, mediaAssetReceiptDocument{
		ID:               strings.TrimSpace(noop.IdempotencyKey),
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      strings.TrimSpace(noop.CommandName),
		CommandDigest:    strings.TrimSpace(noop.CommandDigest),
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        expiresAt,
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			replayed, found, replayErr := s.FindMediaAssetReceipt(
				ctx,
				noop.IdempotencyKey,
				noop.CommandName,
				noop.CommandDigest,
			)
			if replayErr != nil {
				return mediaports.MediaAssetCommitResult{}, replayErr
			}
			if found {
				return replayed, nil
			}
		}
		return mediaports.MediaAssetCommitResult{}, err
	}
	asset, err := mediaAssetFromDocument(record)
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, err
	}
	return mediaports.MediaAssetCommitResult{Aggregate: asset}, nil
}

func (s *MongoMediaStore) CommitMediaAsset(
	ctx context.Context,
	commit mediaports.MediaAssetCommit,
) (mediaports.MediaAssetCommitResult, error) {
	if err := validateMediaAssetCommit(commit); err != nil {
		return mediaports.MediaAssetCommitResult{}, err
	}
	session, err := s.assets.Database().Client().StartSession()
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, fmt.Errorf(
			"start media asset transaction: %w",
			err,
		)
	}
	defer session.EndSession(ctx)

	var result mediaports.MediaAssetCommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replayed, found, err := s.findMediaAssetReceiptTx(
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
		next := mediaAssetDocumentFromModel(commit.Aggregate)
		if commit.Discard {
			if s.referenceFences == nil {
				return nil, errors.New("media reference fence is not configured")
			}
			if err := s.referenceFences.ClaimDeletion(txCtx, next.ID); err != nil {
				if errors.Is(err, mediareferencefence.ErrDeletionInProgress) {
					return nil, mediaerrors.AppErrorFromMediaInUse(
						"media discard raced with another reference transition",
					)
				}
				return nil, err
			}
			if err := s.ensureMediaAssetDiscardable(txCtx, next.ID); err != nil {
				return nil, err
			}
		} else {
			if s.objectFences == nil {
				return nil, errors.New("media object deletion fence is not configured")
			}
			if err := s.objectFences.AllowReference(
				txCtx,
				next.ObjectKey,
			); err != nil {
				return nil, fmt.Errorf(
					"authorize media object reference: %w",
					err,
				)
			}
			if coverID := strings.TrimSpace(next.ManualCoverAssetID); coverID != "" {
				if s.referenceFences == nil {
					return nil, errors.New("media reference fence is not configured")
				}
				if err := s.referenceFences.AllowReferences(
					txCtx,
					[]mediareferencefence.Reference{{
						AssetID: coverID,
						OwnerID: next.OwnerID,
					}},
				); err != nil {
					return nil, mediaerrors.AppErrorFromMediaNotFound(
						"manual cover asset became unavailable before commit",
					)
				}
			}
		}
		if err := s.writeMediaAssetVersion(txCtx, next, commit.ExpectedVersion); err != nil {
			return nil, err
		}
		if err := s.writeMediaOutbox(txCtx, commit.Events); err != nil {
			return nil, err
		}
		if _, err := s.assetReceipts.InsertOne(txCtx, mediaAssetReceiptDocument{
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
		persisted, err := mediaAssetFromDocument(next)
		if err != nil {
			return nil, err
		}
		result = mediaports.MediaAssetCommitResult{Aggregate: persisted}
		return nil, nil
	})
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, err
	}
	return result, nil
}

func (s *MongoMediaStore) ensureMediaAssetDiscardable(
	ctx context.Context,
	assetID string,
) error {
	db := s.assets.Database()
	checks := []struct {
		collection *mongo.Collection
		filter     bson.M
	}{
		{
			collection: db.Collection("posts"),
			filter: bson.M{
				"status": bson.M{"$ne": "deleted"},
				"$or": bson.A{
					bson.M{"mediaAssetIds": assetID},
					bson.M{"illustrationAssetId": assetID},
				},
			},
		},
		{
			collection: db.Collection("comments"),
			filter: bson.M{
				"status":             bson.M{"$nin": bson.A{"deleted", "tombstoned"}},
				"attachmentMediaIds": assetID,
			},
		},
		{
			collection: s.assets,
			filter: bson.M{
				"_id":                bson.M{"$ne": assetID},
				"processingStatus":   bson.M{"$ne": "deleted"},
				"manualCoverAssetId": assetID,
			},
		},
	}
	for _, check := range checks {
		count, err := check.collection.CountDocuments(
			ctx,
			check.filter,
			options.Count().SetLimit(1),
		)
		if err != nil {
			return fmt.Errorf("check media asset references before discard: %w", err)
		}
		if count != 0 {
			return mediaerrors.AppErrorFromMediaInUse(
				"media asset has a live content reference",
			)
		}
	}
	return nil
}

func (s *MongoMediaStore) findMediaAssetReceiptTx(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (mediaports.MediaAssetCommitResult, bool, error) {
	var receipt mediaAssetReceiptDocument
	err := s.assetReceipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaports.MediaAssetCommitResult{}, false, nil
	}
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, false, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.assetReceipts.DeleteOne(
			ctx,
			bson.D{{Key: "_id", Value: receipt.ID}},
		); err != nil {
			return mediaports.MediaAssetCommitResult{}, false, err
		}
		return mediaports.MediaAssetCommitResult{}, false, nil
	}
	if err := validateMediaReceiptCommand(
		receipt.CommandName,
		receipt.CommandDigest,
		commandName,
		commandDigest,
	); err != nil {
		return mediaports.MediaAssetCommitResult{}, false, err
	}
	asset, err := mediaAssetFromDocument(receipt.Result)
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, false, err
	}
	return mediaports.MediaAssetCommitResult{
		Aggregate: asset,
		Replayed:  true,
	}, true, nil
}

func (s *MongoMediaStore) writeMediaAssetVersion(
	ctx context.Context,
	next mediaAssetDocument,
	expectedVersion int64,
) error {
	if expectedVersion == 0 {
		if _, err := s.assets.InsertOne(ctx, next); err != nil {
			return err
		}
		return nil
	}
	result, err := s.assets.ReplaceOne(
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
			"media asset version changed before commit",
		)
	}
	return nil
}

func validateMediaAssetCommit(commit mediaports.MediaAssetCommit) error {
	if commit.Aggregate == nil ||
		strings.TrimSpace(commit.Aggregate.ID()) == "" ||
		commit.ExpectedVersion < 0 ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" ||
		len(commit.Events) != 1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"invalid media asset commit",
		)
	}
	if commit.Discard !=
		(commit.Aggregate.ProcessingStatus() == mediamodel.ProcessingStatusDeleted) {
		return contentgenerated.AppErrorFromVersionConflict(
			"media asset discard marker does not match aggregate state",
		)
	}
	event := commit.Events[0]
	if event.AggregateType != "MediaAsset" ||
		event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() ||
		strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.EventType) == "" ||
		event.OccurredAt.IsZero() {
		return contentgenerated.AppErrorFromVersionConflict(
			"media asset outbox does not match aggregate commit",
		)
	}
	return nil
}

func mediaAssetDocumentFromModel(asset *mediamodel.MediaAsset) mediaAssetDocument {
	snapshot := asset.Snapshot()
	return mediaAssetDocument{
		ID:                            snapshot.ID,
		Version:                       snapshot.Version,
		OwnerID:                       snapshot.OwnerID,
		SourceSessionID:               snapshot.SourceSessionID,
		ObjectKey:                     snapshot.ObjectKey,
		SHA256:                        snapshot.SHA256,
		MediaType:                     snapshot.MediaType,
		ContentType:                   snapshot.ContentType,
		FileSize:                      snapshot.FileSize,
		AccessPolicy:                  snapshot.AccessPolicy,
		ProcessingStatus:              snapshot.ProcessingStatus,
		ProcessingVersion:             snapshot.ProcessingVersion,
		ProcessingFailureReason:       snapshot.ProcessingFailureReason,
		ProcessorProfile:              snapshot.ProcessorProfile,
		ImageWidth:                    snapshot.ImageWidth,
		ImageHeight:                   snapshot.ImageHeight,
		ImageDeliveryContentType:      snapshot.ImageDeliveryContentType,
		ImageNormalizedObjectKey:      snapshot.ImageNormalizedObjectKey,
		ImagePublicSliceKey:           snapshot.ImagePublicSliceKey,
		ImageDominantColor:            snapshot.ImageDominantColor,
		ImageLQIP:                     snapshot.ImageLQIP,
		ImageContentProfile:           snapshot.ImageContentProfile,
		ImageDerivativePolicyVersion:  snapshot.ImageDerivativePolicyVersion,
		ActiveImageDescriptorRevision: snapshot.ActiveImageDescriptorRevision,
		ImageDescriptorRevisions:      snapshot.ImageDescriptorRevisions,
		VerifiedDurationMs:            snapshot.VerifiedDurationMs,
		VideoWidth:                    snapshot.VideoWidth,
		VideoHeight:                   snapshot.VideoHeight,
		VideoCodec:                    snapshot.VideoCodec,
		VideoContainer:                snapshot.VideoContainer,
		VideoAudioCodec:               snapshot.VideoAudioCodec,
		VideoKeyframeIntervalMs:       snapshot.VideoKeyframeIntervalMs,
		VideoFastStart:                snapshot.VideoFastStart,
		VideoPublicSliceKey:           snapshot.VideoPublicSliceKey,
		CoverPublicSliceKey:           snapshot.CoverPublicSliceKey,
		PreviewTrackVersion:           snapshot.PreviewTrackVersion,
		PreviewTrackManifestSliceKey:  snapshot.PreviewTrackManifestSliceKey,
		CoverStrategy:                 snapshot.CoverStrategy,
		ManualCoverAssetID:            snapshot.ManualCoverAssetID,
		CoverFrameTimeMs:              snapshot.CoverFrameTimeMs,
		CreatedAt:                     snapshot.CreatedAt,
		UpdatedAt:                     snapshot.UpdatedAt,
		ProcessedAt:                   cloneMediaTime(snapshot.ProcessedAt),
	}
}

func mediaAssetFromDocument(
	document mediaAssetDocument,
) (*mediamodel.MediaAsset, error) {
	asset, err := mediamodel.RestoreMediaAsset(mediamodel.MediaAssetSnapshot{
		ID:                            document.ID,
		Version:                       document.Version,
		OwnerID:                       document.OwnerID,
		SourceSessionID:               document.SourceSessionID,
		ObjectKey:                     document.ObjectKey,
		SHA256:                        document.SHA256,
		MediaType:                     document.MediaType,
		ContentType:                   document.ContentType,
		FileSize:                      document.FileSize,
		AccessPolicy:                  document.AccessPolicy,
		ProcessingStatus:              document.ProcessingStatus,
		ProcessingVersion:             document.ProcessingVersion,
		ProcessingFailureReason:       document.ProcessingFailureReason,
		ProcessorProfile:              document.ProcessorProfile,
		ImageWidth:                    document.ImageWidth,
		ImageHeight:                   document.ImageHeight,
		ImageDeliveryContentType:      document.ImageDeliveryContentType,
		ImageNormalizedObjectKey:      document.ImageNormalizedObjectKey,
		ImagePublicSliceKey:           document.ImagePublicSliceKey,
		ImageDominantColor:            document.ImageDominantColor,
		ImageLQIP:                     document.ImageLQIP,
		ImageContentProfile:           document.ImageContentProfile,
		ImageDerivativePolicyVersion:  document.ImageDerivativePolicyVersion,
		ActiveImageDescriptorRevision: document.ActiveImageDescriptorRevision,
		ImageDescriptorRevisions:      document.ImageDescriptorRevisions,
		VerifiedDurationMs:            document.VerifiedDurationMs,
		VideoWidth:                    document.VideoWidth,
		VideoHeight:                   document.VideoHeight,
		VideoCodec:                    document.VideoCodec,
		VideoContainer:                document.VideoContainer,
		VideoAudioCodec:               document.VideoAudioCodec,
		VideoKeyframeIntervalMs:       document.VideoKeyframeIntervalMs,
		VideoFastStart:                document.VideoFastStart,
		VideoPublicSliceKey:           document.VideoPublicSliceKey,
		CoverPublicSliceKey:           document.CoverPublicSliceKey,
		PreviewTrackVersion:           document.PreviewTrackVersion,
		PreviewTrackManifestSliceKey:  document.PreviewTrackManifestSliceKey,
		CoverStrategy:                 document.CoverStrategy,
		ManualCoverAssetID:            document.ManualCoverAssetID,
		CoverFrameTimeMs:              document.CoverFrameTimeMs,
		CreatedAt:                     document.CreatedAt,
		UpdatedAt:                     document.UpdatedAt,
		ProcessedAt:                   cloneMediaTime(document.ProcessedAt),
	})
	if err != nil {
		return nil, fmt.Errorf("restore media asset: %w", err)
	}
	return asset, nil
}
