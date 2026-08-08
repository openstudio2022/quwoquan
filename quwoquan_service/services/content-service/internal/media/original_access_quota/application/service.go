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

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	mediaasseterrors "quwoquan_service/services/content-service/generated/media/media_asset"
	quotagenerated "quwoquan_service/services/content-service/generated/media/original_access_quota"
	mediaassetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	auditapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	quotamodel "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/model"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
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

// Service is the OriginalAccessQuotaFacade: it enforces the media access
// policy, holds the per-window grant quota invariant and only then asks the
// audit port to record the outcome.
type Service struct {
	quotas     quotaports.Store
	audits     quotaports.OriginalAccessAuditAppender
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
	quotas quotaports.Store,
	audits quotaports.OriginalAccessAuditAppender,
	assets mediaassetports.OriginalAccessReader,
	visibility PostVisibilityReader,
	urls DeliveryURLSigner,
	options ...Option,
) *Service {
	if quotas == nil || audits == nil || assets == nil || visibility == nil || urls == nil {
		panic("OriginalAccessQuota service requires quota store, audit port, asset reader, visibility reader and URL signer")
	}
	service := &Service{
		quotas: quotas, audits: audits, assets: assets,
		visibility: visibility, urls: urls, now: time.Now,
	}
	for _, option := range options {
		option(service)
	}
	return service
}

func policy() quotamodel.Policy {
	return quotamodel.Policy{
		MaxGrants: quotagenerated.ContentMediaOriginalAccessRateLimitMaxGrants,
		Window: time.Duration(
			quotagenerated.ContentMediaOriginalAccessRateLimitWindowSeconds,
		) * time.Second,
		GrantTTL: time.Duration(
			quotagenerated.ContentMediaOriginalAccessGrantTTLSeconds,
		) * time.Second,
	}
}

func (service *Service) Reserve(ctx context.Context, command Command) (Result, error) {
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
		return Result{}, auditapp.Unavailable(err)
	}
	commandDigest := digestCommand("ReserveOriginalImageAccessGrant", encoded)
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
		return Result{}, quotagenerated.AppErrorFromOriginalAccessDenied(
			"original media access requires an authenticated viewer",
		)
	}
	asset, found, err := service.assets.FindOriginalAccessAsset(ctx, strings.TrimSpace(command.AssetID))
	if err != nil {
		return Result{}, auditapp.Unavailable(err)
	}
	if !found {
		return Result{}, mediaasseterrors.AppErrorFromMediaNotFound(
			fmt.Sprintf("media aggregate %s not found", strings.TrimSpace(command.AssetID)),
		)
	}
	now := service.now().UTC().Truncate(time.Millisecond)
	audit := func(outcome string, reason string, grantExpiresAt time.Time) (quotaports.AuditRecord, error) {
		return service.audits.AppendOriginalAccessAudit(ctx, quotaports.AuditDecision{
			AssetID: asset.AssetID, ViewerID: viewerID, Purpose: purpose,
			Outcome: outcome, Reason: reason, IdempotencyKey: idempotencyKey,
			CommandDigest: commandDigest, DecidedAt: now, GrantExpiresAt: grantExpiresAt,
		})
	}
	deny := func(reason string, debugMessage string) (Result, error) {
		if _, auditErr := audit("denied", reason, time.Time{}); auditErr != nil {
			return Result{}, auditErr
		}
		return Result{}, quotagenerated.AppErrorFromOriginalAccessDenied(debugMessage)
	}
	if asset.ProcessingStatus != "ready" || asset.MediaType != "image" {
		return deny("asset_not_ready", "original media access requires a ready image asset")
	}
	if asset.AccessPolicy == "owner_only" && asset.OwnerID != viewerID {
		return deny("asset_policy", "original media access owner-only policy denied viewer")
	}
	visible, err := service.visibility.CanViewerAccessPublishedMedia(ctx, asset.AssetID, viewerID)
	if err != nil {
		return Result{}, auditapp.Unavailable(err)
	}
	if !visible {
		return deny("post_visibility", "no viewer-visible published Post references the media asset")
	}
	requested, err := quotamodel.NewReservation(
		idempotencyKey, commandDigest, viewerID, asset.AssetID, purpose, now, policy(),
	)
	if err != nil {
		return Result{}, auditapp.Unavailable(err)
	}
	reserved, err := service.quotas.Reserve(ctx, requested, policy())
	if err != nil {
		var appError *rterr.AppError
		if errors.As(err, &appError) &&
			appError.Code.String() == quotagenerated.AppErrorFromOriginalAccessRateLimited("").Code.String() {
			if _, auditErr := audit("rate_limited", "rate_limit_exhausted", time.Time{}); auditErr != nil {
				return Result{}, auditErr
			}
			return Result{}, appError
		}
		return Result{}, auditapp.Unavailable(err)
	}
	record, err := audit("granted", "authorized", reserved.Reservation.GrantExpiresAt)
	if err != nil {
		return Result{}, err
	}
	if record.Outcome != "granted" {
		return Result{}, quotagenerated.AppErrorFromOriginalAccessDenied(
			"original media access replay did not produce a grant",
		)
	}
	originalURL, err := service.urls.DeliveryURLUntil(ctx, asset.ObjectKey, record.ExpiresAt)
	if err != nil {
		return Result{}, auditapp.Unavailable(err)
	}
	return Result{
		AssetID: asset.AssetID, Status: "granted", OriginalURL: originalURL,
		MimeType: asset.MimeType, FileSize: asset.FileSize, ExpiresAt: record.ExpiresAt,
		TTLSeconds: quotagenerated.ContentMediaOriginalAccessGrantTTLSeconds,
		AuditID:    record.AuditID,
	}, nil
}

func digestCommand(name string, encoded []byte) string {
	hasher := sha256.New()
	_, _ = hasher.Write([]byte(name))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write(encoded)
	return hex.EncodeToString(hasher.Sum(nil))
}
