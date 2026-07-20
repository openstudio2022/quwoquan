package media

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runtimemedia "quwoquan_service/runtime/media"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

const mediaReceiptTTL = 24 * time.Hour

type MediaService struct {
	data    DataPorts
	objects MediaObjectGateway
	now     func() time.Time
	newID   func(string) (string, error)
}

type MediaServiceOption func(*MediaService)

func WithClock(now func() time.Time) MediaServiceOption {
	return func(service *MediaService) {
		if now != nil {
			service.now = now
		}
	}
}

func WithIdentifierGenerator(
	newID func(prefix string) (string, error),
) MediaServiceOption {
	return func(service *MediaService) {
		if newID != nil {
			service.newID = newID
		}
	}
}

func NewMediaService(data DataPorts, objects MediaObjectGateway, options ...MediaServiceOption) *MediaService {
	if data.UploadSessions == nil || data.Assets == nil || data.OriginalAccess == nil || objects == nil {
		panic("MediaService requires upload session, asset, original access data ports and media object gateway")
	}
	service := &MediaService{
		data:    data,
		objects: objects,
		now:     time.Now,
		newID:   newMediaIdentifier,
	}
	for _, option := range options {
		option(service)
	}
	return service
}

func (s *MediaService) InitMediaUpload(
	ctx context.Context,
	command InitMediaUploadCommand,
) (MediaUploadSessionCommandResult, error) {
	command = normalizeInitMediaUploadCommand(command)
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("InitMediaUpload", encoded)
	if replayed, found, err := s.replayUploadSession(
		ctx,
		"InitMediaUpload",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	if err := validateInitMediaUploadCommand(command); err != nil {
		return MediaUploadSessionCommandResult{}, err
	}

	now := s.now().UTC()
	sessionID, err := s.newID("mus")
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	grant, err := s.objects.PrepareUpload(ctx, PrepareUploadParams{
		SessionID: sessionID, OwnerID: command.OwnerID, MediaType: command.MediaType,
		ContentType: command.ContentType, FileSize: command.FileSize,
		ExpectedSHA256: command.ExpectedSHA256, ExpiresAt: now.Add(15 * time.Minute),
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	session, err := mediamodel.CreateUploadSession(mediamodel.CreateUploadSessionParams{
		ID:             sessionID,
		OwnerID:        command.OwnerID,
		ObjectKey:      grant.ObjectKey,
		MediaType:      command.MediaType,
		ContentType:    command.ContentType,
		FileSize:       command.FileSize,
		ExpectedSHA256: command.ExpectedSHA256,
		ExpiresAt:      grant.ExpiresAt,
		Now:            now,
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, mapMediaDomainError(err)
	}
	payload, err := json.Marshal(mediaUploadInitializedPayload{
		SessionID: session.ID(),
		OwnerID:   session.OwnerID(),
		ObjectKey: session.ObjectKey(),
		ExpiresAt: session.ExpiresAt(),
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	result, err := s.commitUploadSession(
		ctx,
		session,
		0,
		"InitMediaUpload",
		commandDigest,
		"content.media_upload.initialized",
		payload,
		now,
	)
	if err != nil {
		return MediaUploadSessionCommandResult{}, err
	}
	result.ObjectKey = grant.ObjectKey
	result.UploadURL = grant.UploadURL
	result.ExpiresAt = grant.ExpiresAt
	return result, nil
}

func (s *MediaService) CompleteMediaUpload(
	ctx context.Context,
	command CompleteMediaUploadCommand,
) (MediaUploadSessionCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("CompleteMediaUpload", encoded)
	if replayed, found, err := s.replayCompleteUpload(
		ctx,
		"CompleteMediaUpload",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}

	session, found, err := s.loadUploadSession(ctx, command.SessionID)
	if err != nil {
		return MediaUploadSessionCommandResult{}, err
	}
	if !found {
		return MediaUploadSessionCommandResult{}, mediaNotFound(command.SessionID)
	}
	if strings.TrimSpace(command.OwnerID) != session.OwnerID() {
		return MediaUploadSessionCommandResult{}, mapMediaDomainError(
			fmt.Errorf("%w: completion owner does not match", mediamodel.ErrUploadSessionOwnerForbidden),
		)
	}
	expectedVersion := session.Version()
	now := s.now().UTC()
	assetID, err := s.newID("mas")
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	if err := session.Complete(
		command.OwnerID,
		session.ExpectedSHA256(),
		assetID,
		now,
	); err != nil {
		return MediaUploadSessionCommandResult{}, mapMediaDomainError(err)
	}
	completedObject, err := s.objects.CompleteUpload(
		ctx,
		CompleteUploadParams{
			ObjectKey:      session.ObjectKey(),
			ExpectedSHA256: session.ExpectedSHA256(),
			MediaType:      session.MediaType(),
			ContentType:    session.ContentType(),
			FileSize:       session.FileSize(),
		},
	)
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID:              assetID,
		OwnerID:         session.OwnerID(),
		SourceSessionID: session.ID(),
		ObjectKey:       completedObject.ObjectKey,
		SHA256:          completedObject.SHA256,
		MediaType:       session.MediaType(),
		ContentType:     session.ContentType(),
		FileSize:        session.FileSize(),
		AccessPolicy:    command.AccessPolicy,
		// 图片和视频都必须经过受信处理器验证与归一化；音频/文件没有对应
		// consumer，保持直接 ready，避免制造永远悬挂的 processing 资产。
		ProcessingRequired: session.MediaType() == "image" || session.MediaType() == "video",
		Now:                now,
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, mapMediaDomainError(err)
	}
	sessionPayload, err := json.Marshal(mediaUploadCompletedPayload{
		SessionID: session.ID(),
		OwnerID:   session.OwnerID(),
		ObjectKey: session.ObjectKey(),
		AssetID:   asset.ID(),
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	assetPayload, err := json.Marshal(mediaAssetCreatedPayload{
		AssetID:         asset.ID(),
		OwnerID:         asset.OwnerID(),
		SourceSessionID: asset.SourceSessionID(),
		ObjectKey:       asset.ObjectKey(),
		SHA256:          asset.SHA256(),
		ContentType:     asset.ContentType(),
		FileSize:        asset.FileSize(),
		Processing:      asset.ProcessingStatus(),
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	eventID, err := s.newID("evt")
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	assetEventID, err := s.newID("evt")
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaUploadSessionCommandResult{}, err
	}
	result, err := s.data.UploadSessions.CompleteUpload(ctx, mediaports.CompleteUploadCommit{
		Session:          session,
		ExpectedVersion:  expectedVersion,
		Asset:            asset,
		IdempotencyKey:   idempotencyKey,
		CommandName:      "CompleteMediaUpload",
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.Add(mediaReceiptTTL),
		Events: []mediaports.OutboxEvent{
			{
				EventID:          eventID,
				EventType:        "content.media_upload.completed",
				AggregateType:    "MediaUploadSession",
				AggregateID:      session.ID(),
				AggregateVersion: session.Version(),
				Payload:          sessionPayload,
				OccurredAt:       now,
			},
			{
				EventID:          assetEventID,
				EventType:        "content.media_asset.created",
				AggregateType:    "MediaAsset",
				AggregateID:      asset.ID(),
				AggregateVersion: asset.Version(),
				Payload:          assetPayload,
				OccurredAt:       now,
			},
		},
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	completed := uploadSessionResult(result.Session, result.Asset, result.Replayed)
	completed.DeliveryURL = completedObject.DeliveryURL
	return completed, nil
}

func (s *MediaService) AbortMediaUpload(
	ctx context.Context,
	command AbortMediaUploadCommand,
) (MediaUploadSessionCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("AbortMediaUpload", encoded)
	if replayed, found, err := s.replayUploadSession(
		ctx,
		"AbortMediaUpload",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	session, found, err := s.loadUploadSession(ctx, command.SessionID)
	if err != nil {
		return MediaUploadSessionCommandResult{}, err
	}
	if !found {
		return MediaUploadSessionCommandResult{}, mediaNotFound(command.SessionID)
	}
	expectedVersion := session.Version()
	now := s.now().UTC()
	if err := session.Abort(command.OwnerID, now); err != nil {
		return MediaUploadSessionCommandResult{}, mapMediaDomainError(err)
	}
	payload, err := json.Marshal(mediaUploadAbortedPayload{
		SessionID: session.ID(),
		OwnerID:   session.OwnerID(),
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	return s.commitUploadSession(
		ctx,
		session,
		expectedVersion,
		"AbortMediaUpload",
		commandDigest,
		"content.media_upload.aborted",
		payload,
		now,
	)
}

func (s *MediaService) RecordMediaProcessingResult(
	ctx context.Context,
	command RecordMediaProcessingResultCommand,
) (MediaAssetCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("RecordMediaProcessingResult", encoded)
	if replayed, found, err := s.replayAsset(
		ctx,
		"RecordMediaProcessingResult",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	asset, found, err := s.loadAsset(ctx, command.AssetID)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	if !found {
		return MediaAssetCommandResult{}, mediaNotFound(command.AssetID)
	}
	expectedVersion := asset.Version()
	now := s.now().UTC()
	if err := asset.RecordProcessingResult(
		command.Processing,
		command.FailureReason,
		command.Descriptor,
		now,
	); err != nil {
		return MediaAssetCommandResult{}, mapMediaDomainError(err)
	}
	payload, err := json.Marshal(mediaAssetProcessingUpdatedPayload{
		AssetID:    asset.ID(),
		Processing: asset.ProcessingStatus(),
	})
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	return s.commitAsset(
		ctx,
		asset,
		expectedVersion,
		"RecordMediaProcessingResult",
		commandDigest,
		"content.media_asset.processing_updated",
		payload,
		now,
	)
}

func (s *MediaService) UpdateMediaAssetAccessPolicy(
	ctx context.Context,
	command UpdateMediaAssetAccessPolicyCommand,
) (MediaAssetCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("UpdateMediaAssetAccessPolicy", encoded)
	if replayed, found, err := s.replayAsset(
		ctx,
		"UpdateMediaAssetAccessPolicy",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	asset, found, err := s.loadAsset(ctx, command.AssetID)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	if !found {
		return MediaAssetCommandResult{}, mediaNotFound(command.AssetID)
	}
	// 目标 policy 已满足：持久化 no-op receipt（owner 校验仍须通过），
	// 不递增版本、不制造伪 access_policy_updated 事实。
	if asset.OwnerID() == strings.TrimSpace(command.OwnerID) &&
		asset.AccessPolicy() == command.AccessPolicy {
		return s.recordAssetNoopReceipt(
			ctx,
			asset,
			"UpdateMediaAssetAccessPolicy",
			commandDigest,
		)
	}
	expectedVersion := asset.Version()
	now := s.now().UTC()
	if err := asset.ChangeAccessPolicy(command.OwnerID, command.AccessPolicy, now); err != nil {
		return MediaAssetCommandResult{}, mapMediaDomainError(err)
	}
	payload, err := json.Marshal(mediaAssetAccessPolicyUpdatedPayload{
		AssetID:      asset.ID(),
		OwnerID:      asset.OwnerID(),
		AccessPolicy: asset.AccessPolicy(),
	})
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	return s.commitAsset(
		ctx,
		asset,
		expectedVersion,
		"UpdateMediaAssetAccessPolicy",
		commandDigest,
		"content.media_asset.access_policy_updated",
		payload,
		now,
	)
}

func (s *MediaService) RequestOriginalMediaAccess(
	ctx context.Context,
	command RequestOriginalMediaAccessCommand,
) (OriginalMediaAccessResult, error) {
	purpose := strings.ToLower(strings.TrimSpace(command.Purpose))
	if purpose == "" {
		purpose = "view"
	}
	if purpose != "view" && purpose != "save" {
		return OriginalMediaAccessResult{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"purpose 仅支持 view/save",
			"original media access purpose must be view or save",
		)
	}
	encoded, err := json.Marshal(command)
	if err != nil {
		return OriginalMediaAccessResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("RequestOriginalImageAccess", encoded)
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return OriginalMediaAccessResult{}, err
	}
	asset, err := s.GetMediaAsset(ctx, GetMediaAssetQuery{
		AssetID: command.AssetID,
		OwnerID: command.ViewerID,
	})
	if err != nil {
		return OriginalMediaAccessResult{}, err
	}
	if asset.ProcessingStatus != mediamodel.ProcessingStatusReady ||
		(asset.MediaType != "image" && asset.MediaType != "video") {
		return OriginalMediaAccessResult{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"原始媒体尚未就绪或类型不受支持",
			"original media access requires a ready image or video asset",
		)
	}
	// MongoDB persists timestamps at millisecond precision. Normalize before
	// deriving the fact and signed grant so the first response and a replay are
	// byte-for-byte stable.
	now := s.now().UTC().Truncate(time.Millisecond)
	auditDigest := sha256.Sum256([]byte(strings.Join([]string{
		idempotencyKey, asset.AssetID, command.ViewerID, purpose,
	}, ":")))
	auditID := "moa_" + hex.EncodeToString(auditDigest[:16])
	expiresAt := now.Add(5 * time.Minute)
	fact := mediamodel.MediaOriginalAccessFact{
		AuditID: auditID, AssetID: asset.AssetID, ViewerID: command.ViewerID,
		Purpose: purpose, IdempotencyKey: idempotencyKey, GrantedAt: now, ExpiresAt: expiresAt,
	}
	appended, err := s.data.OriginalAccess.AppendMediaOriginalAccess(ctx, mediaports.MediaOriginalAccessAppendRequest{
		Fact: fact, CommandDigest: commandDigest,
	})
	if err != nil {
		return OriginalMediaAccessResult{}, unavailable(err)
	}
	originalURL, err := s.objects.DeliveryURLUntil(ctx, asset.ObjectKey, appended.Fact.ExpiresAt)
	if err != nil {
		return OriginalMediaAccessResult{}, unavailable(err)
	}
	return OriginalMediaAccessResult{
		AssetID: asset.AssetID, Status: "granted", OriginalURL: originalURL,
		ContentType: asset.ContentType, FileSize: asset.FileSize,
		ExpiresAt: appended.Fact.ExpiresAt, TTLSeconds: 300,
		AuditID: appended.Fact.AuditID,
	}, nil
}

func (s *MediaService) SelectAutoMediaCover(
	ctx context.Context,
	command SelectAutoMediaCoverCommand,
) (MediaAssetCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("SelectAutoMediaCover", encoded)
	if replayed, found, err := s.replayAsset(ctx, "SelectAutoMediaCover", commandDigest); err != nil || found {
		if err != nil {
			return MediaAssetCommandResult{}, err
		}
		asset, _, loadErr := s.loadAsset(ctx, command.AssetID)
		if loadErr != nil {
			return MediaAssetCommandResult{}, loadErr
		}
		return s.decorateCoverResult(ctx, replayed, asset, nil)
	}
	asset, found, err := s.loadAsset(ctx, command.AssetID)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	if !found {
		return MediaAssetCommandResult{}, mediaNotFound(command.AssetID)
	}
	expectedVersion := asset.Version()
	now := s.now().UTC()
	if err := asset.SelectAutoCover(command.OwnerID, now); err != nil {
		return MediaAssetCommandResult{}, mapMediaDomainError(err)
	}
	payload, _ := json.Marshal(map[string]any{
		"assetId": asset.ID(), "coverStrategy": asset.CoverStrategy(), "coverFrameTimeMs": asset.CoverFrameTimeMs(),
	})
	result, err := s.commitAsset(ctx, asset, expectedVersion, "SelectAutoMediaCover", commandDigest, "content.media_asset.cover_selected", payload, now)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	return s.decorateCoverResult(ctx, result, asset, nil)
}

func (s *MediaService) SelectManualMediaCover(
	ctx context.Context,
	command SelectManualMediaCoverCommand,
) (MediaAssetCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("SelectManualMediaCover", encoded)
	if replayed, found, err := s.replayAsset(ctx, "SelectManualMediaCover", commandDigest); err != nil || found {
		if err != nil {
			return MediaAssetCommandResult{}, err
		}
		asset, _, loadErr := s.loadAsset(ctx, command.AssetID)
		if loadErr != nil {
			return MediaAssetCommandResult{}, loadErr
		}
		var cover *MediaAssetSlice
		if strings.TrimSpace(command.CoverAssetID) != "" {
			coverSlice, coverErr := s.GetMediaAsset(ctx, GetMediaAssetQuery{AssetID: command.CoverAssetID, OwnerID: command.OwnerID})
			if coverErr != nil {
				return MediaAssetCommandResult{}, coverErr
			}
			cover = &coverSlice
		}
		return s.decorateCoverResult(ctx, replayed, asset, cover)
	}
	asset, found, err := s.loadAsset(ctx, command.AssetID)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	if !found {
		return MediaAssetCommandResult{}, mediaNotFound(command.AssetID)
	}
	var cover *MediaAssetSlice
	if strings.TrimSpace(command.CoverAssetID) != "" {
		coverSlice, coverErr := s.GetMediaAsset(ctx, GetMediaAssetQuery{AssetID: command.CoverAssetID, OwnerID: command.OwnerID})
		if coverErr != nil {
			return MediaAssetCommandResult{}, coverErr
		}
		if coverSlice.MediaType != "image" || coverSlice.ProcessingStatus != mediamodel.ProcessingStatusReady {
			return MediaAssetCommandResult{}, rterr.NewInvalidArgument(rterr.ModuleContent, "封面素材必须是已就绪图片", "manual cover asset must be a ready image")
		}
		cover = &coverSlice
	}
	expectedVersion := asset.Version()
	now := s.now().UTC()
	if err := asset.SelectManualCover(command.OwnerID, command.CoverAssetID, command.CoverFrameTimeMs, now); err != nil {
		return MediaAssetCommandResult{}, mapMediaDomainError(err)
	}
	payload, _ := json.Marshal(map[string]any{
		"assetId": asset.ID(), "coverStrategy": asset.CoverStrategy(),
		"manualCoverAssetId": asset.ManualCoverAssetID(), "coverFrameTimeMs": asset.CoverFrameTimeMs(),
	})
	result, err := s.commitAsset(ctx, asset, expectedVersion, "SelectManualMediaCover", commandDigest, "content.media_asset.cover_selected", payload, now)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	return s.decorateCoverResult(ctx, result, asset, cover)
}

func (s *MediaService) decorateCoverResult(
	ctx context.Context,
	result MediaAssetCommandResult,
	asset *mediamodel.MediaAsset,
	cover *MediaAssetSlice,
) (MediaAssetCommandResult, error) {
	if asset == nil {
		return MediaAssetCommandResult{}, unavailable(errors.New("media cover result has no asset"))
	}
	if cover != nil {
		result.CoverURL = cover.DeliveryURL
		return result, nil
	}
	deliveryURL, err := s.objects.DeliveryURL(ctx, asset.ObjectKey())
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	separator := "?"
	if strings.Contains(deliveryURL, "?") {
		separator = "&"
	}
	result.CoverURL = fmt.Sprintf("%s%sx-video-frame-ms=%d", deliveryURL, separator, asset.CoverFrameTimeMs())
	return result, nil
}

func (s *MediaService) GetMediaUploadSession(
	ctx context.Context,
	query GetMediaUploadSessionQuery,
) (MediaUploadSessionSlice, error) {
	slice, found, err := s.data.UploadSessions.FindUploadSessionForOwner(
		ctx,
		strings.TrimSpace(query.SessionID),
		strings.TrimSpace(query.OwnerID),
	)
	if err != nil {
		return MediaUploadSessionSlice{}, unavailable(err)
	}
	if !found {
		return MediaUploadSessionSlice{}, mediaNotFound(query.SessionID)
	}
	return slice, nil
}

func (s *MediaService) GetMediaAsset(
	ctx context.Context,
	query GetMediaAssetQuery,
) (MediaAssetSlice, error) {
	slice, found, err := s.data.Assets.FindMediaAssetForOwner(
		ctx,
		strings.TrimSpace(query.AssetID),
		strings.TrimSpace(query.OwnerID),
	)
	if err != nil {
		return MediaAssetSlice{}, unavailable(err)
	}
	if !found {
		return MediaAssetSlice{}, mediaNotFound(query.AssetID)
	}
	deliveryKey := slice.ObjectKey
	if slice.MediaType == "image" && strings.TrimSpace(slice.ImageNormalizedObjectKey) != "" {
		deliveryKey = slice.ImageNormalizedObjectKey
	} else if slice.MediaType == "video" && strings.TrimSpace(slice.VideoPublicSliceKey) != "" {
		deliveryKey = slice.VideoPublicSliceKey
	}
	deliveryURL, err := s.objects.DeliveryURL(ctx, deliveryKey)
	if err != nil {
		return MediaAssetSlice{}, unavailable(err)
	}
	slice.DeliveryURL = deliveryURL
	return slice, nil
}

func (s *MediaService) GetOwnedReadyMediaAssetReference(
	ctx context.Context,
	query GetMediaAssetQuery,
) (MediaAssetReferenceSlice, error) {
	slice, found, err := s.data.Assets.FindMediaAssetForOwner(
		ctx,
		strings.TrimSpace(query.AssetID),
		strings.TrimSpace(query.OwnerID),
	)
	if err != nil {
		return MediaAssetReferenceSlice{}, unavailable(err)
	}
	if !found {
		return MediaAssetReferenceSlice{}, mediaNotFound(query.AssetID)
	}
	if slice.ProcessingStatus != mediamodel.ProcessingStatusReady {
		return MediaAssetReferenceSlice{}, contentgenerated.AppErrorFromMediaNotReady(
			"cross-context MediaAsset reference requires ready processing status",
		)
	}
	if strings.TrimSpace(slice.AssetID) == "" || strings.TrimSpace(slice.OwnerID) == "" ||
		strings.TrimSpace(slice.ContentType) == "" || slice.FileSize <= 0 {
		return MediaAssetReferenceSlice{}, unavailable(errors.New("MediaAsset owner projection is incomplete"))
	}
	return MediaAssetReferenceSlice{
		AssetID: slice.AssetID, OwnerPersonaID: slice.OwnerID,
		ProcessingStatus: slice.ProcessingStatus, ContentType: slice.ContentType,
		FileSize: slice.FileSize,
	}, nil
}

func (s *MediaService) GetOwnedReadyMediaAssetDeliveryReference(
	ctx context.Context,
	query GetMediaAssetQuery,
) (MediaAssetDeliveryReferenceSlice, error) {
	slice, err := s.GetMediaAsset(ctx, query)
	if err != nil {
		return MediaAssetDeliveryReferenceSlice{}, err
	}
	if slice.ProcessingStatus != mediamodel.ProcessingStatusReady {
		return MediaAssetDeliveryReferenceSlice{}, contentgenerated.AppErrorFromMediaNotReady(
			"cross-context MediaAsset delivery requires ready processing status",
		)
	}
	if strings.TrimSpace(slice.AssetID) == "" || strings.TrimSpace(slice.OwnerID) == "" ||
		strings.TrimSpace(slice.MediaType) == "" || strings.TrimSpace(slice.ContentType) == "" ||
		slice.FileSize <= 0 || strings.TrimSpace(slice.DeliveryURL) == "" {
		return MediaAssetDeliveryReferenceSlice{}, unavailable(errors.New("MediaAsset delivery projection is incomplete"))
	}
	publicSliceKey := slice.VideoPublicSliceKey
	if slice.MediaType == "image" {
		publicSliceKey = slice.ImagePublicSliceKey
	} else if slice.MediaType != "video" {
		publicSliceKey = runtimemedia.BuildContentMediaPublicSliceKey(
			slice.MediaType,
			slice.AssetID,
			slice.Version,
			slice.ContentType,
		)
	}
	if publicSliceKey == "" {
		return MediaAssetDeliveryReferenceSlice{}, unavailable(
			errors.New("MediaAsset delivery projection has no canonical public slice key"),
		)
	}
	return MediaAssetDeliveryReferenceSlice{
		AssetID: slice.AssetID, OwnerPersonaID: slice.OwnerID,
		ProcessingStatus: slice.ProcessingStatus, MediaType: slice.MediaType,
		ContentType: slice.ContentType, FileSize: slice.FileSize,
		PublicSliceKey:               publicSliceKey,
		DeliveryURL:                  slice.DeliveryURL,
		ImageWidth:                   slice.ImageWidth,
		ImageHeight:                  slice.ImageHeight,
		ImageDeliveryContentType:     slice.ImageDeliveryContentType,
		VerifiedDurationMs:           slice.VerifiedDurationMs,
		VideoWidth:                   slice.VideoWidth,
		VideoHeight:                  slice.VideoHeight,
		VideoPublicSliceKey:          slice.VideoPublicSliceKey,
		CoverPublicSliceKey:          slice.CoverPublicSliceKey,
		PreviewTrackVersion:          slice.PreviewTrackVersion,
		PreviewTrackManifestSliceKey: slice.PreviewTrackManifestSliceKey,
	}, nil
}

func (s *MediaService) GetPublicMediaAsset(
	ctx context.Context,
	query GetPublicMediaAssetQuery,
) (MediaAssetSlice, error) {
	slice, found, err := s.data.Assets.FindPublicMediaAsset(ctx, strings.TrimSpace(query.AssetID))
	if err != nil {
		return MediaAssetSlice{}, unavailable(err)
	}
	if !found {
		return MediaAssetSlice{}, mediaNotFound(query.AssetID)
	}
	deliveryKey := slice.ObjectKey
	if slice.MediaType == "image" && strings.TrimSpace(slice.ImagePublicSliceKey) != "" {
		deliveryKey = slice.ImagePublicSliceKey
	} else if slice.MediaType == "video" && strings.TrimSpace(slice.VideoPublicSliceKey) != "" {
		deliveryKey = slice.VideoPublicSliceKey
	}
	deliveryURL, err := s.objects.DeliveryURL(ctx, deliveryKey)
	if err != nil {
		return MediaAssetSlice{}, unavailable(err)
	}
	slice.DeliveryURL = deliveryURL
	return slice, nil
}
