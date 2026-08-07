package audit

import (
	"context"

	auditapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
)

// Appender is the composition-facing typed internal port for appending one
// audit fact after OriginalAccessQuota has made an access decision.
type Appender struct {
	service *auditapp.Service
}

func NewAppender(service *auditapp.Service) *Appender {
	if service == nil {
		panic("MediaOriginalAccessFact audit adapter requires service")
	}
	return &Appender{service: service}
}

func (appender *Appender) AppendOriginalAccessAudit(
	ctx context.Context,
	decision quotaports.AuditDecision,
) (quotaports.AuditRecord, error) {
	record, err := appender.service.AppendAudit(ctx, auditapp.Decision{
		AssetID:        decision.AssetID,
		ViewerID:       decision.ViewerID,
		Purpose:        decision.Purpose,
		Outcome:        decision.Outcome,
		Reason:         decision.Reason,
		IdempotencyKey: decision.IdempotencyKey,
		CommandDigest:  decision.CommandDigest,
		DecidedAt:      decision.DecidedAt,
		GrantExpiresAt: decision.GrantExpiresAt,
	})
	if err != nil {
		return quotaports.AuditRecord{}, err
	}
	return quotaports.AuditRecord{
		AuditID:   record.AuditID,
		Outcome:   record.Outcome,
		ExpiresAt: record.ExpiresAt,
		Replayed:  record.Replayed,
	}, nil
}
