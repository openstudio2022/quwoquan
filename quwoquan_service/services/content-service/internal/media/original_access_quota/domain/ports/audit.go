package ports

import (
	"context"
	"time"
)

// AuditDecision is the immutable outcome already decided by
// OriginalAccessQuota. The audit fact is downstream evidence only; it cannot
// affect quota state.
type AuditDecision struct {
	AssetID        string
	ViewerID       string
	Purpose        string
	Outcome        string
	Reason         string
	IdempotencyKey string
	CommandDigest  string
	DecidedAt      time.Time
	GrantExpiresAt time.Time
}

// AuditRecord is the immutable receipt returned after the decision has been
// appended to MediaOriginalAccessFact.
type AuditRecord struct {
	AuditID   string
	Outcome   string
	ExpiresAt time.Time
	Replayed  bool
}

// OriginalAccessAuditAppender appends a fact for an already-made quota
// decision. It is a downstream port of OriginalAccessQuota.
type OriginalAccessAuditAppender interface {
	AppendOriginalAccessAudit(context.Context, AuditDecision) (AuditRecord, error)
}
