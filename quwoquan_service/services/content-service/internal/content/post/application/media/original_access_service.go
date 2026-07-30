package media

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/media/media_original_access_fact"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/content/post/domain/media/ports"
)

func (s *MediaService) RequestOriginalMediaAccess(
	ctx context.Context,
	command RequestOriginalMediaAccessCommand,
) (OriginalMediaAccessResult, error) {
	purpose := strings.ToLower(strings.TrimSpace(command.Purpose))
	if purpose == "" {
		purpose = "view"
	}
	if purpose != "view" && purpose != "save" {
		return OriginalMediaAccessResult{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"purpose 仅支持 view/save",
			"original media access purpose must be view or save",
		)
	}
	encoded, err := json.Marshal(command)
	if err != nil {
		return OriginalMediaAccessResult{}, unavailable(err)
	}
	commandDigest := mediaCommandDigest("RequestOriginalImageAccess", encoded)
	idempotencyKey, err := requireMediaIdempotencyKey(ctx)
	if err != nil {
		return OriginalMediaAccessResult{}, err
	}
	viewerID := strings.TrimSpace(command.ViewerID)
	if viewerID == "" {
		return OriginalMediaAccessResult{}, contentgenerated.AppErrorFromOriginalAccessDenied(
			"original media access requires an authenticated viewer",
		)
	}
	asset, found, err := s.data.Assets.FindMediaAssetForOriginalAccess(
		ctx,
		strings.TrimSpace(command.AssetID),
	)
	if err != nil {
		return OriginalMediaAccessResult{}, unavailable(err)
	}
	if !found {
		return OriginalMediaAccessResult{}, mediaNotFound(command.AssetID)
	}
	// MongoDB persists timestamps at millisecond precision. Normalize before
	// deriving the immutable decision fact and its optional signed grant.
	now := s.now().UTC().Truncate(time.Millisecond)
	appendDecision := func(
		outcome string,
		reason string,
	) (mediaports.MediaOriginalAccessAppendResult, error) {
		auditDigest := sha256.Sum256([]byte(strings.Join([]string{
			idempotencyKey, asset.AssetID, viewerID, purpose, outcome, reason,
		}, ":")))
		fact := mediamodel.MediaOriginalAccessFact{
			AuditID:        "moa_" + hex.EncodeToString(auditDigest[:16]),
			AssetID:        asset.AssetID,
			ViewerID:       viewerID,
			Purpose:        purpose,
			Outcome:        outcome,
			Reason:         reason,
			IdempotencyKey: idempotencyKey,
			GrantedAt:      now,
		}
		if outcome == "granted" {
			fact.ExpiresAt = now.Add(
				time.Duration(contentgenerated.ContentMediaOriginalAccessGrantTTLSeconds) *
					time.Second,
			)
		}
		request := mediaports.MediaOriginalAccessAppendRequest{
			Fact:          fact,
			CommandDigest: commandDigest,
		}
		if outcome == "granted" {
			request.RateLimit = mediaports.MediaOriginalAccessRateLimit{
				MaxGrants: contentgenerated.ContentMediaOriginalAccessRateLimitMaxGrants,
				Window: time.Duration(
					contentgenerated.ContentMediaOriginalAccessRateLimitWindowSeconds,
				) * time.Second,
			}
		}
		return s.data.OriginalAccess.AppendMediaOriginalAccess(ctx, request)
	}
	deny := func(reason string, debugMessage string) (OriginalMediaAccessResult, error) {
		if _, appendErr := appendDecision("denied", reason); appendErr != nil {
			return OriginalMediaAccessResult{}, unavailable(appendErr)
		}
		return OriginalMediaAccessResult{}, contentgenerated.AppErrorFromOriginalAccessDenied(
			debugMessage,
		)
	}
	if asset.ProcessingStatus != mediamodel.ProcessingStatusReady ||
		asset.MediaType != "image" {
		return deny(
			"asset_not_ready",
			"original media access requires a ready image asset",
		)
	}
	if asset.AccessPolicy == mediamodel.AccessPolicyOwnerOnly && asset.OwnerID != viewerID {
		return deny(
			"asset_policy",
			"original media access owner-only policy denied viewer",
		)
	}
	if s.originalAccessVisibility == nil {
		return OriginalMediaAccessResult{}, unavailable(
			errors.New("Post media visibility reader is not configured"),
		)
	}
	visible, visibilityErr := s.originalAccessVisibility.CanViewerAccessPublishedMedia(
		ctx,
		asset.AssetID,
		viewerID,
	)
	if visibilityErr != nil {
		return OriginalMediaAccessResult{}, unavailable(visibilityErr)
	}
	if !visible {
		return deny(
			"post_visibility",
			"no viewer-visible published Post references the media asset",
		)
	}
	appended, err := appendDecision("granted", "authorized")
	if err != nil {
		var appError *rterr.AppError
		if errors.As(err, &appError) &&
			appError.Code.String() ==
				contentgenerated.AppErrorFromOriginalAccessRateLimited("").Code.String() {
			if _, auditErr := appendDecision("rate_limited", "rate_limit_exhausted"); auditErr != nil {
				return OriginalMediaAccessResult{}, unavailable(auditErr)
			}
			return OriginalMediaAccessResult{}, appError
		}
		return OriginalMediaAccessResult{}, unavailable(err)
	}
	if appended.Fact.Outcome == "rate_limited" {
		return OriginalMediaAccessResult{}, contentgenerated.AppErrorFromOriginalAccessRateLimited(
			"media original access rate limit exhausted",
		)
	}
	if appended.Fact.Outcome != "granted" {
		return OriginalMediaAccessResult{}, contentgenerated.AppErrorFromOriginalAccessDenied(
			"original media access replay did not produce a grant",
		)
	}
	originalURL, err := s.objects.DeliveryURLUntil(ctx, asset.ObjectKey, appended.Fact.ExpiresAt)
	if err != nil {
		return OriginalMediaAccessResult{}, unavailable(err)
	}
	return OriginalMediaAccessResult{
		AssetID: asset.AssetID, Status: "granted", OriginalURL: originalURL,
		MimeType: asset.MimeType, FileSize: asset.FileSize,
		ExpiresAt:  appended.Fact.ExpiresAt,
		TTLSeconds: contentgenerated.ContentMediaOriginalAccessGrantTTLSeconds,
		AuditID:    appended.Fact.AuditID,
	}, nil
}
