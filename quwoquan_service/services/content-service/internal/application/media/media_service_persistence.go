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

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/application/commandmeta"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func (s *MediaService) replayUploadSession(
	ctx context.Context,
	commandName string,
	commandDigest string,
) (MediaUploadSessionCommandResult, bool, error) {
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaUploadSessionCommandResult{}, false, err
	}
	result, found, err := s.data.UploadSessions.FindUploadSessionReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil {
		return MediaUploadSessionCommandResult{}, false, unavailable(err)
	}
	if !found {
		return MediaUploadSessionCommandResult{}, false, nil
	}
	if result.Aggregate == nil {
		return MediaUploadSessionCommandResult{}, false, unavailable(errors.New("upload receipt has no session"))
	}
	replayed := uploadSessionResult(result.Aggregate, nil, true)
	if commandName == "InitMediaUpload" && result.Aggregate.Status() == mediamodel.UploadSessionPending {
		uploadURL, err := s.objects.UploadURL(
			ctx,
			result.Aggregate.ObjectKey(),
			result.Aggregate.ContentType(),
			result.Aggregate.ExpectedSHA256(),
			result.Aggregate.ExpiresAt(),
		)
		if err != nil {
			return MediaUploadSessionCommandResult{}, false, unavailable(err)
		}
		replayed.UploadURL = uploadURL
	}
	return replayed, true, nil
}

func (s *MediaService) replayCompleteUpload(
	ctx context.Context,
	commandName string,
	commandDigest string,
) (MediaUploadSessionCommandResult, bool, error) {
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaUploadSessionCommandResult{}, false, err
	}
	result, found, err := s.data.UploadSessions.FindCompleteUploadReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil {
		return MediaUploadSessionCommandResult{}, false, unavailable(err)
	}
	if !found {
		return MediaUploadSessionCommandResult{}, false, nil
	}
	if result.Session == nil || result.Asset == nil {
		return MediaUploadSessionCommandResult{}, false, unavailable(errors.New("complete upload receipt is incomplete"))
	}
	replayed := uploadSessionResult(result.Session, result.Asset, true)
	deliveryURL, err := s.objects.DeliveryURL(ctx, result.Asset.ObjectKey())
	if err != nil {
		return MediaUploadSessionCommandResult{}, false, unavailable(err)
	}
	replayed.DeliveryURL = deliveryURL
	return replayed, true, nil
}

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

func (s *MediaService) commitUploadSession(
	ctx context.Context,
	session *mediamodel.MediaUploadSession,
	expectedVersion int64,
	commandName string,
	commandDigest string,
	eventType string,
	eventPayload []byte,
	now time.Time,
) (MediaUploadSessionCommandResult, error) {
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaUploadSessionCommandResult{}, err
	}
	eventID, err := s.newID("evt")
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	result, err := s.data.UploadSessions.CommitUploadSession(ctx, mediaports.UploadSessionCommit{
		Aggregate:        session,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.Add(mediaReceiptTTL),
		Events: []mediaports.OutboxEvent{{
			EventID:          eventID,
			EventType:        eventType,
			AggregateType:    "MediaUploadSession",
			AggregateID:      session.ID(),
			AggregateVersion: session.Version(),
			Payload:          eventPayload,
			OccurredAt:       now,
		}},
	})
	if err != nil {
		return MediaUploadSessionCommandResult{}, unavailable(err)
	}
	return uploadSessionResult(result.Aggregate, nil, result.Replayed), nil
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
) (MediaAssetCommandResult, error) {
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return MediaAssetCommandResult{}, err
	}
	eventID, err := s.newID("evt")
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	result, err := s.data.Assets.CommitMediaAsset(ctx, mediaports.MediaAssetCommit{
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
	})
	if err != nil {
		return MediaAssetCommandResult{}, unavailable(err)
	}
	return mediaAssetResult(result.Aggregate, result.Replayed), nil
}

func (s *MediaService) loadUploadSession(
	ctx context.Context,
	sessionID string,
) (*mediamodel.MediaUploadSession, bool, error) {
	session, found, err := s.data.UploadSessions.LoadUploadSession(
		ctx,
		strings.TrimSpace(sessionID),
	)
	if err != nil {
		return nil, false, unavailable(err)
	}
	return session, found, nil
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

func uploadSessionResult(
	session *mediamodel.MediaUploadSession,
	asset *mediamodel.MediaAsset,
	replayed bool,
) MediaUploadSessionCommandResult {
	result := MediaUploadSessionCommandResult{Replayed: replayed}
	if session != nil {
		result.SessionID = session.ID()
		result.Version = session.Version()
		result.Status = session.Status()
		result.ObjectKey = session.ObjectKey()
		result.ExpiresAt = session.ExpiresAt()
	}
	if asset != nil {
		result.AssetID = asset.ID()
		result.ObjectKey = asset.ObjectKey()
	}
	return result
}

func mediaAssetResult(
	asset *mediamodel.MediaAsset,
	replayed bool,
) MediaAssetCommandResult {
	if asset == nil {
		return MediaAssetCommandResult{Replayed: replayed}
	}
	descriptor := asset.VideoProcessingDescriptor()
	return MediaAssetCommandResult{
		AssetID:             asset.ID(),
		Version:             asset.Version(),
		ProcessingStatus:    asset.ProcessingStatus(),
		AccessPolicy:        asset.AccessPolicy(),
		CoverStrategy:       asset.CoverStrategy(),
		ManualCoverAssetID:  asset.ManualCoverAssetID(),
		CoverFrameTimeMs:    asset.CoverFrameTimeMs(),
		VerifiedDurationMs:  descriptor.VerifiedDurationMs,
		VideoWidth:          descriptor.VideoWidth,
		VideoHeight:         descriptor.VideoHeight,
		VideoCodec:          descriptor.VideoCodec,
		VideoContainer:      descriptor.VideoContainer,
		PreviewTrackVersion: descriptor.PreviewTrackVersion,
		Replayed:            replayed,
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
	case errors.Is(err, mediamodel.ErrUploadSessionOwnerForbidden),
		errors.Is(err, mediamodel.ErrMediaAssetOwnerForbidden):
		return contentgenerated.AppErrorFromUnauthorized(err.Error())
	case errors.Is(err, mediamodel.ErrInvalidUploadSession),
		errors.Is(err, mediamodel.ErrInvalidUploadSessionTransition),
		errors.Is(err, mediamodel.ErrUploadSessionExpired),
		errors.Is(err, mediamodel.ErrUploadDigestMismatch),
		errors.Is(err, mediamodel.ErrInvalidMediaAsset),
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
	return contentgenerated.AppErrorFromMediaNotFound(
		fmt.Sprintf("media aggregate %s not found", strings.TrimSpace(identifier)),
	)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return rterr.NewUnavailable(
		rterr.ModuleContent,
		"媒体服务暂时不可用",
		err.Error(),
	)
}

func newMediaIdentifier(prefix string) (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return prefix + "_" + hex.EncodeToString(raw[:]), nil
}

type mediaUploadInitializedPayload struct {
	SessionID string    `json:"sessionId"`
	OwnerID   string    `json:"ownerId"`
	ObjectKey string    `json:"objectKey"`
	ExpiresAt time.Time `json:"expiresAt"`
}

type mediaUploadCompletedPayload struct {
	SessionID string `json:"sessionId"`
	OwnerID   string `json:"ownerId"`
	ObjectKey string `json:"objectKey"`
	AssetID   string `json:"assetId"`
}

type mediaUploadAbortedPayload struct {
	SessionID string `json:"sessionId"`
	OwnerID   string `json:"ownerId"`
}

type mediaAssetCreatedPayload struct {
	AssetID         string                      `json:"assetId"`
	OwnerID         string                      `json:"ownerId"`
	SourceSessionID string                      `json:"sourceSessionId"`
	ObjectKey       string                      `json:"objectKey"`
	SHA256          string                      `json:"sha256"`
	ContentType     string                      `json:"contentType"`
	FileSize        int64                       `json:"fileSize"`
	Processing      mediamodel.ProcessingStatus `json:"processingStatus"`
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

type mediaOriginalAccessGrantedPayload struct {
	AuditID   string    `json:"auditId"`
	AssetID   string    `json:"assetId"`
	ViewerID  string    `json:"viewerId"`
	Purpose   string    `json:"purpose"`
	GrantedAt time.Time `json:"grantedAt"`
	ExpiresAt time.Time `json:"expiresAt"`
}
