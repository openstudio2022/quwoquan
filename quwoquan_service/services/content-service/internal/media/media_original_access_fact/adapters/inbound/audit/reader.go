package audit

import (
	"context"

	auditapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
)

// Reader is the composition-facing typed internal port for reading one
// immutable audit fact back into the OriginalAccessQuota query facade.
type Reader struct {
	service *auditapp.QueryService
}

func NewReader(service *auditapp.QueryService) *Reader {
	if service == nil {
		panic("MediaOriginalAccessFact audit reader adapter requires query service")
	}
	return &Reader{service: service}
}

func (reader *Reader) FindOriginalAccessAudit(
	ctx context.Context,
	auditID string,
) (quotaports.AuditFact, bool, error) {
	fact, found, err := reader.service.FindAudit(ctx, auditID)
	if err != nil || !found {
		return quotaports.AuditFact{}, false, err
	}
	return quotaports.AuditFact{
		AuditID:   fact.AuditID,
		AssetID:   fact.AssetID,
		ViewerID:  fact.ViewerID,
		Purpose:   fact.Purpose,
		Outcome:   fact.Outcome,
		DecidedAt: fact.DecidedAt,
		ExpiresAt: fact.ExpiresAt,
	}, true, nil
}
