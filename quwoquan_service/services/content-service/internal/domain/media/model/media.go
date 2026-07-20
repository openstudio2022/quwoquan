package model

import (
	"errors"
	"fmt"
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
)

var (
	ErrInvalidMediaAsset           = errors.New("invalid media asset")
	ErrInvalidMediaAssetTransition = errors.New("invalid media asset transition")
	ErrMediaAssetOwnerForbidden    = errors.New("media asset owner forbidden")
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

// MediaAssetSnapshot is the persistence boundary for MediaAsset.
type MediaAssetSnapshot struct {
	ID                           string
	Version                      int64
	OwnerID                      string
	SourceSessionID              string
	ObjectKey                    string
	SHA256                       string
	MediaType                    string
	ContentType                  string
	FileSize                     int64
	AccessPolicy                 AccessPolicy
	ProcessingStatus             ProcessingStatus
	ProcessingFailureReason      string
	ProcessorProfile             string
	ImageWidth                   int
	ImageHeight                  int
	ImageDeliveryContentType     string
	ImageNormalizedObjectKey     string
	ImagePublicSliceKey          string
	VerifiedDurationMs           int64
	VideoWidth                   int
	VideoHeight                  int
	VideoCodec                   string
	VideoContainer               string
	VideoAudioCodec              string
	VideoKeyframeIntervalMs      int
	VideoFastStart               bool
	VideoPublicSliceKey          string
	CoverPublicSliceKey          string
	PreviewTrackVersion          int
	PreviewTrackManifestSliceKey string
	CoverStrategy                string
	ManualCoverAssetID           string
	CoverFrameTimeMs             int64
	CreatedAt                    time.Time
	UpdatedAt                    time.Time
	ProcessedAt                  *time.Time
}

// VideoProcessingDescriptor is the trusted output produced by the VOD worker.
// It is bound to a MediaAsset version by the processing-result command, never
// accepted from a publishing client, and deliberately contains slice keys rather
// than directly consumable URLs.
type VideoProcessingDescriptor struct {
	ProcessorProfile             string
	VerifiedDurationMs           int64
	VideoWidth                   int
	VideoHeight                  int
	VideoCodec                   string
	VideoContainer               string
	VideoAudioCodec              string
	VideoKeyframeIntervalMs      int
	VideoFastStart               bool
	VideoPublicSliceKey          string
	CoverPublicSliceKey          string
	PreviewTrackVersion          int
	PreviewTrackManifestSliceKey string
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
	ImageDeliveryContentType string
	ImageNormalizedObjectKey string
	ImagePublicSliceKey      string
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
	MediaType          string
	ContentType        string
	FileSize           int64
	AccessPolicy       AccessPolicy
	ProcessingRequired bool
	Now                time.Time
}

// MediaAsset is a durable, independently authorized media object. It never
// derives its owner or processing state from PostService process-local maps.
type MediaAsset struct {
	id                           string
	version                      int64
	ownerID                      string
	sourceSessionID              string
	objectKey                    string
	sha256                       string
	mediaType                    string
	contentType                  string
	fileSize                     int64
	accessPolicy                 AccessPolicy
	processingStatus             ProcessingStatus
	processingFailureReason      string
	processorProfile             string
	imageWidth                   int
	imageHeight                  int
	imageDeliveryContentType     string
	imageNormalizedObjectKey     string
	imagePublicSliceKey          string
	verifiedDurationMs           int64
	videoWidth                   int
	videoHeight                  int
	videoCodec                   string
	videoContainer               string
	videoAudioCodec              string
	videoKeyframeIntervalMs      int
	videoFastStart               bool
	videoPublicSliceKey          string
	coverPublicSliceKey          string
	previewTrackVersion          int
	previewTrackManifestSliceKey string
	coverStrategy                string
	manualCoverAssetID           string
	coverFrameTimeMs             int64
	createdAt                    time.Time
	updatedAt                    time.Time
	processedAt                  *time.Time
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
		mediaType:        strings.TrimSpace(params.MediaType),
		contentType:      strings.TrimSpace(params.ContentType),
		fileSize:         params.FileSize,
		accessPolicy:     params.AccessPolicy,
		processingStatus: ProcessingStatusReady,
		coverStrategy:    "first_frame",
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
		id:                           strings.TrimSpace(snapshot.ID),
		version:                      snapshot.Version,
		ownerID:                      strings.TrimSpace(snapshot.OwnerID),
		sourceSessionID:              strings.TrimSpace(snapshot.SourceSessionID),
		objectKey:                    strings.TrimSpace(snapshot.ObjectKey),
		sha256:                       normalizeDigest(snapshot.SHA256),
		mediaType:                    strings.TrimSpace(snapshot.MediaType),
		contentType:                  strings.TrimSpace(snapshot.ContentType),
		fileSize:                     snapshot.FileSize,
		accessPolicy:                 snapshot.AccessPolicy,
		processingStatus:             snapshot.ProcessingStatus,
		processingFailureReason:      strings.TrimSpace(snapshot.ProcessingFailureReason),
		processorProfile:             strings.TrimSpace(snapshot.ProcessorProfile),
		imageWidth:                   snapshot.ImageWidth,
		imageHeight:                  snapshot.ImageHeight,
		imageDeliveryContentType:     strings.TrimSpace(snapshot.ImageDeliveryContentType),
		imageNormalizedObjectKey:     strings.TrimSpace(snapshot.ImageNormalizedObjectKey),
		imagePublicSliceKey:          strings.TrimSpace(snapshot.ImagePublicSliceKey),
		verifiedDurationMs:           snapshot.VerifiedDurationMs,
		videoWidth:                   snapshot.VideoWidth,
		videoHeight:                  snapshot.VideoHeight,
		videoCodec:                   strings.TrimSpace(snapshot.VideoCodec),
		videoContainer:               strings.TrimSpace(snapshot.VideoContainer),
		videoAudioCodec:              strings.TrimSpace(snapshot.VideoAudioCodec),
		videoKeyframeIntervalMs:      snapshot.VideoKeyframeIntervalMs,
		videoFastStart:               snapshot.VideoFastStart,
		videoPublicSliceKey:          strings.TrimSpace(snapshot.VideoPublicSliceKey),
		coverPublicSliceKey:          strings.TrimSpace(snapshot.CoverPublicSliceKey),
		previewTrackVersion:          snapshot.PreviewTrackVersion,
		previewTrackManifestSliceKey: strings.TrimSpace(snapshot.PreviewTrackManifestSliceKey),
		coverStrategy:                strings.TrimSpace(snapshot.CoverStrategy),
		manualCoverAssetID:           strings.TrimSpace(snapshot.ManualCoverAssetID),
		coverFrameTimeMs:             snapshot.CoverFrameTimeMs,
		createdAt:                    snapshot.CreatedAt.UTC(),
		updatedAt:                    snapshot.UpdatedAt.UTC(),
		processedAt:                  cloneTime(snapshot.ProcessedAt),
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
	// 处理产物 slice 绑定本次状态迁移后的聚合版本；worker 同样以
	// current version + 1 构造 key。先校验再 advance 时必须显式传目标版本，
	// 否则合法的 v2 产物会被错误地按当前 v1 拒绝。
	if err := a.validateProcessingDescriptor(status, descriptor, a.version+1); err != nil {
		return err
	}
	if err := a.advance(now); err != nil {
		return err
	}
	processedAt := a.updatedAt
	a.processingStatus = status
	a.processingFailureReason = strings.TrimSpace(failureReason)
	if status == ProcessingStatusReady {
		switch a.mediaType {
		case "image":
			a.processorProfile = strings.TrimSpace(descriptor.Image.ProcessorProfile)
			a.imageWidth = descriptor.Image.ImageWidth
			a.imageHeight = descriptor.Image.ImageHeight
			a.imageDeliveryContentType = strings.TrimSpace(descriptor.Image.ImageDeliveryContentType)
			a.imageNormalizedObjectKey = strings.TrimSpace(descriptor.Image.ImageNormalizedObjectKey)
			a.imagePublicSliceKey = strings.TrimSpace(descriptor.Image.ImagePublicSliceKey)
		case "video":
			a.processorProfile = strings.TrimSpace(descriptor.Video.ProcessorProfile)
			a.verifiedDurationMs = descriptor.Video.VerifiedDurationMs
			a.videoWidth = descriptor.Video.VideoWidth
			a.videoHeight = descriptor.Video.VideoHeight
			a.videoCodec = strings.TrimSpace(descriptor.Video.VideoCodec)
			a.videoContainer = strings.TrimSpace(descriptor.Video.VideoContainer)
			a.videoAudioCodec = strings.TrimSpace(descriptor.Video.VideoAudioCodec)
			a.videoKeyframeIntervalMs = descriptor.Video.VideoKeyframeIntervalMs
			a.videoFastStart = descriptor.Video.VideoFastStart
			a.videoPublicSliceKey = strings.TrimSpace(descriptor.Video.VideoPublicSliceKey)
			a.coverPublicSliceKey = strings.TrimSpace(descriptor.Video.CoverPublicSliceKey)
			a.previewTrackVersion = descriptor.Video.PreviewTrackVersion
			a.previewTrackManifestSliceKey = strings.TrimSpace(descriptor.Video.PreviewTrackManifestSliceKey)
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
			(strings.TrimSpace(image.ImageDeliveryContentType) != "image/jpeg" &&
				strings.TrimSpace(image.ImageDeliveryContentType) != "image/png") ||
			strings.TrimSpace(image.ImageNormalizedObjectKey) == "" ||
			strings.TrimSpace(image.ImagePublicSliceKey) == "" {
			return fmt.Errorf(
				"%w: ready image requires a bounded normalized JPEG/PNG descriptor",
				ErrInvalidMediaAsset,
			)
		}
		expectedPublicSlice := runtimemedia.BuildContentMediaPublicSliceKey(
			"image",
			a.id,
			assetVersion,
			image.ImageDeliveryContentType,
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
			!strings.EqualFold(strings.TrimSpace(video.VideoCodec), "h264") ||
			!strings.EqualFold(strings.TrimSpace(video.VideoContainer), "mp4") ||
			!strings.EqualFold(strings.TrimSpace(video.VideoAudioCodec), "aac") ||
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
	default:
		if descriptor != (MediaProcessingDescriptor{}) {
			return fmt.Errorf("%w: non-visual media carries a processing descriptor", ErrInvalidMediaAsset)
		}
	}
	return nil
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
	if err := a.advance(now); err != nil {
		return err
	}
	a.coverStrategy = "first_frame"
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
	if err := a.advance(now); err != nil {
		return err
	}
	a.coverStrategy = "manual"
	a.manualCoverAssetID = strings.TrimSpace(coverAssetID)
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
	if a.mediaType != "video" || a.processingStatus != ProcessingStatusReady {
		return fmt.Errorf("%w: cover selection requires a ready video asset", ErrInvalidMediaAssetTransition)
	}
	return nil
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
	return a.mediaType
}

func (a *MediaAsset) ContentType() string {
	if a == nil {
		return ""
	}
	return a.contentType
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
	return a.coverStrategy
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
		ProcessorProfile:             a.processorProfile,
		VerifiedDurationMs:           a.verifiedDurationMs,
		VideoWidth:                   a.videoWidth,
		VideoHeight:                  a.videoHeight,
		VideoCodec:                   a.videoCodec,
		VideoContainer:               a.videoContainer,
		VideoAudioCodec:              a.videoAudioCodec,
		VideoKeyframeIntervalMs:      a.videoKeyframeIntervalMs,
		VideoFastStart:               a.videoFastStart,
		VideoPublicSliceKey:          a.videoPublicSliceKey,
		CoverPublicSliceKey:          a.coverPublicSliceKey,
		PreviewTrackVersion:          a.previewTrackVersion,
		PreviewTrackManifestSliceKey: a.previewTrackManifestSliceKey,
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
		ImageDeliveryContentType: a.imageDeliveryContentType,
		ImageNormalizedObjectKey: a.imageNormalizedObjectKey,
		ImagePublicSliceKey:      a.imagePublicSliceKey,
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
		ID:                           a.id,
		Version:                      a.version,
		OwnerID:                      a.ownerID,
		SourceSessionID:              a.sourceSessionID,
		ObjectKey:                    a.objectKey,
		SHA256:                       a.sha256,
		MediaType:                    a.mediaType,
		ContentType:                  a.contentType,
		FileSize:                     a.fileSize,
		AccessPolicy:                 a.accessPolicy,
		ProcessingStatus:             a.processingStatus,
		ProcessingFailureReason:      a.processingFailureReason,
		ProcessorProfile:             a.processorProfile,
		ImageWidth:                   a.imageWidth,
		ImageHeight:                  a.imageHeight,
		ImageDeliveryContentType:     a.imageDeliveryContentType,
		ImageNormalizedObjectKey:     a.imageNormalizedObjectKey,
		ImagePublicSliceKey:          a.imagePublicSliceKey,
		VerifiedDurationMs:           a.verifiedDurationMs,
		VideoWidth:                   a.videoWidth,
		VideoHeight:                  a.videoHeight,
		VideoCodec:                   a.videoCodec,
		VideoContainer:               a.videoContainer,
		VideoAudioCodec:              a.videoAudioCodec,
		VideoKeyframeIntervalMs:      a.videoKeyframeIntervalMs,
		VideoFastStart:               a.videoFastStart,
		VideoPublicSliceKey:          a.videoPublicSliceKey,
		CoverPublicSliceKey:          a.coverPublicSliceKey,
		PreviewTrackVersion:          a.previewTrackVersion,
		PreviewTrackManifestSliceKey: a.previewTrackManifestSliceKey,
		CoverStrategy:                a.coverStrategy,
		ManualCoverAssetID:           a.manualCoverAssetID,
		CoverFrameTimeMs:             a.coverFrameTimeMs,
		CreatedAt:                    a.createdAt,
		UpdatedAt:                    a.updatedAt,
		ProcessedAt:                  cloneTime(a.processedAt),
	}
}

func (a *MediaAsset) validate() error {
	if a == nil ||
		a.id == "" ||
		a.version < 1 ||
		a.ownerID == "" ||
		a.sourceSessionID == "" ||
		a.objectKey == "" ||
		a.sha256 == "" ||
		a.mediaType == "" ||
		a.contentType == "" ||
		a.fileSize <= 0 ||
		(a.coverStrategy != "first_frame" && a.coverStrategy != "manual") ||
		a.coverFrameTimeMs < 0 ||
		!validAccessPolicy(a.accessPolicy) ||
		!validProcessingStatus(a.processingStatus) ||
		a.createdAt.IsZero() ||
		a.updatedAt.IsZero() ||
		a.updatedAt.Before(a.createdAt) {
		return fmt.Errorf("%w: required state is missing", ErrInvalidMediaAsset)
	}
	switch a.processingStatus {
	case ProcessingStatusProcessing:
		if a.processedAt != nil || a.processingFailureReason != "" {
			return fmt.Errorf("%w: processing asset carries final result", ErrInvalidMediaAsset)
		}
	case ProcessingStatusReady:
		if a.processedAt == nil || a.processingFailureReason != "" {
			return fmt.Errorf("%w: ready asset state is inconsistent", ErrInvalidMediaAsset)
		}
		if err := a.validateProcessingDescriptor(
			ProcessingStatusReady,
			a.ProcessingDescriptor(),
			a.version,
		); err != nil {
			return err
		}
	case ProcessingStatusRejected:
		if a.processedAt == nil || a.processingFailureReason == "" {
			return fmt.Errorf("%w: rejected asset state is inconsistent", ErrInvalidMediaAsset)
		}
		if err := a.validateProcessingDescriptor(
			ProcessingStatusRejected,
			MediaProcessingDescriptor{},
			a.version,
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
