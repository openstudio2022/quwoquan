package model

import (
	"strings"
	"time"
)

type MediaType string

const (
	MediaTypeImage MediaType = "image"
	MediaTypeVideo MediaType = "video"
	MediaTypeAudio MediaType = "audio"
	MediaTypeFile  MediaType = "file"
)

type AccessPolicy string

const (
	AccessPolicyOwnerOnly      AccessPolicy = "owner_only"
	AccessPolicyReferencedPost AccessPolicy = "referenced_post"
	AccessPolicyPublic         AccessPolicy = "public"
)

type ProcessingStatus string

const (
	ProcessingStatusProcessing ProcessingStatus = "processing"
	ProcessingStatusReady      ProcessingStatus = "ready"
	ProcessingStatusRejected   ProcessingStatus = "rejected"
	ProcessingStatusDeleted    ProcessingStatus = "deleted"
)

type VideoCodec string

const VideoCodecH264 VideoCodec = "h264"

type MediaContainer string

const MediaContainerMP4 MediaContainer = "mp4"

type AudioCodec string

const AudioCodecAAC AudioCodec = "aac"

type CoverStrategy string

const (
	CoverStrategyFirstFrame CoverStrategy = "first_frame"
	CoverStrategyManual     CoverStrategy = "manual"
)

// MediaAssetSnapshot is the persistence boundary for MediaAsset.
type MediaAssetSnapshot struct {
	ID                            string
	Version                       int64
	OwnerID                       string
	SourceSessionID               string
	ObjectKey                     string
	SHA256                        string
	MediaType                     MediaType
	MimeType                      string
	FileSize                      int64
	CaptureMetadata               CaptureMetadata
	AccessPolicy                  AccessPolicy
	ProcessingStatus              ProcessingStatus
	ProcessingVersion             int64
	ProcessingFailureReason       string
	ProcessorProfile              string
	ImageWidth                    int
	ImageHeight                   int
	ImageDeliveryMimeType         string
	ImageNormalizedObjectKey      string
	ImagePublicSliceKey           string
	ImageDominantColor            string
	ImageLQIP                     string
	ImageContentProfile           string
	ImageDerivativePolicyVersion  int
	ActiveImageDescriptorRevision int
	ImageDescriptorRevisions      []ImageDescriptorRevision
	VerifiedDurationMs            int64
	VideoWidth                    int
	VideoHeight                   int
	VideoCodec                    VideoCodec
	VideoContainer                MediaContainer
	VideoAudioCodec               AudioCodec
	VideoKeyframeIntervalMs       int
	VideoFastStart                bool
	VideoPublicSliceKey           string
	CoverPublicSliceKey           string
	PreviewTrackVersion           int
	PreviewTrackManifestSliceKey  string
	HLSCMAFDescriptorVersion      int
	HLSCMAFDescriptorSliceKey     string
	HLSCMAFMasterManifestSliceKey string
	HLSCMAFRenditionCount         int
	CoverStrategy                 CoverStrategy
	ManualCoverAssetID            string
	CoverFrameTimeMs              int64
	CreatedAt                     time.Time
	UpdatedAt                     time.Time
	ProcessedAt                   *time.Time
}

// VideoProcessingDescriptor is the trusted output produced by the VOD worker.
// It is bound to a MediaAsset version by the processing-result command, never
// accepted from a publishing client, and deliberately contains slice keys rather
// than directly consumable URLs.
type VideoProcessingDescriptor struct {
	ProcessorProfile              string
	VerifiedDurationMs            int64
	VideoWidth                    int
	VideoHeight                   int
	VideoCodec                    VideoCodec
	VideoContainer                MediaContainer
	VideoAudioCodec               AudioCodec
	VideoKeyframeIntervalMs       int
	VideoFastStart                bool
	VideoPublicSliceKey           string
	CoverPublicSliceKey           string
	PreviewTrackVersion           int
	PreviewTrackManifestSliceKey  string
	HLSCMAFDescriptorVersion      int
	HLSCMAFDescriptorSliceKey     string
	HLSCMAFMasterManifestSliceKey string
	HLSCMAFRenditionCount         int
}

// ImageProcessingDescriptor is the trusted output produced by the image
// normalization worker. The original CAS object remains immutable; this
// descriptor points to a private normalized baseline and its stable public
// slice identity. CDN variants are derived from that baseline by metadata
// profiles instead of becoming separate business objects.
type ImageProcessingDescriptor struct {
	ProcessorProfile         string
	ImageWidth               int
	ImageHeight              int
	ImageDeliveryMimeType    string
	ImageNormalizedObjectKey string
	ImagePublicSliceKey      string
	ImageDominantColor       string
	ImageLQIP                string
	ImageContentProfile      string
	DerivativePolicyVersion  int
}

// ImageDescriptorRevision is an owned MediaAsset value. It preserves the
// immutable object/slice identities of each verified image presentation so a
// reprocess run can atomically switch or restore the active descriptor without
// creating a second MediaAsset.
type ImageDescriptorRevision struct {
	Revision           int
	PreviousRevision   int
	ProcessingVersion  int64
	Descriptor         ImageProcessingDescriptor
	ActivatedByRunID   string
	ActivatedAt        time.Time
	CleanupCandidateAt *time.Time
}

// MediaProcessingDescriptor is a typed union. Exactly one member is populated
// for an image or video ready result; rejected and non-visual assets carry the
// zero value.
type MediaProcessingDescriptor struct {
	Image ImageProcessingDescriptor
	Video VideoProcessingDescriptor
}

type CreateMediaAssetParams struct {
	ID                 string
	OwnerID            string
	SourceSessionID    string
	ObjectKey          string
	SHA256             string
	MediaType          MediaType
	MimeType           string
	FileSize           int64
	CaptureMetadata    CaptureMetadata
	AccessPolicy       AccessPolicy
	ProcessingRequired bool
	Now                time.Time
}

// CaptureMetadata is the creator-disclosed EXIF snapshot owned by MediaAsset.
// Pointer scalars preserve the difference between an absent value and a valid
// zero coordinate. The type deliberately has no String method because GPS and
// CapturedAt are PII and must not enter logs.
type CaptureMetadata struct {
	CameraMake          string     `bson:"cameraMake,omitempty" json:"cameraMake,omitempty"`
	CameraModel         string     `bson:"cameraModel,omitempty" json:"cameraModel,omitempty"`
	LensModel           string     `bson:"lensModel,omitempty" json:"lensModel,omitempty"`
	FocalLengthMM       *float64   `bson:"focalLengthMm,omitempty" json:"focalLengthMm,omitempty"`
	ApertureFNumber     *float64   `bson:"apertureFNumber,omitempty" json:"apertureFNumber,omitempty"`
	ShutterSpeedSeconds *float64   `bson:"shutterSpeedSeconds,omitempty" json:"shutterSpeedSeconds,omitempty"`
	ISOSensitivity      *int       `bson:"isoSensitivity,omitempty" json:"isoSensitivity,omitempty"`
	CapturedAt          *time.Time `bson:"capturedAt,omitempty" json:"capturedAt,omitempty"`
	GPSLatitude         *float64   `bson:"gpsLatitude,omitempty" json:"gpsLatitude,omitempty"`
	GPSLongitude        *float64   `bson:"gpsLongitude,omitempty" json:"gpsLongitude,omitempty"`
}

func (m CaptureMetadata) IsEmpty() bool {
	return strings.TrimSpace(m.CameraMake) == "" &&
		strings.TrimSpace(m.CameraModel) == "" &&
		strings.TrimSpace(m.LensModel) == "" &&
		m.FocalLengthMM == nil && m.ApertureFNumber == nil &&
		m.ShutterSpeedSeconds == nil && m.ISOSensitivity == nil &&
		m.CapturedAt == nil && m.GPSLatitude == nil && m.GPSLongitude == nil
}
