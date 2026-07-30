package media

import (
	"context"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
)

type RecordMediaProcessingResultCommand struct {
	AssetID       string
	Processing    mediamodel.ProcessingStatus
	FailureReason string
	Descriptor    mediamodel.MediaProcessingDescriptor
}

// ActivateReprocessedImageDescriptorCommand is internal-only. The caller must
// first validate the candidate baseline and public slice readback; this command
// performs the MediaAsset version-CAS activation.
type ActivateReprocessedImageDescriptorCommand struct {
	AssetID    string
	RunID      string
	Descriptor mediamodel.ImageProcessingDescriptor
}

type RollbackReprocessedImageDescriptorCommand struct {
	AssetID           string
	RunID             string
	PreviousRevision  int
	ActivatedRevision int
}

type ImageDescriptorActivationResult struct {
	AssetID           string
	Version           int64
	PreviousRevision  int
	ActivatedRevision int
	Replayed          bool
}

type UpdateMediaAssetAccessPolicyCommand struct {
	AssetID      string
	OwnerID      string
	AccessPolicy mediamodel.AccessPolicy
}

type DiscardMediaAssetCommand struct {
	AssetID string
	OwnerID string
}

type DiscardMediaAssetResult struct {
	MediaID  string                      `json:"mediaId"`
	Status   mediamodel.ProcessingStatus `json:"status"`
	Replayed bool                        `json:"replayed"`
}

type SelectAutoMediaCoverCommand struct {
	AssetID string
	OwnerID string
}

type SelectManualMediaCoverCommand struct {
	AssetID          string
	OwnerID          string
	CoverAssetID     string
	CoverFrameTimeMs int64
}

type RequestOriginalMediaAccessCommand struct {
	AssetID  string
	ViewerID string
	Purpose  string
}

type OriginalMediaAccessResult struct {
	AssetID     string    `json:"mediaId"`
	Status      string    `json:"status"`
	OriginalURL string    `json:"originalUrl"`
	MimeType    string    `json:"format"`
	FileSize    int64     `json:"sizeBytes"`
	ExpiresAt   time.Time `json:"expiresAt"`
	TTLSeconds  int       `json:"ttlSeconds"`
	AuditID     string    `json:"auditId"`
}

type GetMediaAssetQuery struct {
	AssetID string
	OwnerID string
}

type GetPublicMediaAssetQuery struct {
	AssetID string
}

type MediaAssetCommandResult struct {
	AssetID                      string                      `json:"assetId"`
	Version                      int64                       `json:"version"`
	ProcessingStatus             mediamodel.ProcessingStatus `json:"processingStatus"`
	AccessPolicy                 mediamodel.AccessPolicy     `json:"accessPolicy"`
	CoverStrategy                string                      `json:"coverStrategy"`
	ManualCoverAssetID           string                      `json:"manualCoverAssetId,omitempty"`
	CoverFrameTimeMs             int64                       `json:"coverFrameTimeMs"`
	ImageWidth                   int                         `json:"imageWidth,omitempty"`
	ImageHeight                  int                         `json:"imageHeight,omitempty"`
	ImageDeliveryMimeType        string                      `json:"imageDeliveryMimeType,omitempty"`
	ImageDominantColor           string                      `json:"imageDominantColor,omitempty"`
	ImageLQIP                    string                      `json:"imageLqip,omitempty"`
	ImageContentProfile          string                      `json:"imageContentProfile,omitempty"`
	ImageDerivativePolicyVersion int                         `json:"imageDerivativePolicyVersion,omitempty"`
	VerifiedDurationMs           int64                       `json:"verifiedDurationMs,omitempty"`
	VideoWidth                   int                         `json:"videoWidth,omitempty"`
	VideoHeight                  int                         `json:"videoHeight,omitempty"`
	VideoCodec                   mediamodel.VideoCodec       `json:"videoCodec,omitempty"`
	VideoContainer               mediamodel.MediaContainer   `json:"videoContainer,omitempty"`
	VideoAudioCodec              mediamodel.AudioCodec       `json:"videoAudioCodec,omitempty"`
	VideoKeyframeIntervalMs      int                         `json:"videoKeyframeIntervalMs,omitempty"`
	VideoFastStart               bool                        `json:"videoFastStart,omitempty"`
	PreviewTrackVersion          int                         `json:"previewTrackVersion,omitempty"`
	HLSCMAFDescriptorVersion     int                         `json:"hlsCmafDescriptorVersion,omitempty"`
	HLSCMAFRenditionCount        int                         `json:"hlsCmafRenditionCount,omitempty"`
	CoverURL                     string                      `json:"coverUrl,omitempty"`
	Replayed                     bool                        `json:"replayed"`
}

type MediaObjectGateway interface {
	PublishPublicSlice(context.Context, string, string) error
	DeliveryURL(context.Context, string) (string, error)
	DeliveryURLUntil(context.Context, string, time.Time) (string, error)
}

// MediaAssetSlice is a typed BSON projection for owner-facing reads.
type MediaAssetSlice struct {
	AssetID                       string                      `json:"assetId"`
	Version                       int64                       `json:"version"`
	OwnerID                       string                      `json:"-"`
	SourceSessionID               string                      `json:"-"`
	ObjectKey                     string                      `json:"-"`
	SHA256                        string                      `json:"-"`
	MediaType                     string                      `json:"mediaType"`
	MimeType                      string                      `json:"mimeType"`
	FileSize                      int64                       `json:"fileSize"`
	AccessPolicy                  mediamodel.AccessPolicy     `json:"accessPolicy"`
	ProcessingStatus              mediamodel.ProcessingStatus `json:"status"`
	CreatedAt                     time.Time                   `json:"createdAt"`
	UpdatedAt                     time.Time                   `json:"updatedAt"`
	ProcessedAt                   *time.Time                  `json:"processedAt,omitempty"`
	CoverStrategy                 string                      `json:"coverStrategy"`
	ManualCoverAssetID            string                      `json:"manualCoverAssetId,omitempty"`
	CoverFrameTimeMs              int64                       `json:"coverFrameTimeMs"`
	ProcessorProfile              string                      `json:"-"`
	ImageWidth                    int                         `json:"imageWidth,omitempty"`
	ImageHeight                   int                         `json:"imageHeight,omitempty"`
	ImageDeliveryMimeType         string                      `json:"imageDeliveryMimeType,omitempty"`
	ImageNormalizedObjectKey      string                      `json:"-"`
	ImagePublicSliceKey           string                      `json:"-"`
	ImageDominantColor            string                      `json:"imageDominantColor,omitempty"`
	ImageLQIP                     string                      `json:"imageLqip,omitempty"`
	ImageContentProfile           string                      `json:"imageContentProfile,omitempty"`
	ImageDerivativePolicyVersion  int                         `json:"imageDerivativePolicyVersion,omitempty"`
	VerifiedDurationMs            int64                       `json:"verifiedDurationMs,omitempty"`
	VideoWidth                    int                         `json:"videoWidth,omitempty"`
	VideoHeight                   int                         `json:"videoHeight,omitempty"`
	VideoCodec                    mediamodel.VideoCodec       `json:"videoCodec,omitempty"`
	VideoContainer                mediamodel.MediaContainer   `json:"videoContainer,omitempty"`
	VideoAudioCodec               mediamodel.AudioCodec       `json:"videoAudioCodec,omitempty"`
	VideoKeyframeIntervalMs       int                         `json:"videoKeyframeIntervalMs,omitempty"`
	VideoFastStart                bool                        `json:"videoFastStart,omitempty"`
	VideoPublicSliceKey           string                      `json:"-"`
	CoverPublicSliceKey           string                      `json:"-"`
	PreviewTrackVersion           int                         `json:"previewTrackVersion,omitempty"`
	PreviewTrackManifestSliceKey  string                      `json:"-"`
	HLSCMAFDescriptorVersion      int                         `json:"hlsCmafDescriptorVersion,omitempty"`
	HLSCMAFDescriptorSliceKey     string                      `json:"-"`
	HLSCMAFMasterManifestSliceKey string                      `json:"-"`
	HLSCMAFRenditionCount         int                         `json:"hlsCmafRenditionCount,omitempty"`
	DeliveryURL                   string                      `json:"cdnUrl"`
}

// MediaAssetReferenceSlice is the minimal owner-scoped reference contract
// exposed to another bounded context. It intentionally contains neither an
// object-storage key nor a delivery URL.
type MediaAssetReferenceSlice struct {
	AssetID          string                      `json:"assetId"`
	OwnerPersonaID   string                      `json:"ownerPersonaId"`
	ProcessingStatus mediamodel.ProcessingStatus `json:"processingStatus"`
	MimeType         string                      `json:"mimeType"`
	FileSize         int64                       `json:"fileSize"`
}

// MediaAssetDeliveryReferenceSlice is the owner-scoped, service-to-service
// projection used by a bounded context after it has enforced its own access
// policy. It never exposes an object-storage key or digest.
type MediaAssetDeliveryReferenceSlice struct {
	AssetID                       string                      `json:"assetId"`
	OwnerPersonaID                string                      `json:"ownerPersonaId"`
	ProcessingStatus              mediamodel.ProcessingStatus `json:"processingStatus"`
	MediaType                     string                      `json:"mediaType"`
	MimeType                      string                      `json:"mimeType"`
	FileSize                      int64                       `json:"fileSize"`
	PublicSliceKey                string                      `json:"publicSliceKey,omitempty"`
	DeliveryURL                   string                      `json:"cdnUrl"`
	ImageWidth                    int                         `json:"imageWidth,omitempty"`
	ImageHeight                   int                         `json:"imageHeight,omitempty"`
	ImageDeliveryMimeType         string                      `json:"imageDeliveryMimeType,omitempty"`
	ImageDominantColor            string                      `json:"imageDominantColor,omitempty"`
	ImageLQIP                     string                      `json:"imageLqip,omitempty"`
	ImageContentProfile           string                      `json:"imageContentProfile,omitempty"`
	ImageDerivativePolicyVersion  int                         `json:"imageDerivativePolicyVersion,omitempty"`
	VerifiedDurationMs            int64                       `json:"verifiedDurationMs,omitempty"`
	VideoWidth                    int                         `json:"videoWidth,omitempty"`
	VideoHeight                   int                         `json:"videoHeight,omitempty"`
	VideoAudioCodec               mediamodel.AudioCodec       `json:"videoAudioCodec,omitempty"`
	VideoKeyframeIntervalMs       int                         `json:"videoKeyframeIntervalMs,omitempty"`
	VideoFastStart                bool                        `json:"videoFastStart,omitempty"`
	VideoPublicSliceKey           string                      `json:"videoPublicSliceKey,omitempty"`
	CoverPublicSliceKey           string                      `json:"coverPublicSliceKey,omitempty"`
	PreviewTrackVersion           int                         `json:"previewTrackVersion,omitempty"`
	PreviewTrackManifestSliceKey  string                      `json:"previewTrackManifestSliceKey,omitempty"`
	HLSCMAFDescriptorVersion      int                         `json:"hlsCmafDescriptorVersion,omitempty"`
	HLSCMAFDescriptorSliceKey     string                      `json:"hlsCmafDescriptorSliceKey,omitempty"`
	HLSCMAFMasterManifestSliceKey string                      `json:"hlsCmafMasterManifestSliceKey,omitempty"`
	HLSCMAFRenditionCount         int                         `json:"hlsCmafRenditionCount,omitempty"`
	ExpiresAt                     string                      `json:"expiresAt,omitempty"`
}

type MediaAssetOwnerReader interface {
	FindMediaAssetForOwner(
		ctx context.Context,
		assetID string,
		ownerID string,
	) (MediaAssetSlice, bool, error)
}

// MediaAssetOriginalAccessReader 是原图授权的内部 named reader。它不按
// caller owner 过滤，调用方必须先使用 Post 可见性和 asset policy 进行授权。
type MediaAssetOriginalAccessReader interface {
	FindMediaAssetForOriginalAccess(
		ctx context.Context,
		assetID string,
	) (MediaAssetSlice, bool, error)
}

type MediaAssetPublicReader interface {
	FindPublicMediaAsset(
		ctx context.Context,
		assetID string,
	) (MediaAssetSlice, bool, error)
}
