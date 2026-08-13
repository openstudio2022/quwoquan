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

// AuditFact is the immutable identity of one already-appended audit fact as
// read back for its owning viewer. It carries the viewer binding so the
// query facade can fail closed on any cross-persona readback.
type AuditFact struct {
	AuditID   string
	AssetID   string
	ViewerID  string
	Purpose   string
	Outcome   string
	DecidedAt time.Time
	ExpiresAt time.Time
}

// OriginalAccessAuditReader finds one immutable audit fact by its identity.
// A missing fact is (zero, false, nil); errors are reserved for storage
// failures.
type OriginalAccessAuditReader interface {
	FindOriginalAccessAudit(context.Context, string) (AuditFact, bool, error)
}
