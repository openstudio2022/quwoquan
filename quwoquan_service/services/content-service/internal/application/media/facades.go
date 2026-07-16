package media

import "context"

// Facades are the future transport-visible object APIs. They are kept separate
// while routes remain commercially blocked, so no handler needs to reach into
// PostService's process-local media maps.
type Facades struct {
	MediaUploadSessionCommandFacet
	MediaUploadSessionQueryFacet
	MediaAssetCommandFacet
	MediaAssetQueryFacet
}

type MediaUploadSessionCommandFacet interface {
	InitMediaUpload(
		context.Context,
		InitMediaUploadCommand,
	) (MediaUploadSessionCommandResult, error)
	CompleteMediaUpload(
		context.Context,
		CompleteMediaUploadCommand,
	) (MediaUploadSessionCommandResult, error)
	AbortMediaUpload(
		context.Context,
		AbortMediaUploadCommand,
	) (MediaUploadSessionCommandResult, error)
}

type MediaUploadSessionQueryFacet interface {
	GetMediaUploadSession(
		context.Context,
		GetMediaUploadSessionQuery,
	) (MediaUploadSessionSlice, error)
}

type MediaAssetCommandFacet interface {
	RecordMediaProcessingResult(
		context.Context,
		RecordMediaProcessingResultCommand,
	) (MediaAssetCommandResult, error)
	UpdateMediaAssetAccessPolicy(
		context.Context,
		UpdateMediaAssetAccessPolicyCommand,
	) (MediaAssetCommandResult, error)
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
		MediaUploadSessionCommandFacet: service,
		MediaUploadSessionQueryFacet:   service,
		MediaAssetCommandFacet:         service,
		MediaAssetQueryFacet:           service,
	}
}
