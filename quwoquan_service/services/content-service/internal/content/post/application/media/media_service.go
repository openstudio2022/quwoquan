package media

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runtimemedia "quwoquan_service/runtime/media"
	mediaerrors "quwoquan_service/services/content-service/generated/media/media_asset"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
)

const mediaReceiptTTL = 24 * time.Hour

type MediaService struct {
	data                     DataPorts
	objects                  MediaObjectGateway
	originalAccessVisibility OriginalAccessPostVisibilityReader
	now                      func() time.Time
	newID                    func(string) (string, error)
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

func WithOriginalAccessPostVisibilityReader(
	reader OriginalAccessPostVisibilityReader,
) MediaServiceOption {
	return func(service *MediaService) {
		service.originalAccessVisibility = reader
	}
}

func NewMediaService(data DataPorts, objects MediaObjectGateway, options ...MediaServiceOption) *MediaService {
	if data.Assets == nil || data.OriginalAccess == nil || objects == nil {
		panic("MediaService requires asset, original access data ports and media object gateway")
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

func (s *MediaService) ActivateReprocessedImageDescriptor(
	ctx context.Context,
	command ActivateReprocessedImageDescriptorCommand,
) (ImageDescriptorActivationResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return ImageDescriptorActivationResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("ActivateReprocessedImageDescriptor", encoded)
	if replayed, found, err := s.replayAsset(
		ctx,
		"ActivateReprocessedImageDescriptor",
		commandDigest,
	); err != nil {
		return ImageDescriptorActivationResult{}, err
	} else if found {
		asset, assetFound, loadErr := s.loadAsset(ctx, command.AssetID)
		if loadErr != nil {
			return ImageDescriptorActivationResult{}, loadErr
		}
		if !assetFound {
			return ImageDescriptorActivationResult{}, mediaNotFound(command.AssetID)
		}
		activation, activationFound := asset.ImageDescriptorActivationForRun(command.RunID)
		if !activationFound {
			return ImageDescriptorActivationResult{}, unavailable(
				errors.New("replayed image descriptor activation audit is missing"),
			)
		}
		return ImageDescriptorActivationResult{
			AssetID:           replayed.AssetID,
			Version:           replayed.Version,
			PreviousRevision:  activation.PreviousRevision,
			ActivatedRevision: activation.Revision,
			Replayed:          true,
		}, nil
	}
	asset, found, err := s.loadAsset(ctx, command.AssetID)
	if err != nil {
		return ImageDescriptorActivationResult{}, err
	}
	if !found {
		return ImageDescriptorActivationResult{}, mediaNotFound(command.AssetID)
	}
	expectedVersion := asset.Version()
	now := s.now().UTC()
	previousRevision, activatedRevision, err := asset.ActivateReprocessedImageDescriptor(
		command.RunID,
		command.Descriptor,
		now,
	)
	if err != nil {
		return ImageDescriptorActivationResult{}, mapMediaDomainError(err)
	}
	payload, err := json.Marshal(mediaAssetImageDescriptorActivatedPayload{
		AssetID:           asset.ID(),
		RunID:             command.RunID,
		PreviousRevision:  previousRevision,
		ActivatedRevision: activatedRevision,
	})
	if err != nil {
		return ImageDescriptorActivationResult{}, unavailable(err)
	}
	committed, err := s.commitAsset(
		ctx,
		asset,
		expectedVersion,
		"ActivateReprocessedImageDescriptor",
		commandDigest,
		"content.media_asset.image_descriptor_activated",
		payload,
		now,
	)
	if err != nil {
		return ImageDescriptorActivationResult{}, err
	}
	return ImageDescriptorActivationResult{
		AssetID:           committed.AssetID,
		Version:           committed.Version,
		PreviousRevision:  previousRevision,
		ActivatedRevision: activatedRevision,
		Replayed:          committed.Replayed,
	}, nil
}

func (s *MediaService) RollbackReprocessedImageDescriptor(
	ctx context.Context,
	command RollbackReprocessedImageDescriptorCommand,
) (MediaAssetCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("RollbackReprocessedImageDescriptor", encoded)
	if replayed, found, err := s.replayAsset(
		ctx,
		"RollbackReprocessedImageDescriptor",
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
	if err := asset.RollbackImageDescriptorRevision(
		command.RunID,
		command.PreviousRevision,
		command.ActivatedRevision,
		now,
	); err != nil {
		return MediaAssetCommandResult{}, mapMediaDomainError(err)
	}
	payload, err := json.Marshal(mediaAssetImageDescriptorRolledBackPayload{
		AssetID:           asset.ID(),
		RunID:             command.RunID,
		PreviousRevision:  command.PreviousRevision,
		ActivatedRevision: command.ActivatedRevision,
	})
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	return s.commitAsset(
		ctx,
		asset,
		expectedVersion,
		"RollbackReprocessedImageDescriptor",
		commandDigest,
		"content.media_asset.image_descriptor_rolled_back",
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

func (s *MediaService) DiscardMediaAsset(
	ctx context.Context,
	command DiscardMediaAssetCommand,
) (DiscardMediaAssetResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return DiscardMediaAssetResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("DiscardMediaAsset", encoded)
	if replayed, found, err := s.replayAsset(
		ctx,
		"DiscardMediaAsset",
		commandDigest,
	); err != nil {
		return DiscardMediaAssetResult{}, err
	} else if found {
		return DiscardMediaAssetResult{
			MediaID:  replayed.AssetID,
			Status:   replayed.ProcessingStatus,
			Replayed: true,
		}, nil
	}
	asset, found, err := s.loadAsset(ctx, command.AssetID)
	if err != nil {
		return DiscardMediaAssetResult{}, err
	}
	if !found {
		return DiscardMediaAssetResult{}, mediaNotFound(command.AssetID)
	}
	if asset.ProcessingStatus() == mediamodel.ProcessingStatusDeleted {
		if strings.TrimSpace(command.OwnerID) != asset.OwnerID() {
			return DiscardMediaAssetResult{}, mediaNotFound(command.AssetID)
		}
		return DiscardMediaAssetResult{
			MediaID:  asset.ID(),
			Status:   mediamodel.ProcessingStatusDeleted,
			Replayed: true,
		}, nil
	}
	expectedVersion := asset.Version()
	now := s.now().UTC()
	if err := asset.Delete(command.OwnerID, now); err != nil {
		return DiscardMediaAssetResult{}, mapMediaDomainError(err)
	}
	payload, err := json.Marshal(mediaAssetDiscardedPayload{
		AssetID:    asset.ID(),
		Version:    asset.Version(),
		OwnerID:    asset.OwnerID(),
		ObjectKey:  asset.ObjectKey(),
		Processing: asset.ProcessingStatus(),
	})
	if err != nil {
		return DiscardMediaAssetResult{}, unavailable(err)
	}
	committed, err := s.commitAsset(
		ctx,
		asset,
		expectedVersion,
		"DiscardMediaAsset",
		commandDigest,
		"content.media_asset.discarded",
		payload,
		now,
		withMediaAssetDiscard(),
	)
	if err != nil {
		return DiscardMediaAssetResult{}, err
	}
	return DiscardMediaAssetResult{
		MediaID:  committed.AssetID,
		Status:   committed.ProcessingStatus,
		Replayed: committed.Replayed,
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
	if asset.Version() == expectedVersion {
		result, receiptErr := s.recordAssetNoopReceipt(
			ctx,
			asset,
			"SelectAutoMediaCover",
			commandDigest,
		)
		if receiptErr != nil {
			return MediaAssetCommandResult{}, receiptErr
		}
		return s.decorateCoverResult(ctx, result, asset, nil)
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
		if coverSlice.MediaType != "image" {
			return MediaAssetCommandResult{}, rterr.NewInvalidArgument(rterr.ModuleContent, "封面素材必须是已就绪图片", "manual cover asset must be a ready image")
		}
		switch coverSlice.ProcessingStatus {
		case mediamodel.ProcessingStatusReady:
		case mediamodel.ProcessingStatusProcessing:
			return MediaAssetCommandResult{}, mapMediaDomainError(mediamodel.ErrMediaNotReady)
		case mediamodel.ProcessingStatusRejected:
			return MediaAssetCommandResult{}, mapMediaDomainError(mediamodel.ErrMediaProcessingRejected)
		default:
			return MediaAssetCommandResult{}, rterr.NewInvalidArgument(rterr.ModuleContent, "封面素材必须是已就绪图片", "manual cover asset must be a ready image")
		}
		cover = &coverSlice
	}
	expectedVersion := asset.Version()
	now := s.now().UTC()
	if err := asset.SelectManualCover(command.OwnerID, command.CoverAssetID, command.CoverFrameTimeMs, now); err != nil {
		return MediaAssetCommandResult{}, mapMediaDomainError(err)
	}
	if asset.Version() == expectedVersion {
		result, receiptErr := s.recordAssetNoopReceipt(
			ctx,
			asset,
			"SelectManualMediaCover",
			commandDigest,
		)
		if receiptErr != nil {
			return MediaAssetCommandResult{}, receiptErr
		}
		return s.decorateCoverResult(ctx, result, asset, cover)
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
		return MediaAssetReferenceSlice{}, mediaerrors.AppErrorFromMediaNotReady(
			"cross-context MediaAsset reference requires ready processing status",
		)
	}
	if strings.TrimSpace(slice.AssetID) == "" || strings.TrimSpace(slice.OwnerID) == "" ||
		strings.TrimSpace(slice.MimeType) == "" || slice.FileSize <= 0 {
		return MediaAssetReferenceSlice{}, unavailable(errors.New("MediaAsset owner projection is incomplete"))
	}
	return MediaAssetReferenceSlice{
		AssetID: slice.AssetID, OwnerPersonaID: slice.OwnerID,
		ProcessingStatus: slice.ProcessingStatus, MimeType: slice.MimeType,
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
		return MediaAssetDeliveryReferenceSlice{}, mediaerrors.AppErrorFromMediaNotReady(
			"cross-context MediaAsset delivery requires ready processing status",
		)
	}
	if strings.TrimSpace(slice.AssetID) == "" || strings.TrimSpace(slice.OwnerID) == "" ||
		strings.TrimSpace(slice.MediaType) == "" || strings.TrimSpace(slice.MimeType) == "" ||
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
			slice.MimeType,
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
		MimeType: slice.MimeType, FileSize: slice.FileSize,
		PublicSliceKey:                publicSliceKey,
		DeliveryURL:                   slice.DeliveryURL,
		ImageWidth:                    slice.ImageWidth,
		ImageHeight:                   slice.ImageHeight,
		ImageDeliveryMimeType:         slice.ImageDeliveryMimeType,
		ImageDominantColor:            slice.ImageDominantColor,
		ImageLQIP:                     slice.ImageLQIP,
		ImageContentProfile:           slice.ImageContentProfile,
		ImageDerivativePolicyVersion:  slice.ImageDerivativePolicyVersion,
		VerifiedDurationMs:            slice.VerifiedDurationMs,
		VideoWidth:                    slice.VideoWidth,
		VideoHeight:                   slice.VideoHeight,
		VideoPublicSliceKey:           slice.VideoPublicSliceKey,
		CoverPublicSliceKey:           slice.CoverPublicSliceKey,
		PreviewTrackVersion:           slice.PreviewTrackVersion,
		PreviewTrackManifestSliceKey:  slice.PreviewTrackManifestSliceKey,
		HLSCMAFDescriptorVersion:      slice.HLSCMAFDescriptorVersion,
		HLSCMAFDescriptorSliceKey:     slice.HLSCMAFDescriptorSliceKey,
		HLSCMAFMasterManifestSliceKey: slice.HLSCMAFMasterManifestSliceKey,
		HLSCMAFRenditionCount:         slice.HLSCMAFRenditionCount,
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
