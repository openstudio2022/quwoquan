package media

import (
	"context"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

type InitMediaUploadCommand struct {
	OwnerID        string
	MediaType      string
	ContentType    string
	FileSize       int64
	ExpectedSHA256 string
}

type CompleteMediaUploadCommand struct {
	SessionID    string
	OwnerID      string
	AccessPolicy mediamodel.AccessPolicy
}

type AbortMediaUploadCommand struct {
	SessionID string
	OwnerID   string
}

type RecordMediaProcessingResultCommand struct {
	AssetID       string
	Processing    mediamodel.ProcessingStatus
	FailureReason string
	Descriptor    mediamodel.MediaProcessingDescriptor
}

type UpdateMediaAssetAccessPolicyCommand struct {
	AssetID      string
	OwnerID      string
	AccessPolicy mediamodel.AccessPolicy
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
	ContentType string    `json:"format"`
	FileSize    int64     `json:"sizeBytes"`
	ExpiresAt   time.Time `json:"expiresAt"`
	TTLSeconds  int       `json:"ttlSeconds"`
	AuditID     string    `json:"auditId"`
}

type GetMediaUploadSessionQuery struct {
	SessionID string
	OwnerID   string
}

type GetMediaAssetQuery struct {
	AssetID string
	OwnerID string
}

type GetPublicMediaAssetQuery struct {
	AssetID string
}

type MediaUploadSessionCommandResult struct {
	SessionID   string
	Version     int64
	Status      mediamodel.UploadSessionStatus
	AssetID     string
	ObjectKey   string
	UploadURL   string
	DeliveryURL string
	ExpiresAt   time.Time
	Replayed    bool
}

type MediaAssetCommandResult struct {
	AssetID                  string                      `json:"assetId"`
	Version                  int64                       `json:"version"`
	ProcessingStatus         mediamodel.ProcessingStatus `json:"processingStatus"`
	AccessPolicy             mediamodel.AccessPolicy     `json:"accessPolicy"`
	CoverStrategy            string                      `json:"coverStrategy"`
	ManualCoverAssetID       string                      `json:"manualCoverAssetId,omitempty"`
	CoverFrameTimeMs         int64                       `json:"coverFrameTimeMs"`
	ImageWidth               int                         `json:"imageWidth,omitempty"`
	ImageHeight              int                         `json:"imageHeight,omitempty"`
	ImageDeliveryContentType string                      `json:"imageDeliveryContentType,omitempty"`
	VerifiedDurationMs       int64                       `json:"verifiedDurationMs,omitempty"`
	VideoWidth               int                         `json:"videoWidth,omitempty"`
	VideoHeight              int                         `json:"videoHeight,omitempty"`
	VideoCodec               string                      `json:"videoCodec,omitempty"`
	VideoContainer           string                      `json:"videoContainer,omitempty"`
	VideoAudioCodec          string                      `json:"videoAudioCodec,omitempty"`
	VideoKeyframeIntervalMs  int                         `json:"videoKeyframeIntervalMs,omitempty"`
	VideoFastStart           bool                        `json:"videoFastStart,omitempty"`
	PreviewTrackVersion      int                         `json:"previewTrackVersion,omitempty"`
	CoverURL                 string                      `json:"coverUrl,omitempty"`
	Replayed                 bool                        `json:"replayed"`
}

// MediaUploadSessionSlice contains the owner-scoped projection. The expected
// digest is intentionally not exposed outside the write model.
type MediaUploadSessionSlice struct {
	SessionID   string                         `json:"sessionId"`
	Version     int64                          `json:"version"`
	AssetID     string                         `json:"assetId,omitempty"`
	ObjectKey   string                         `json:"objectKey"`
	MediaType   string                         `json:"mediaType"`
	ContentType string                         `json:"contentType"`
	FileSize    int64                          `json:"fileSize"`
	Status      mediamodel.UploadSessionStatus `json:"status"`
	CreatedAt   time.Time                      `json:"createdAt"`
	UpdatedAt   time.Time                      `json:"updatedAt"`
	ExpiresAt   time.Time                      `json:"expiresAt"`
}

type PrepareUploadParams struct {
	SessionID      string
	OwnerID        string
	MediaType      string
	ContentType    string
	FileSize       int64
	ExpectedSHA256 string
	ExpiresAt      time.Time
}

type UploadGrant struct {
	ObjectKey string
	UploadURL string
	ExpiresAt time.Time
}

type CompleteUploadParams struct {
	ObjectKey      string
	ExpectedSHA256 string
	MediaType      string
	ContentType    string
	FileSize       int64
}

type CompletedUploadObject struct {
	ObjectKey   string
	SHA256      string
	DeliveryURL string
}

type MediaObjectGateway interface {
	PrepareUpload(context.Context, PrepareUploadParams) (UploadGrant, error)
	UploadURL(context.Context, string, string, string, time.Time) (string, error)
	CompleteUpload(context.Context, CompleteUploadParams) (CompletedUploadObject, error)
	PublishPublicSlice(context.Context, string, string) error
	DeliveryURL(context.Context, string) (string, error)
	DeliveryURLUntil(context.Context, string, time.Time) (string, error)
}

// MediaAssetSlice is a typed BSON projection for owner-facing reads.
type MediaAssetSlice struct {
	AssetID                      string                      `json:"assetId"`
	Version                      int64                       `json:"version"`
	OwnerID                      string                      `json:"-"`
	SourceSessionID              string                      `json:"-"`
	ObjectKey                    string                      `json:"-"`
	SHA256                       string                      `json:"-"`
	MediaType                    string                      `json:"mediaType"`
	ContentType                  string                      `json:"contentType"`
	FileSize                     int64                       `json:"fileSize"`
	AccessPolicy                 mediamodel.AccessPolicy     `json:"accessPolicy"`
	ProcessingStatus             mediamodel.ProcessingStatus `json:"status"`
	CreatedAt                    time.Time                   `json:"createdAt"`
	UpdatedAt                    time.Time                   `json:"updatedAt"`
	ProcessedAt                  *time.Time                  `json:"processedAt,omitempty"`
	CoverStrategy                string                      `json:"coverStrategy"`
	ManualCoverAssetID           string                      `json:"manualCoverAssetId,omitempty"`
	CoverFrameTimeMs             int64                       `json:"coverFrameTimeMs"`
	ProcessorProfile             string                      `json:"-"`
	ImageWidth                   int                         `json:"imageWidth,omitempty"`
	ImageHeight                  int                         `json:"imageHeight,omitempty"`
	ImageDeliveryContentType     string                      `json:"imageDeliveryContentType,omitempty"`
	ImageNormalizedObjectKey     string                      `json:"-"`
	ImagePublicSliceKey          string                      `json:"-"`
	VerifiedDurationMs           int64                       `json:"verifiedDurationMs,omitempty"`
	VideoWidth                   int                         `json:"videoWidth,omitempty"`
	VideoHeight                  int                         `json:"videoHeight,omitempty"`
	VideoCodec                   string                      `json:"videoCodec,omitempty"`
	VideoContainer               string                      `json:"videoContainer,omitempty"`
	VideoAudioCodec              string                      `json:"videoAudioCodec,omitempty"`
	VideoKeyframeIntervalMs      int                         `json:"videoKeyframeIntervalMs,omitempty"`
	VideoFastStart               bool                        `json:"videoFastStart,omitempty"`
	VideoPublicSliceKey          string                      `json:"-"`
	CoverPublicSliceKey          string                      `json:"-"`
	PreviewTrackVersion          int                         `json:"previewTrackVersion,omitempty"`
	PreviewTrackManifestSliceKey string                      `json:"-"`
	DeliveryURL                  string                      `json:"cdnUrl"`
}

// MediaAssetReferenceSlice is the minimal owner-scoped reference contract
// exposed to another bounded context. It intentionally contains neither an
// object-storage key nor a delivery URL.
type MediaAssetReferenceSlice struct {
	AssetID          string                      `json:"assetId"`
	OwnerPersonaID   string                      `json:"ownerPersonaId"`
	ProcessingStatus mediamodel.ProcessingStatus `json:"processingStatus"`
	ContentType      string                      `json:"contentType"`
	FileSize         int64                       `json:"fileSize"`
}

// MediaAssetDeliveryReferenceSlice is the owner-scoped, service-to-service
// projection used by a bounded context after it has enforced its own access
// policy. It never exposes an object-storage key or digest.
type MediaAssetDeliveryReferenceSlice struct {
	AssetID                      string                      `json:"assetId"`
	OwnerPersonaID               string                      `json:"ownerPersonaId"`
	ProcessingStatus             mediamodel.ProcessingStatus `json:"processingStatus"`
	MediaType                    string                      `json:"mediaType"`
	ContentType                  string                      `json:"contentType"`
	FileSize                     int64                       `json:"fileSize"`
	PublicSliceKey               string                      `json:"publicSliceKey,omitempty"`
	DeliveryURL                  string                      `json:"cdnUrl"`
	ImageWidth                   int                         `json:"imageWidth,omitempty"`
	ImageHeight                  int                         `json:"imageHeight,omitempty"`
	ImageDeliveryContentType     string                      `json:"imageDeliveryContentType,omitempty"`
	VerifiedDurationMs           int64                       `json:"verifiedDurationMs,omitempty"`
	VideoWidth                   int                         `json:"videoWidth,omitempty"`
	VideoHeight                  int                         `json:"videoHeight,omitempty"`
	VideoAudioCodec              string                      `json:"videoAudioCodec,omitempty"`
	VideoKeyframeIntervalMs      int                         `json:"videoKeyframeIntervalMs,omitempty"`
	VideoFastStart               bool                        `json:"videoFastStart,omitempty"`
	VideoPublicSliceKey          string                      `json:"videoPublicSliceKey,omitempty"`
	CoverPublicSliceKey          string                      `json:"coverPublicSliceKey,omitempty"`
	PreviewTrackVersion          int                         `json:"previewTrackVersion,omitempty"`
	PreviewTrackManifestSliceKey string                      `json:"previewTrackManifestSliceKey,omitempty"`
	ExpiresAt                    string                      `json:"expiresAt,omitempty"`
}

type MediaUploadSessionOwnerReader interface {
	FindUploadSessionForOwner(
		ctx context.Context,
		sessionID string,
		ownerID string,
	) (MediaUploadSessionSlice, bool, error)
}

type MediaAssetOwnerReader interface {
	FindMediaAssetForOwner(
		ctx context.Context,
		assetID string,
		ownerID string,
	) (MediaAssetSlice, bool, error)
}

type MediaAssetPublicReader interface {
	FindPublicMediaAsset(
		ctx context.Context,
		assetID string,
	) (MediaAssetSlice, bool, error)
}
