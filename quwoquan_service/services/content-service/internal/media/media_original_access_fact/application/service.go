package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	mediaasseterrors "quwoquan_service/services/content-service/generated/media/media_asset"
	originalaccesserrors "quwoquan_service/services/content-service/generated/media/media_original_access_fact"
	"quwoquan_service/runtime/commandmeta"
	mediaassetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
	originalaccessports "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/ports"
)

type Command struct {
	AssetID  string
	ViewerID string
	Purpose  string
}

type Result struct {
	AssetID     string    `json:"mediaId"`
	Status      string    `json:"status"`
	OriginalURL string    `json:"originalUrl"`
	MimeType    string    `json:"format"`
	FileSize    int64     `json:"sizeBytes"`
	ExpiresAt   time.Time `json:"expiresAt"`
	TTLSeconds  int       `json:"ttlSeconds"`
	AuditID     string    `json:"auditId"`
}

type PostVisibilityReader interface {
	CanViewerAccessPublishedMedia(context.Context, string, string) (bool, error)
}

type DeliveryURLSigner interface {
	DeliveryURLUntil(context.Context, string, time.Time) (string, error)
}

type Service struct {
	store      originalaccessports.Store
	assets     mediaassetports.OriginalAccessReader
	visibility PostVisibilityReader
	urls       DeliveryURLSigner
	now        func() time.Time
}

type Option func(*Service)

func WithClock(now func() time.Time) Option {
	return func(service *Service) {
		if now != nil {
			service.now = now
		}
	}
}

func NewService(
	store originalaccessports.Store,
	assets mediaassetports.OriginalAccessReader,
	visibility PostVisibilityReader,
	urls DeliveryURLSigner,
	options ...Option,
) *Service {
	if store == nil || assets == nil || visibility == nil || urls == nil {
		panic("MediaOriginalAccessFact service requires store, asset reader, visibility reader and URL signer")
	}
	service := &Service{
		store: store, assets: assets, visibility: visibility, urls: urls, now: time.Now,
	}
	for _, option := range options {
		option(service)
	}
	return service
}

func (service *Service) Request(ctx context.Context, command Command) (Result, error) {
	purpose := strings.ToLower(strings.TrimSpace(command.Purpose))
	if purpose == "" {
		purpose = "view"
	}
	if purpose != "view" && purpose != "save" {
		return Result{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"purpose 仅支持 view/save",
			"original media access purpose must be view or save",
		)
	}
	encoded, err := json.Marshal(command)
	if err != nil {
		return Result{}, unavailable(err)
	}
	commandDigest := digestCommand("RequestOriginalImageAccess", encoded)
	idempotencyKey := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if idempotencyKey == "" {
		return Result{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"idempotencyKey 必填",
			"media original access command requires idempotencyKey",
		)
	}
	viewerID := strings.TrimSpace(command.ViewerID)
	if viewerID == "" {
		return Result{}, originalaccesserrors.AppErrorFromOriginalAccessDenied(
			"original media access requires an authenticated viewer",
		)
	}
	asset, found, err := service.assets.FindOriginalAccessAsset(ctx, strings.TrimSpace(command.AssetID))
	if err != nil {
		return Result{}, unavailable(err)
	}
	if !found {
		return Result{}, mediaasseterrors.AppErrorFromMediaNotFound(
			fmt.Sprintf("media aggregate %s not found", strings.TrimSpace(command.AssetID)),
		)
	}
	now := service.now().UTC().Truncate(time.Millisecond)
	appendDecision := func(outcome string, reason string) (originalaccessports.AppendResult, error) {
		auditDigest := sha256.Sum256([]byte(strings.Join([]string{
			idempotencyKey, asset.AssetID, viewerID, purpose, outcome, reason,
		}, ":")))
		fact := originalaccessmodel.Fact{
			AuditID: "moa_" + hex.EncodeToString(auditDigest[:16]), AssetID: asset.AssetID,
			ViewerID: viewerID, Purpose: purpose, Outcome: outcome, Reason: reason,
			IdempotencyKey: idempotencyKey, GrantedAt: now,
		}
		if outcome == "granted" {
			fact.ExpiresAt = now.Add(time.Duration(
				originalaccesserrors.ContentMediaOriginalAccessGrantTTLSeconds,
			) * time.Second)
		}
		request := originalaccessports.AppendRequest{Fact: fact, CommandDigest: commandDigest}
		if outcome == "granted" {
			request.RateLimit = originalaccessports.RateLimit{
				MaxGrants: originalaccesserrors.ContentMediaOriginalAccessRateLimitMaxGrants,
				Window: time.Duration(
					originalaccesserrors.ContentMediaOriginalAccessRateLimitWindowSeconds,
				) * time.Second,
			}
		}
		return service.store.Append(ctx, request)
	}
	deny := func(reason string, debugMessage string) (Result, error) {
		if _, appendErr := appendDecision("denied", reason); appendErr != nil {
			return Result{}, unavailable(appendErr)
		}
		return Result{}, originalaccesserrors.AppErrorFromOriginalAccessDenied(debugMessage)
	}
	if asset.ProcessingStatus != "ready" || asset.MediaType != "image" {
		return deny("asset_not_ready", "original media access requires a ready image asset")
	}
	if asset.AccessPolicy == "owner_only" && asset.OwnerID != viewerID {
		return deny("asset_policy", "original media access owner-only policy denied viewer")
	}
	visible, err := service.visibility.CanViewerAccessPublishedMedia(ctx, asset.AssetID, viewerID)
	if err != nil {
		return Result{}, unavailable(err)
	}
	if !visible {
		return deny("post_visibility", "no viewer-visible published Post references the media asset")
	}
	appended, err := appendDecision("granted", "authorized")
	if err != nil {
		var appError *rterr.AppError
		if errors.As(err, &appError) &&
			appError.Code.String() == originalaccesserrors.AppErrorFromOriginalAccessRateLimited("").Code.String() {
			if _, auditErr := appendDecision("rate_limited", "rate_limit_exhausted"); auditErr != nil {
				return Result{}, unavailable(auditErr)
			}
			return Result{}, appError
		}
		return Result{}, unavailable(err)
	}
	if appended.Fact.Outcome == "rate_limited" {
		return Result{}, originalaccesserrors.AppErrorFromOriginalAccessRateLimited(
			"media original access rate limit exhausted",
		)
	}
	if appended.Fact.Outcome != "granted" {
		return Result{}, originalaccesserrors.AppErrorFromOriginalAccessDenied(
			"original media access replay did not produce a grant",
		)
	}
	originalURL, err := service.urls.DeliveryURLUntil(ctx, asset.ObjectKey, appended.Fact.ExpiresAt)
	if err != nil {
		return Result{}, unavailable(err)
	}
	return Result{
		AssetID: asset.AssetID, Status: "granted", OriginalURL: originalURL,
		MimeType: asset.MimeType, FileSize: asset.FileSize, ExpiresAt: appended.Fact.ExpiresAt,
		TTLSeconds: originalaccesserrors.ContentMediaOriginalAccessGrantTTLSeconds,
		AuditID:    appended.Fact.AuditID,
	}, nil
}

func digestCommand(name string, encoded []byte) string {
	hasher := sha256.New()
	_, _ = hasher.Write([]byte(name))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write(encoded)
	return hex.EncodeToString(hasher.Sum(nil))
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return rterr.NewUnavailable(rterr.ModuleContent, "媒体服务暂时不可用", err.Error())
}
