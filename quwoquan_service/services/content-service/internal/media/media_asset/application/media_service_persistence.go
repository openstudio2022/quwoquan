package media

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediaerrors "quwoquan_service/services/content-service/generated/media/media_asset"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

func (s *MediaService) replayAsset(
	ctx context.Context,
	commandName string,
	commandDigest string,
) (MediaAssetCommandResult, bool, error) {
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaAssetCommandResult{}, false, err
	}
	result, found, err := s.data.Assets.FindMediaAssetReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil {
		return MediaAssetCommandResult{}, false, unavailable(err)
	}
	if !found {
		return MediaAssetCommandResult{}, false, nil
	}
	if result.Aggregate == nil {
		return MediaAssetCommandResult{}, false, unavailable(errors.New("media asset receipt has no asset"))
	}
	return mediaAssetResult(result.Aggregate, true), true, nil
}

// recordAssetNoopReceipt 为目标状态已满足的媒体命名 set 持久化首个 no-op
// 回执；相同 key 的后续重试即使资产状态继续演进也只重放本次结果。
func (s *MediaService) recordAssetNoopReceipt(
	ctx context.Context,
	asset *mediamodel.MediaAsset,
	commandName string,
	commandDigest string,
) (MediaAssetCommandResult, error) {
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	result, err := s.data.Assets.RecordMediaAssetNoopReceipt(
		ctx,
		mediaports.MediaAssetNoopReceipt{
			Aggregate:        asset,
			IdempotencyKey:   idempotencyKey,
			CommandName:      commandName,
			CommandDigest:    commandDigest,
			ReceiptExpiresAt: s.now().UTC().Add(mediaReceiptTTL),
		},
	)
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	if result.Aggregate == nil {
		return MediaAssetCommandResult{}, unavailable(
			errors.New("media asset no-op receipt returned no asset"),
		)
	}
	return mediaAssetResult(result.Aggregate, result.Replayed), nil
}

func (s *MediaService) commitAsset(
	ctx context.Context,
	asset *mediamodel.MediaAsset,
	expectedVersion int64,
	commandName string,
	commandDigest string,
	eventType string,
	eventPayload []byte,
	now time.Time,
	options ...mediaAssetCommitOption,
) (MediaAssetCommandResult, error) {
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	eventID, err := s.newID("evt")
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	commit := mediaports.MediaAssetCommit{
		Aggregate:        asset,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.Add(mediaReceiptTTL),
		Events: []mediaports.OutboxEvent{{
			EventID:          eventID,
			EventType:        eventType,
			AggregateType:    "MediaAsset",
			AggregateID:      asset.ID(),
			AggregateVersion: asset.Version(),
			Payload:          eventPayload,
			OccurredAt:       now,
		}},
	}
	for _, option := range options {
		option(&commit)
	}
	result, err := s.data.Assets.CommitMediaAsset(ctx, commit)
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	return mediaAssetResult(result.Aggregate, result.Replayed), nil
}

type mediaAssetCommitOption func(*mediaports.MediaAssetCommit)

func withMediaAssetDiscard() mediaAssetCommitOption {
	return func(commit *mediaports.MediaAssetCommit) {
		commit.Discard = true
	}
}

func (s *MediaService) loadAsset(
	ctx context.Context,
	assetID string,
) (*mediamodel.MediaAsset, bool, error) {
	asset, found, err := s.data.Assets.LoadMediaAsset(ctx, strings.TrimSpace(assetID))
	if err != nil {
		return nil, false, unavailable(err)
	}
	return asset, found, nil
}

func mediaAssetResult(
	asset *mediamodel.MediaAsset,
	replayed bool,
) MediaAssetCommandResult {
	if asset == nil {
		return MediaAssetCommandResult{Replayed: replayed}
	}
	videoDescriptor := asset.VideoProcessingDescriptor()
	imageDescriptor := asset.ImageProcessingDescriptor()
	return MediaAssetCommandResult{
		AssetID:                      asset.ID(),
		Version:                      asset.Version(),
		ProcessingStatus:             asset.ProcessingStatus(),
		AccessPolicy:                 asset.AccessPolicy(),
		CoverStrategy:                asset.CoverStrategy(),
		ManualCoverAssetID:           asset.ManualCoverAssetID(),
		CoverFrameTimeMs:             asset.CoverFrameTimeMs(),
		ImageWidth:                   imageDescriptor.ImageWidth,
		ImageHeight:                  imageDescriptor.ImageHeight,
		ImageDeliveryMimeType:        imageDescriptor.ImageDeliveryMimeType,
		ImageDominantColor:           imageDescriptor.ImageDominantColor,
		ImageLQIP:                    imageDescriptor.ImageLQIP,
		ImageContentProfile:          imageDescriptor.ImageContentProfile,
		ImageDerivativePolicyVersion: imageDescriptor.DerivativePolicyVersion,
		VerifiedDurationMs:           videoDescriptor.VerifiedDurationMs,
		VideoWidth:                   videoDescriptor.VideoWidth,
		VideoHeight:                  videoDescriptor.VideoHeight,
		VideoCodec:                   videoDescriptor.VideoCodec,
		VideoContainer:               videoDescriptor.VideoContainer,
		VideoAudioCodec:              videoDescriptor.VideoAudioCodec,
		VideoKeyframeIntervalMs:      videoDescriptor.VideoKeyframeIntervalMs,
		VideoFastStart:               videoDescriptor.VideoFastStart,
		PreviewTrackVersion:          videoDescriptor.PreviewTrackVersion,
		HLSCMAFDescriptorVersion:     videoDescriptor.HLSCMAFDescriptorVersion,
		HLSCMAFRenditionCount:        videoDescriptor.HLSCMAFRenditionCount,
		Replayed:                     replayed,
	}
}

func requireMediaIdempotencyKey(ctx context.Context) (string, error) {
	key := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if key == "" {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"idempotencyKey 必填",
			"media command requires idempotencyKey",
		)
	}
	return key, nil
}

func mediaCommandDigest(commandName string, encoded []byte) string {
	hasher := sha256.New()
	_, _ = hasher.Write([]byte(commandName))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write(encoded)
	return hex.EncodeToString(hasher.Sum(nil))
}

func mapMediaDomainError(err error) error {
	switch {
	case errors.Is(err, mediamodel.ErrMediaAssetOwnerForbidden):
		return contentgenerated.AppErrorFromUnauthorized(err.Error())
	case errors.Is(err, mediamodel.ErrMediaNotReady):
		return mediaerrors.AppErrorFromMediaNotReady(err.Error())
	case errors.Is(err, mediamodel.ErrMediaProcessingRejected):
		return mediaerrors.AppErrorFromMediaProcessingRejected(err.Error())
	case errors.Is(err, mediamodel.ErrInvalidMediaAsset),
		errors.Is(err, mediamodel.ErrInvalidMediaAssetTransition):
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"媒体状态或参数不合法",
			err.Error(),
		)
	default:
		return err
	}
}

func mediaNotFound(identifier string) error {
	return mediaerrors.AppErrorFromMediaNotFound(
		fmt.Sprintf("media aggregate %s not found", strings.TrimSpace(identifier)),
	)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error())
}

func newMediaIdentifier(prefix string) (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return prefix + "_" + hex.EncodeToString(raw[:]), nil
}

type mediaAssetProcessingUpdatedPayload struct {
	AssetID    string                      `json:"assetId"`
	Processing mediamodel.ProcessingStatus `json:"processingStatus"`
}

type mediaAssetAccessPolicyUpdatedPayload struct {
	AssetID      string                  `json:"assetId"`
	OwnerID      string                  `json:"ownerId"`
	AccessPolicy mediamodel.AccessPolicy `json:"accessPolicy"`
}

type mediaAssetDiscardedPayload struct {
	AssetID    string                      `json:"id"`
	Version    int64                       `json:"version"`
	OwnerID    string                      `json:"ownerId"`
	ObjectKey  string                      `json:"objectKey"`
	Processing mediamodel.ProcessingStatus `json:"processingStatus"`
}
