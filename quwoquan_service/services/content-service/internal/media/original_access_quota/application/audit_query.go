package application

import (
	"context"
	"strings"
	"time"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	quotagenerated "quwoquan_service/services/content-service/generated/media/original_access_quota"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
)

// AuditView is the owner-scoped readback of one immutable original access
// audit fact (GetOriginalImageAccessAudit response body).
type AuditView struct {
	AuditID    string    `json:"auditId"`
	MediaID    string    `json:"mediaId"`
	Outcome    string    `json:"outcome"`
	TTLSeconds int       `json:"ttlSeconds"`
	ExpiresAt  time.Time `json:"expiresAt"`
}

// AuditQueryFacade is the OriginalAccessAuditQueryFacade: it only serves the
// persona that owns the audited grant decision (the research managed persona
// reads back its own audit through the same ownership rule). Missing and
// foreign audits are indistinguishable and both fail closed.
type AuditQueryFacade struct {
	audits quotaports.OriginalAccessAuditReader
}

func NewAuditQueryFacade(
	audits quotaports.OriginalAccessAuditReader,
) *AuditQueryFacade {
	if audits == nil {
		panic("OriginalAccessQuota audit query facade requires audit reader")
	}
	return &AuditQueryFacade{audits: audits}
}

func (facade *AuditQueryFacade) GetOriginalImageAccessAudit(
	ctx context.Context,
	viewerID string,
	auditID string,
) (AuditView, error) {
	viewerID = strings.TrimSpace(viewerID)
	auditID = strings.TrimSpace(auditID)
	if viewerID == "" {
		return AuditView{}, contentgenerated.AppErrorFromUnauthorized(
			"original media access audit readback requires an authenticated viewer",
		)
	}
	denied := func() (AuditView, error) {
		return AuditView{}, quotagenerated.AppErrorFromOriginalAccessDenied(
			"original media access audit is not readable by this viewer",
		)
	}
	if auditID == "" {
		return denied()
	}
	fact, found, err := facade.audits.FindOriginalAccessAudit(ctx, auditID)
	if err != nil {
		return AuditView{}, contentgenerated.AppErrorFromStorageReadFailed(
			"original media access audit readback failed",
		)
	}
	if !found || fact.ViewerID != viewerID {
		return denied()
	}
	ttlSeconds := 0
	if !fact.ExpiresAt.IsZero() && fact.ExpiresAt.After(fact.DecidedAt) {
		ttlSeconds = int(fact.ExpiresAt.Sub(fact.DecidedAt) / time.Second)
	}
	return AuditView{
		AuditID:    fact.AuditID,
		MediaID:    fact.AssetID,
		Outcome:    fact.Outcome,
		TTLSeconds: ttlSeconds,
		ExpiresAt:  fact.ExpiresAt.UTC(),
	}, nil
}
