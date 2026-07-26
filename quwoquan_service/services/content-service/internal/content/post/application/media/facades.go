package media

import "context"

// Facades are the future transport-visible object APIs. They are kept separate
// while routes remain commercially blocked, so no handler needs to reach into
// PostService's process-local media maps.
type Facades struct {
	MediaAssetCommandFacet
	MediaAssetQueryFacet
}

type MediaAssetCommandFacet interface {
	RecordMediaProcessingResult(
		context.Context,
		RecordMediaProcessingResultCommand,
	) (MediaAssetCommandResult, error)
	ActivateReprocessedImageDescriptor(
		context.Context,
		ActivateReprocessedImageDescriptorCommand,
	) (ImageDescriptorActivationResult, error)
	RollbackReprocessedImageDescriptor(
		context.Context,
		RollbackReprocessedImageDescriptorCommand,
	) (MediaAssetCommandResult, error)
	UpdateMediaAssetAccessPolicy(
		context.Context,
		UpdateMediaAssetAccessPolicyCommand,
	) (MediaAssetCommandResult, error)
	DiscardMediaAsset(
		context.Context,
		DiscardMediaAssetCommand,
	) (DiscardMediaAssetResult, error)
	RequestOriginalMediaAccess(
		context.Context,
		RequestOriginalMediaAccessCommand,
	) (OriginalMediaAccessResult, error)
	SelectAutoMediaCover(
		context.Context,
		SelectAutoMediaCoverCommand,
	) (MediaAssetCommandResult, error)
	SelectManualMediaCover(
		context.Context,
		SelectManualMediaCoverCommand,
	) (MediaAssetCommandResult, error)
}

type MediaAssetQueryFacet interface {
	GetOwnedReadyMediaAssetReference(
		context.Context,
		GetMediaAssetQuery,
	) (MediaAssetReferenceSlice, error)
	GetOwnedReadyMediaAssetDeliveryReference(
		context.Context,
		GetMediaAssetQuery,
	) (MediaAssetDeliveryReferenceSlice, error)
	GetMediaAsset(
		context.Context,
		GetMediaAssetQuery,
	) (MediaAssetSlice, error)
	GetPublicMediaAsset(
		context.Context,
		GetPublicMediaAssetQuery,
	) (MediaAssetSlice, error)
}

func BindFacades(service *MediaService) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{
		MediaAssetCommandFacet: service,
		MediaAssetQueryFacet:   service,
	}
}
