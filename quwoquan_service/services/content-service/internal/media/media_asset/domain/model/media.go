package model

import (
	"encoding/base64"
	"errors"
	"fmt"
	"math"
	"strings"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
)

const (
	MaxVideoDurationMs         int64 = 3_600_000
	MaxVideoKeyframeIntervalMs       = 2_000
	MaxImageDimension                = 8_192
	MaxImagePixels             int64 = 64_000_000
	MaxImageDeliveryDimension        = 2_560
	MaxImageLQIPDataURIBytes         = 8_192
)

var (
	ErrInvalidMediaAsset           = errors.New("invalid media asset")
	ErrInvalidMediaAssetTransition = errors.New("invalid media asset transition")
	ErrMediaAssetOwnerForbidden    = errors.New("media asset owner forbidden")
	ErrMediaNotReady               = errors.New("media asset is not ready")
	ErrMediaProcessingRejected     = errors.New("media asset processing was rejected")
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

// MediaAsset is a durable, independently authorized media object. It never
// derives its owner or processing state from PostService process-local maps.
type MediaAsset struct {
	id                            string
	version                       int64
	ownerID                       string
	sourceSessionID               string
	objectKey                     string
	sha256                        string
	mediaType                     MediaType
	mimeType                      string
	fileSize                      int64
	captureMetadata               CaptureMetadata
	accessPolicy                  AccessPolicy
	processingStatus              ProcessingStatus
	processingVersion             int64
	processingFailureReason       string
	processorProfile              string
	imageWidth                    int
	imageHeight                   int
	imageDeliveryMimeType         string
	imageNormalizedObjectKey      string
	imagePublicSliceKey           string
	imageDominantColor            string
	imageLQIP                     string
	imageContentProfile           string
	imageDerivativePolicyVersion  int
	activeImageDescriptorRevision int
	imageDescriptorRevisions      []ImageDescriptorRevision
	verifiedDurationMs            int64
	videoWidth                    int
	videoHeight                   int
	videoCodec                    VideoCodec
	videoContainer                MediaContainer
	videoAudioCodec               AudioCodec
	videoKeyframeIntervalMs       int
	videoFastStart                bool
	videoPublicSliceKey           string
	coverPublicSliceKey           string
	previewTrackVersion           int
	previewTrackManifestSliceKey  string
	hlsCMAFDescriptorVersion      int
	hlsCMAFDescriptorSliceKey     string
	hlsCMAFMasterManifestSliceKey string
	hlsCMAFRenditionCount         int
	coverStrategy                 CoverStrategy
	manualCoverAssetID            string
	coverFrameTimeMs              int64
	createdAt                     time.Time
	updatedAt                     time.Time
	processedAt                   *time.Time
}

func CreateMediaAsset(params CreateMediaAssetParams) (*MediaAsset, error) {
	now := params.Now.UTC()
	asset := &MediaAsset{
		id:               strings.TrimSpace(params.ID),
		version:          1,
		ownerID:          strings.TrimSpace(params.OwnerID),
		sourceSessionID:  strings.TrimSpace(params.SourceSessionID),
		objectKey:        strings.TrimSpace(params.ObjectKey),
		sha256:           normalizeDigest(params.SHA256),
		mediaType:        MediaType(strings.ToLower(strings.TrimSpace(string(params.MediaType)))),
		mimeType:         strings.TrimSpace(params.MimeType),
		fileSize:         params.FileSize,
		captureMetadata:  normalizeCaptureMetadata(params.CaptureMetadata),
		accessPolicy:     params.AccessPolicy,
		processingStatus: ProcessingStatusReady,
		coverStrategy:    CoverStrategyFirstFrame,
		createdAt:        now,
		updatedAt:        now,
	}
	if params.ProcessingRequired {
		asset.processingStatus = ProcessingStatusProcessing
	} else {
		processedAt := now
		asset.processedAt = &processedAt
	}
	if err := asset.validate(); err != nil {
		return nil, err
	}
	return asset, nil
}

func RestoreMediaAsset(snapshot MediaAssetSnapshot) (*MediaAsset, error) {
	asset := &MediaAsset{
		id:                            strings.TrimSpace(snapshot.ID),
		version:                       snapshot.Version,
		ownerID:                       strings.TrimSpace(snapshot.OwnerID),
		sourceSessionID:               strings.TrimSpace(snapshot.SourceSessionID),
		objectKey:                     strings.TrimSpace(snapshot.ObjectKey),
		sha256:                        normalizeDigest(snapshot.SHA256),
		mediaType:                     MediaType(strings.ToLower(strings.TrimSpace(string(snapshot.MediaType)))),
		mimeType:                      strings.TrimSpace(snapshot.MimeType),
		fileSize:                      snapshot.FileSize,
		captureMetadata:               normalizeCaptureMetadata(snapshot.CaptureMetadata),
		accessPolicy:                  snapshot.AccessPolicy,
		processingStatus:              snapshot.ProcessingStatus,
		processingVersion:             snapshot.ProcessingVersion,
		processingFailureReason:       strings.TrimSpace(snapshot.ProcessingFailureReason),
		processorProfile:              strings.TrimSpace(snapshot.ProcessorProfile),
		imageWidth:                    snapshot.ImageWidth,
		imageHeight:                   snapshot.ImageHeight,
		imageDeliveryMimeType:         strings.TrimSpace(snapshot.ImageDeliveryMimeType),
		imageNormalizedObjectKey:      strings.TrimSpace(snapshot.ImageNormalizedObjectKey),
		imagePublicSliceKey:           strings.TrimSpace(snapshot.ImagePublicSliceKey),
		imageDominantColor:            strings.TrimSpace(snapshot.ImageDominantColor),
		imageLQIP:                     strings.TrimSpace(snapshot.ImageLQIP),
		imageContentProfile:           strings.TrimSpace(snapshot.ImageContentProfile),
		imageDerivativePolicyVersion:  snapshot.ImageDerivativePolicyVersion,
		activeImageDescriptorRevision: snapshot.ActiveImageDescriptorRevision,
		imageDescriptorRevisions:      cloneImageDescriptorRevisions(snapshot.ImageDescriptorRevisions),
		verifiedDurationMs:            snapshot.VerifiedDurationMs,
		videoWidth:                    snapshot.VideoWidth,
		videoHeight:                   snapshot.VideoHeight,
		videoCodec:                    VideoCodec(strings.ToLower(strings.TrimSpace(string(snapshot.VideoCodec)))),
		videoContainer:                MediaContainer(strings.ToLower(strings.TrimSpace(string(snapshot.VideoContainer)))),
		videoAudioCodec:               AudioCodec(strings.ToLower(strings.TrimSpace(string(snapshot.VideoAudioCodec)))),
		videoKeyframeIntervalMs:       snapshot.VideoKeyframeIntervalMs,
		videoFastStart:                snapshot.VideoFastStart,
		videoPublicSliceKey:           strings.TrimSpace(snapshot.VideoPublicSliceKey),
		coverPublicSliceKey:           strings.TrimSpace(snapshot.CoverPublicSliceKey),
		previewTrackVersion:           snapshot.PreviewTrackVersion,
		previewTrackManifestSliceKey:  strings.TrimSpace(snapshot.PreviewTrackManifestSliceKey),
		hlsCMAFDescriptorVersion:      snapshot.HLSCMAFDescriptorVersion,
		hlsCMAFDescriptorSliceKey:     strings.TrimSpace(snapshot.HLSCMAFDescriptorSliceKey),
		hlsCMAFMasterManifestSliceKey: strings.TrimSpace(snapshot.HLSCMAFMasterManifestSliceKey),
		hlsCMAFRenditionCount:         snapshot.HLSCMAFRenditionCount,
		coverStrategy:                 CoverStrategy(strings.ToLower(strings.TrimSpace(string(snapshot.CoverStrategy)))),
		manualCoverAssetID:            strings.TrimSpace(snapshot.ManualCoverAssetID),
		coverFrameTimeMs:              snapshot.CoverFrameTimeMs,
		createdAt:                     snapshot.CreatedAt.UTC(),
		updatedAt:                     snapshot.UpdatedAt.UTC(),
		processedAt:                   cloneTime(snapshot.ProcessedAt),
	}
	if err := asset.validate(); err != nil {
		return nil, err
	}
	return asset, nil
}

func (a *MediaAsset) RecordProcessingResult(
	status ProcessingStatus,
	failureReason string,
	descriptor MediaProcessingDescriptor,
	now time.Time,
) error {
	if a == nil || a.processingStatus != ProcessingStatusProcessing {
		return fmt.Errorf("%w: only processing assets can receive a processing result", ErrInvalidMediaAssetTransition)
	}
	if status != ProcessingStatusReady && status != ProcessingStatusRejected {
		return fmt.Errorf("%w: processing result must be ready or rejected", ErrInvalidMediaAsset)
	}
	if status == ProcessingStatusRejected && strings.TrimSpace(failureReason) == "" {
		return fmt.Errorf("%w: rejected asset requires failure reason", ErrInvalidMediaAsset)
	}
	if status == ProcessingStatusReady && strings.TrimSpace(failureReason) != "" {
		return fmt.Errorf("%w: ready asset cannot carry failure reason", ErrInvalidMediaAsset)
	}
	// 处理产物 slice 绑定本次状态迁移后的聚合 revision；worker 同样以
	// current revision + 1 构造 key。先校验再 advance 时必须显式传目标 revision，
	// 否则本次迁移的产物会被错误地按迁移前 revision 拒绝。
	if err := a.validateProcessingDescriptor(status, descriptor, a.version+1); err != nil {
		return err
	}
	if err := a.advance(now); err != nil {
		return err
	}
	processedAt := a.updatedAt
	a.processingStatus = status
	a.processingVersion = a.version
	a.processingFailureReason = strings.TrimSpace(failureReason)
	if status == ProcessingStatusReady {
		switch a.mediaType {
		case "image":
			a.applyImageDescriptor(descriptor.Image)
			a.imageDescriptorRevisions = []ImageDescriptorRevision{{
				Revision:          1,
				ProcessingVersion: a.processingVersion,
				Descriptor:        a.ImageProcessingDescriptor(),
				ActivatedAt:       processedAt,
			}}
			a.activeImageDescriptorRevision = 1
		case "video":
			a.processorProfile = strings.TrimSpace(descriptor.Video.ProcessorProfile)
			a.verifiedDurationMs = descriptor.Video.VerifiedDurationMs
			a.videoWidth = descriptor.Video.VideoWidth
			a.videoHeight = descriptor.Video.VideoHeight
			a.videoCodec = descriptor.Video.VideoCodec
			a.videoContainer = descriptor.Video.VideoContainer
			a.videoAudioCodec = descriptor.Video.VideoAudioCodec
			a.videoKeyframeIntervalMs = descriptor.Video.VideoKeyframeIntervalMs
			a.videoFastStart = descriptor.Video.VideoFastStart
			a.videoPublicSliceKey = strings.TrimSpace(descriptor.Video.VideoPublicSliceKey)
			a.coverPublicSliceKey = strings.TrimSpace(descriptor.Video.CoverPublicSliceKey)
			a.previewTrackVersion = descriptor.Video.PreviewTrackVersion
			a.previewTrackManifestSliceKey = strings.TrimSpace(descriptor.Video.PreviewTrackManifestSliceKey)
			a.hlsCMAFDescriptorVersion = descriptor.Video.HLSCMAFDescriptorVersion
			a.hlsCMAFDescriptorSliceKey = strings.TrimSpace(descriptor.Video.HLSCMAFDescriptorSliceKey)
			a.hlsCMAFMasterManifestSliceKey = strings.TrimSpace(descriptor.Video.HLSCMAFMasterManifestSliceKey)
			a.hlsCMAFRenditionCount = descriptor.Video.HLSCMAFRenditionCount
		}
	}
	a.processedAt = &processedAt
	return nil
}

func (a *MediaAsset) validateProcessingDescriptor(
	status ProcessingStatus,
	descriptor MediaProcessingDescriptor,
	assetVersion int64,
) error {
	if status == ProcessingStatusRejected {
		if descriptor != (MediaProcessingDescriptor{}) {
			return fmt.Errorf("%w: rejected media carries descriptor", ErrInvalidMediaAsset)
		}
		return nil
	}
	switch a.mediaType {
	case "image":
		if descriptor.Video != (VideoProcessingDescriptor{}) {
			return fmt.Errorf("%w: ready image carries video descriptor", ErrInvalidMediaAsset)
		}
		image := descriptor.Image
		pixels := int64(image.ImageWidth) * int64(image.ImageHeight)
		if strings.TrimSpace(image.ProcessorProfile) == "" ||
			image.ImageWidth <= 0 ||
			image.ImageHeight <= 0 ||
			image.ImageWidth > MaxImageDeliveryDimension ||
			image.ImageHeight > MaxImageDeliveryDimension ||
			pixels <= 0 ||
			pixels > MaxImagePixels ||
			(strings.TrimSpace(image.ImageDeliveryMimeType) != "image/jpeg" &&
				strings.TrimSpace(image.ImageDeliveryMimeType) != "image/png") ||
			strings.TrimSpace(image.ImageNormalizedObjectKey) == "" ||
			strings.TrimSpace(image.ImagePublicSliceKey) == "" ||
			!validImageDominantColor(image.ImageDominantColor) ||
			!validImageLQIP(image.ImageLQIP) ||
			!validImageContentProfile(image.ImageContentProfile) ||
			image.DerivativePolicyVersion <= 0 {
			return fmt.Errorf(
				"%w: ready image requires a complete bounded delivery descriptor",
				ErrInvalidMediaAsset,
			)
		}
		expectedPublicSlice := runtimemedia.BuildContentMediaPublicSliceKey(
			"image",
			a.id,
			assetVersion,
			image.ImageDeliveryMimeType,
		)
		if strings.TrimSpace(image.ImagePublicSliceKey) != expectedPublicSlice {
			return fmt.Errorf(
				"%w: ready image public slice must use canonical asset identity",
				ErrInvalidMediaAsset,
			)
		}
	case "video":
		if descriptor.Image != (ImageProcessingDescriptor{}) {
			return fmt.Errorf("%w: ready video carries image descriptor", ErrInvalidMediaAsset)
		}
		video := descriptor.Video
		if strings.TrimSpace(video.ProcessorProfile) == "" ||
			video.VerifiedDurationMs <= 0 ||
			video.VerifiedDurationMs > MaxVideoDurationMs ||
			video.VideoWidth <= 0 ||
			video.VideoHeight <= 0 ||
			video.VideoCodec != VideoCodecH264 ||
			video.VideoContainer != MediaContainerMP4 ||
			video.VideoAudioCodec != AudioCodecAAC ||
			video.VideoKeyframeIntervalMs <= 0 ||
			video.VideoKeyframeIntervalMs > MaxVideoKeyframeIntervalMs ||
			!video.VideoFastStart ||
			strings.TrimSpace(video.VideoPublicSliceKey) == "" ||
			strings.TrimSpace(video.CoverPublicSliceKey) == "" {
			return fmt.Errorf(
				"%w: ready video requires a <=1h fast-start H.264/AAC descriptor with <=2s keyframes",
				ErrInvalidMediaAsset,
			)
		}
		if video.PreviewTrackVersion < 0 ||
			(video.PreviewTrackVersion == 0 && strings.TrimSpace(video.PreviewTrackManifestSliceKey) != "") ||
			(video.PreviewTrackVersion > 0 && strings.TrimSpace(video.PreviewTrackManifestSliceKey) == "") {
			return fmt.Errorf("%w: preview track version and manifest must be paired", ErrInvalidMediaAsset)
		}
		hlsDeclared := video.HLSCMAFDescriptorVersion != 0 ||
			strings.TrimSpace(video.HLSCMAFDescriptorSliceKey) != "" ||
			strings.TrimSpace(video.HLSCMAFMasterManifestSliceKey) != "" ||
			video.HLSCMAFRenditionCount != 0
		if hlsDeclared && (video.HLSCMAFDescriptorVersion <= 0 ||
			strings.TrimSpace(video.HLSCMAFDescriptorSliceKey) == "" ||
			strings.TrimSpace(video.HLSCMAFMasterManifestSliceKey) == "" ||
			video.HLSCMAFRenditionCount < 1 ||
			video.HLSCMAFRenditionCount > 4) {
			return fmt.Errorf("%w: HLS/CMAF descriptor, master manifest and rendition count must be complete", ErrInvalidMediaAsset)
		}
		expectedVideoSlice := runtimemedia.BuildContentMediaPublicSliceKey(
			"video",
			a.id,
			assetVersion,
			"video/mp4",
		)
		expectedPrefix := strings.TrimSuffix(expectedVideoSlice, "/source.mp4")
		if strings.TrimSpace(video.VideoPublicSliceKey) != expectedVideoSlice ||
			!strings.HasPrefix(
				strings.TrimSpace(video.CoverPublicSliceKey),
				expectedPrefix+"/cover.",
			) ||
			(video.PreviewTrackVersion > 0 &&
				strings.TrimSpace(video.PreviewTrackManifestSliceKey) !=
					expectedPrefix+"/preview/manifest.json") {
			return fmt.Errorf(
				"%w: ready video delivery slices must use canonical asset identity",
				ErrInvalidMediaAsset,
			)
		}
		if hlsDeclared && (strings.TrimSpace(video.HLSCMAFDescriptorSliceKey) != expectedPrefix+"/hls/descriptor.json" ||
			strings.TrimSpace(video.HLSCMAFMasterManifestSliceKey) != expectedPrefix+"/hls/master.m3u8") {
			return fmt.Errorf(
				"%w: HLS/CMAF delivery slices must use canonical asset identity",
				ErrInvalidMediaAsset,
			)
		}
	default:
		if descriptor != (MediaProcessingDescriptor{}) {
			return fmt.Errorf("%w: non-visual media carries a processing descriptor", ErrInvalidMediaAsset)
		}
	}
	return nil
}

func validImageDominantColor(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 7 || value[0] != '#' {
		return false
	}
	for _, character := range value[1:] {
		if !((character >= '0' && character <= '9') ||
			(character >= 'a' && character <= 'f') ||
			(character >= 'A' && character <= 'F')) {
			return false
		}
	}
	return true
}

func validImageLQIP(value string) bool {
	value = strings.TrimSpace(value)
	const prefix = "data:image/jpeg;base64,"
	if !strings.HasPrefix(value, prefix) || len(value) > MaxImageLQIPDataURIBytes {
		return false
	}
	decoded, err := base64.StdEncoding.DecodeString(strings.TrimPrefix(value, prefix))
	return err == nil && len(decoded) > 0
}

func validImageContentProfile(value string) bool {
	switch strings.TrimSpace(value) {
	case "photographic", "alpha_graphic":
		return true
	default:
		return false
	}
}

func (a *MediaAsset) ChangeAccessPolicy(ownerID string, policy AccessPolicy, now time.Time) error {
	if a == nil {
		return fmt.Errorf("%w: asset is required", ErrInvalidMediaAsset)
	}
	if strings.TrimSpace(ownerID) != a.ownerID {
		return fmt.Errorf("%w: access policy owner does not match", ErrMediaAssetOwnerForbidden)
	}
	if !validAccessPolicy(policy) {
		return fmt.Errorf("%w: access policy is invalid", ErrInvalidMediaAsset)
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.accessPolicy = policy
	return nil
}

func (a *MediaAsset) SelectAutoCover(ownerID string, now time.Time) error {
	if err := a.requireCoverOwner(ownerID); err != nil {
		return err
	}
	if a.coverStrategy == "first_frame" &&
		a.manualCoverAssetID == "" &&
		a.coverFrameTimeMs == 0 {
		return nil
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.coverStrategy = CoverStrategyFirstFrame
	a.manualCoverAssetID = ""
	a.coverFrameTimeMs = 0
	return nil
}

func (a *MediaAsset) SelectManualCover(ownerID string, coverAssetID string, frameTimeMs int64, now time.Time) error {
	if err := a.requireCoverOwner(ownerID); err != nil {
		return err
	}
	if strings.TrimSpace(coverAssetID) == "" && frameTimeMs < 0 {
		return fmt.Errorf("%w: manual cover requires a cover asset or non-negative frame", ErrInvalidMediaAsset)
	}
	coverAssetID = strings.TrimSpace(coverAssetID)
	if a.coverStrategy == "manual" &&
		a.manualCoverAssetID == coverAssetID &&
		a.coverFrameTimeMs == frameTimeMs {
		return nil
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.coverStrategy = CoverStrategyManual
	a.manualCoverAssetID = coverAssetID
	a.coverFrameTimeMs = frameTimeMs
	return nil
}

func (a *MediaAsset) requireCoverOwner(ownerID string) error {
	if a == nil {
		return fmt.Errorf("%w: asset is required", ErrInvalidMediaAsset)
	}
	if strings.TrimSpace(ownerID) != a.ownerID {
		return fmt.Errorf("%w: cover owner does not match", ErrMediaAssetOwnerForbidden)
	}
	if a.mediaType != "video" {
		return fmt.Errorf(
			"%w: cover selection requires a video asset",
			ErrInvalidMediaAsset,
		)
	}
	switch a.processingStatus {
	case ProcessingStatusReady:
		return nil
	case ProcessingStatusProcessing:
		return fmt.Errorf(
			"%w: cover selection requires completed processing",
			ErrMediaNotReady,
		)
	case ProcessingStatusRejected:
		return fmt.Errorf(
			"%w: rejected video cannot select a cover",
			ErrMediaProcessingRejected,
		)
	default:
		return fmt.Errorf(
			"%w: cover selection cannot mutate this asset",
			ErrInvalidMediaAssetTransition,
		)
	}
}

func (a *MediaAsset) Delete(ownerID string, now time.Time) error {
	if a == nil {
		return fmt.Errorf("%w: asset is required", ErrInvalidMediaAsset)
	}
	if strings.TrimSpace(ownerID) != a.ownerID {
		return fmt.Errorf("%w: delete owner does not match", ErrMediaAssetOwnerForbidden)
	}
	if a.processingStatus == ProcessingStatusDeleted {
		return fmt.Errorf("%w: deleted asset cannot be deleted again", ErrInvalidMediaAssetTransition)
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.processingStatus = ProcessingStatusDeleted
	a.processingFailureReason = ""
	return nil
}

func (a *MediaAsset) ID() string {
	if a == nil {
		return ""
	}
	return a.id
}

func (a *MediaAsset) Version() int64 {
	if a == nil {
		return 0
	}
	return a.version
}

func (a *MediaAsset) OwnerID() string {
	if a == nil {
		return ""
	}
	return a.ownerID
}

func (a *MediaAsset) SourceSessionID() string {
	if a == nil {
		return ""
	}
	return a.sourceSessionID
}

func (a *MediaAsset) ObjectKey() string {
	if a == nil {
		return ""
	}
	return a.objectKey
}

func (a *MediaAsset) SHA256() string {
	if a == nil {
		return ""
	}
	return a.sha256
}

func (a *MediaAsset) AccessPolicy() AccessPolicy {
	if a == nil {
		return ""
	}
	return a.accessPolicy
}

func (a *MediaAsset) MediaType() string {
	if a == nil {
		return ""
	}
	return string(a.mediaType)
}

func (a *MediaAsset) MimeType() string {
	if a == nil {
		return ""
	}
	return a.mimeType
}

func (a *MediaAsset) FileSize() int64 {
	if a == nil {
		return 0
	}
	return a.fileSize
}

func (a *MediaAsset) ProcessingStatus() ProcessingStatus {
	if a == nil {
		return ""
	}
	return a.processingStatus
}

func (a *MediaAsset) ProcessingFailureReason() string {
	if a == nil {
		return ""
	}
	return a.processingFailureReason
}

func (a *MediaAsset) CoverStrategy() string {
	if a == nil {
		return ""
	}
	return string(a.coverStrategy)
}

func (a *MediaAsset) ManualCoverAssetID() string {
	if a == nil {
		return ""
	}
	return a.manualCoverAssetID
}

func (a *MediaAsset) CoverFrameTimeMs() int64 {
	if a == nil {
		return 0
	}
	return a.coverFrameTimeMs
}

func (a *MediaAsset) VideoProcessingDescriptor() VideoProcessingDescriptor {
	if a == nil {
		return VideoProcessingDescriptor{}
	}
	return VideoProcessingDescriptor{
		ProcessorProfile:              a.processorProfile,
		VerifiedDurationMs:            a.verifiedDurationMs,
		VideoWidth:                    a.videoWidth,
		VideoHeight:                   a.videoHeight,
		VideoCodec:                    a.videoCodec,
		VideoContainer:                a.videoContainer,
		VideoAudioCodec:               a.videoAudioCodec,
		VideoKeyframeIntervalMs:       a.videoKeyframeIntervalMs,
		VideoFastStart:                a.videoFastStart,
		VideoPublicSliceKey:           a.videoPublicSliceKey,
		CoverPublicSliceKey:           a.coverPublicSliceKey,
		PreviewTrackVersion:           a.previewTrackVersion,
		PreviewTrackManifestSliceKey:  a.previewTrackManifestSliceKey,
		HLSCMAFDescriptorVersion:      a.hlsCMAFDescriptorVersion,
		HLSCMAFDescriptorSliceKey:     a.hlsCMAFDescriptorSliceKey,
		HLSCMAFMasterManifestSliceKey: a.hlsCMAFMasterManifestSliceKey,
		HLSCMAFRenditionCount:         a.hlsCMAFRenditionCount,
	}
}

func (a *MediaAsset) ImageProcessingDescriptor() ImageProcessingDescriptor {
	if a == nil {
		return ImageProcessingDescriptor{}
	}
	return ImageProcessingDescriptor{
		ProcessorProfile:         a.processorProfile,
		ImageWidth:               a.imageWidth,
		ImageHeight:              a.imageHeight,
		ImageDeliveryMimeType:    a.imageDeliveryMimeType,
		ImageNormalizedObjectKey: a.imageNormalizedObjectKey,
		ImagePublicSliceKey:      a.imagePublicSliceKey,
		ImageDominantColor:       a.imageDominantColor,
		ImageLQIP:                a.imageLQIP,
		ImageContentProfile:      a.imageContentProfile,
		DerivativePolicyVersion:  a.imageDerivativePolicyVersion,
	}
}

func (a *MediaAsset) ProcessingDescriptor() MediaProcessingDescriptor {
	if a == nil {
		return MediaProcessingDescriptor{}
	}
	switch a.mediaType {
	case "image":
		return MediaProcessingDescriptor{Image: a.ImageProcessingDescriptor()}
	case "video":
		return MediaProcessingDescriptor{Video: a.VideoProcessingDescriptor()}
	default:
		return MediaProcessingDescriptor{}
	}
}

func (a *MediaAsset) Snapshot() MediaAssetSnapshot {
	if a == nil {
		return MediaAssetSnapshot{}
	}
	return MediaAssetSnapshot{
		ID:                            a.id,
		Version:                       a.version,
		OwnerID:                       a.ownerID,
		SourceSessionID:               a.sourceSessionID,
		ObjectKey:                     a.objectKey,
		SHA256:                        a.sha256,
		MediaType:                     a.mediaType,
		MimeType:                      a.mimeType,
		FileSize:                      a.fileSize,
		CaptureMetadata:               normalizeCaptureMetadata(a.captureMetadata),
		AccessPolicy:                  a.accessPolicy,
		ProcessingStatus:              a.processingStatus,
		ProcessingVersion:             a.processingVersion,
		ProcessingFailureReason:       a.processingFailureReason,
		ProcessorProfile:              a.processorProfile,
		ImageWidth:                    a.imageWidth,
		ImageHeight:                   a.imageHeight,
		ImageDeliveryMimeType:         a.imageDeliveryMimeType,
		ImageNormalizedObjectKey:      a.imageNormalizedObjectKey,
		ImagePublicSliceKey:           a.imagePublicSliceKey,
		ImageDominantColor:            a.imageDominantColor,
		ImageLQIP:                     a.imageLQIP,
		ImageContentProfile:           a.imageContentProfile,
		ImageDerivativePolicyVersion:  a.imageDerivativePolicyVersion,
		ActiveImageDescriptorRevision: a.activeImageDescriptorRevision,
		ImageDescriptorRevisions:      cloneImageDescriptorRevisions(a.imageDescriptorRevisions),
		VerifiedDurationMs:            a.verifiedDurationMs,
		VideoWidth:                    a.videoWidth,
		VideoHeight:                   a.videoHeight,
		VideoCodec:                    a.videoCodec,
		VideoContainer:                a.videoContainer,
		VideoAudioCodec:               a.videoAudioCodec,
		VideoKeyframeIntervalMs:       a.videoKeyframeIntervalMs,
		VideoFastStart:                a.videoFastStart,
		VideoPublicSliceKey:           a.videoPublicSliceKey,
		CoverPublicSliceKey:           a.coverPublicSliceKey,
		PreviewTrackVersion:           a.previewTrackVersion,
		PreviewTrackManifestSliceKey:  a.previewTrackManifestSliceKey,
		HLSCMAFDescriptorVersion:      a.hlsCMAFDescriptorVersion,
		HLSCMAFDescriptorSliceKey:     a.hlsCMAFDescriptorSliceKey,
		HLSCMAFMasterManifestSliceKey: a.hlsCMAFMasterManifestSliceKey,
		HLSCMAFRenditionCount:         a.hlsCMAFRenditionCount,
		CoverStrategy:                 a.coverStrategy,
		ManualCoverAssetID:            a.manualCoverAssetID,
		CoverFrameTimeMs:              a.coverFrameTimeMs,
		CreatedAt:                     a.createdAt,
		UpdatedAt:                     a.updatedAt,
		ProcessedAt:                   cloneTime(a.processedAt),
	}
}

func cloneImageDescriptorRevisions(
	revisions []ImageDescriptorRevision,
) []ImageDescriptorRevision {
	if len(revisions) == 0 {
		return nil
	}
	cloned := make([]ImageDescriptorRevision, len(revisions))
	for index, revision := range revisions {
		cloned[index] = revision
		cloned[index].ActivatedAt = revision.ActivatedAt.UTC()
		cloned[index].CleanupCandidateAt = cloneTime(revision.CleanupCandidateAt)
	}
	return cloned
}

func (a *MediaAsset) validate() error {
	if a == nil ||
		a.id == "" ||
		a.version < 1 ||
		a.ownerID == "" ||
		a.sourceSessionID == "" ||
		a.objectKey == "" ||
		a.sha256 == "" ||
		!validMediaType(a.mediaType) ||
		a.mimeType == "" ||
		a.fileSize <= 0 ||
		(a.coverStrategy != CoverStrategyFirstFrame && a.coverStrategy != CoverStrategyManual) ||
		a.coverFrameTimeMs < 0 ||
		!validAccessPolicy(a.accessPolicy) ||
		!validProcessingStatus(a.processingStatus) ||
		a.createdAt.IsZero() ||
		a.updatedAt.IsZero() ||
		a.updatedAt.Before(a.createdAt) {
		return fmt.Errorf("%w: required state is missing", ErrInvalidMediaAsset)
	}
	if err := validateCaptureMetadata(a.captureMetadata, a.mediaType, a.createdAt); err != nil {
		return err
	}
	switch a.processingStatus {
	case ProcessingStatusProcessing:
		if a.processedAt != nil || a.processingVersion != 0 || a.processingFailureReason != "" {
			return fmt.Errorf("%w: processing asset carries final result", ErrInvalidMediaAsset)
		}
	case ProcessingStatusReady:
		if a.processedAt == nil ||
			((a.mediaType == "image" || a.mediaType == "video") && a.processingVersion <= 0) ||
			a.processingFailureReason != "" {
			return fmt.Errorf("%w: ready asset state is inconsistent", ErrInvalidMediaAsset)
		}
		if err := a.validateProcessingDescriptor(
			ProcessingStatusReady,
			a.ProcessingDescriptor(),
			a.processingVersion,
		); err != nil {
			return err
		}
		if a.mediaType == "image" {
			if err := a.validateImageDescriptorRevisions(); err != nil {
				return err
			}
		}
	case ProcessingStatusRejected:
		if a.processedAt == nil || a.processingVersion <= 0 || a.processingFailureReason == "" {
			return fmt.Errorf("%w: rejected asset state is inconsistent", ErrInvalidMediaAsset)
		}
		if err := a.validateProcessingDescriptor(
			ProcessingStatusRejected,
			MediaProcessingDescriptor{},
			a.processingVersion,
		); err != nil {
			return err
		}
	case ProcessingStatusDeleted:
		if a.processingFailureReason != "" {
			return fmt.Errorf("%w: deleted asset carries failure reason", ErrInvalidMediaAsset)
		}
	}
	return nil
}

func normalizeCaptureMetadata(value CaptureMetadata) CaptureMetadata {
	value.CameraMake = strings.TrimSpace(value.CameraMake)
	value.CameraModel = strings.TrimSpace(value.CameraModel)
	value.LensModel = strings.TrimSpace(value.LensModel)
	value.FocalLengthMM = cloneFloat64(value.FocalLengthMM)
	value.ApertureFNumber = cloneFloat64(value.ApertureFNumber)
	value.ShutterSpeedSeconds = cloneFloat64(value.ShutterSpeedSeconds)
	value.ISOSensitivity = cloneInt(value.ISOSensitivity)
	value.CapturedAt = cloneTime(value.CapturedAt)
	value.GPSLatitude = cloneFloat64(value.GPSLatitude)
	value.GPSLongitude = cloneFloat64(value.GPSLongitude)
	return value
}

func validateCaptureMetadata(value CaptureMetadata, mediaType MediaType, now time.Time) error {
	if value.IsEmpty() {
		return nil
	}
	if mediaType != MediaTypeImage {
		return fmt.Errorf("%w: capture metadata is only valid for images", ErrInvalidMediaAsset)
	}
	if len(value.CameraMake) > 128 || len(value.CameraModel) > 128 || len(value.LensModel) > 192 {
		return fmt.Errorf("%w: capture metadata text is too long", ErrInvalidMediaAsset)
	}
	if !validPositiveCaptureNumber(value.FocalLengthMM, 2000) ||
		!validPositiveCaptureNumber(value.ApertureFNumber, 128) ||
		!validPositiveCaptureNumber(value.ShutterSpeedSeconds, 86400) {
		return fmt.Errorf("%w: capture exposure parameter is out of range", ErrInvalidMediaAsset)
	}
	if value.ISOSensitivity != nil && (*value.ISOSensitivity <= 0 || *value.ISOSensitivity > 6553600) {
		return fmt.Errorf("%w: capture ISO is out of range", ErrInvalidMediaAsset)
	}
	if (value.GPSLatitude == nil) != (value.GPSLongitude == nil) {
		return fmt.Errorf("%w: capture GPS requires latitude and longitude", ErrInvalidMediaAsset)
	}
	if value.GPSLatitude != nil &&
		(!validFiniteCaptureNumber(*value.GPSLatitude) || math.Abs(*value.GPSLatitude) > 90 ||
			!validFiniteCaptureNumber(*value.GPSLongitude) || math.Abs(*value.GPSLongitude) > 180) {
		return fmt.Errorf("%w: capture GPS is out of range", ErrInvalidMediaAsset)
	}
	if value.CapturedAt != nil {
		capturedAt := value.CapturedAt.UTC()
		earliest := time.Date(1826, time.January, 1, 0, 0, 0, 0, time.UTC)
		if capturedAt.Before(earliest) || capturedAt.After(now.UTC().Add(24*time.Hour)) {
			return fmt.Errorf("%w: capture time is out of range", ErrInvalidMediaAsset)
		}
	}
	return nil
}

func validPositiveCaptureNumber(value *float64, maximum float64) bool {
	return value == nil || (validFiniteCaptureNumber(*value) && *value > 0 && *value <= maximum)
}

func validFiniteCaptureNumber(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0)
}

func cloneFloat64(value *float64) *float64 {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}

func cloneInt(value *int) *int {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}

func validMediaType(value MediaType) bool {
	switch value {
	case MediaTypeImage, MediaTypeVideo, MediaTypeAudio, MediaTypeFile:
		return true
	default:
		return false
	}
}

func (a *MediaAsset) validateImageDescriptorRevisions() error {
	if len(a.imageDescriptorRevisions) == 0 ||
		len(a.imageDescriptorRevisions) > 32 ||
		a.activeImageDescriptorRevision <= 0 {
		return fmt.Errorf("%w: ready image descriptor revision state is missing", ErrInvalidMediaAsset)
	}
	activeFound := false
	seen := make(map[int]struct{}, len(a.imageDescriptorRevisions))
	for _, revision := range a.imageDescriptorRevisions {
		if revision.Revision <= 0 || revision.ProcessingVersion <= 0 ||
			revision.PreviousRevision < 0 ||
			revision.PreviousRevision == revision.Revision ||
			revision.ActivatedAt.IsZero() {
			return fmt.Errorf("%w: image descriptor revision is invalid", ErrInvalidMediaAsset)
		}
		if _, exists := seen[revision.Revision]; exists {
			return fmt.Errorf("%w: image descriptor revision is duplicated", ErrInvalidMediaAsset)
		}
		seen[revision.Revision] = struct{}{}
		if err := a.validateProcessingDescriptor(
			ProcessingStatusReady,
			MediaProcessingDescriptor{Image: revision.Descriptor},
			revision.ProcessingVersion,
		); err != nil {
			return err
		}
		if revision.Revision == a.activeImageDescriptorRevision {
			activeFound = true
			if revision.Descriptor != a.ImageProcessingDescriptor() ||
				revision.ProcessingVersion != a.processingVersion {
				return fmt.Errorf("%w: active image descriptor revision diverges", ErrInvalidMediaAsset)
			}
		}
	}
	if !activeFound {
		return fmt.Errorf("%w: active image descriptor revision is absent", ErrInvalidMediaAsset)
	}
	return nil
}

func (a *MediaAsset) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(a.updatedAt) {
		return fmt.Errorf("%w: transition time is invalid", ErrInvalidMediaAsset)
	}
	a.version++
	a.updatedAt = now
	return nil
}

func validAccessPolicy(value AccessPolicy) bool {
	switch value {
	case AccessPolicyOwnerOnly, AccessPolicyReferencedPost, AccessPolicyPublic:
		return true
	default:
		return false
	}
}

func validProcessingStatus(value ProcessingStatus) bool {
	switch value {
	case ProcessingStatusProcessing,
		ProcessingStatusReady,
		ProcessingStatusRejected,
		ProcessingStatusDeleted:
		return true
	default:
		return false
	}
}

func normalizeDigest(value string) string {
	raw := strings.TrimPrefix(strings.ToLower(strings.TrimSpace(value)), "sha256:")
	if raw == "" {
		return ""
	}
	return "sha256:" + raw
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
