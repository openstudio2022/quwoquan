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
	// ResearchPrincipal 由 HTTP handler 从已验签 principal 的 research role
	// 派生（DEC-031/DEC-032）：research 会话只允许 purpose=view，可为当前
	// active research release 闭包内 ready 的 avatar|image|video 资产签发。
	ResearchPrincipal bool
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

// ActiveResearchReleaseReader 只回答一个事实：当前环境是否存在 status=active
// 且 releaseClass=research 的 canonical data release，及其 releaseId。
// found=false 表示读取成功但没有 active research release（缺席，不是失败）。
type ActiveResearchReleaseReader interface {
	ActiveResearchReleaseID(ctx context.Context) (releaseID string, found bool, err error)
}

type DeliveryURLSigner interface {
	DeliveryURLUntil(context.Context, string, time.Time) (string, error)
}

// Service is the OriginalAccessQuotaFacade: it enforces the media access
// policy, holds the per-window grant quota invariant and only then asks the
// audit port to record the outcome.
type Service struct {
	quotas          quotaports.Store
	audits          quotaports.OriginalAccessAuditAppender
	assets          mediaassetports.OriginalAccessReader
	visibility      PostVisibilityReader
	urls            DeliveryURLSigner
	researchRelease ActiveResearchReleaseReader
	now             func() time.Time
}

type Option func(*Service)

func WithClock(now func() time.Time) Option {
	return func(service *Service) {
		if now != nil {
			service.now = now
		}
	}
}

// WithActiveResearchReleaseReader 接入 research principal 分流所需的 active
// research release 事实（DEC-031）。未注入时 research principal 的请求整体
// fail closed，不回退到普通会话的 Post 可见性链。
func WithActiveResearchReleaseReader(reader ActiveResearchReleaseReader) Option {
	return func(service *Service) {
		if reader != nil {
			service.researchRelease = reader
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
	if command.ResearchPrincipal {
		// DEC-031 research 分流：view-only、扩展媒体类别、以 active research
		// release membership 取代 Post 可见性（creator 头像与 homepage assets
		// 没有引用 Post）。任何一环缺失即拒绝，不回退普通会话链。
		if purpose != "view" {
			return deny("research_purpose", "research principal may only reserve purpose=view")
		}
		if asset.ProcessingStatus != "ready" {
			return deny("asset_not_ready", "original media access requires a ready asset")
		}
		if asset.MediaType != "avatar" && asset.MediaType != "image" && asset.MediaType != "video" {
			return deny("unsupported_media_type", "research original access supports avatar|image|video assets")
		}
		if asset.AccessPolicy == "owner_only" && asset.OwnerID != viewerID {
			return deny("asset_policy", "original media access owner-only policy denied viewer")
		}
		if service.researchRelease == nil {
			return deny("research_release_membership", "active research release reader is not configured")
		}
		activeReleaseID, foundActive, err := service.researchRelease.ActiveResearchReleaseID(ctx)
		if err != nil {
			return Result{}, auditapp.Unavailable(err)
		}
		if !foundActive {
			return deny("research_release_membership", "no active research release is present")
		}
		if strings.TrimSpace(asset.SourceReleaseID) == "" ||
			asset.SourceReleaseID != activeReleaseID {
			return deny("research_release_membership", "asset does not belong to the active research release closure")
		}
	} else {
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
