package ports

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
)

var ErrOutboxClaimLost = errors.New("profile update proposal outbox claim lost")

type ChangeSet struct {
	Proposal       model.ProfileUpdateProposal
	Events         []model.Event
	Audit          *model.AuditRecord
	IdempotencyKey string
	CommandDigest  string
}

type CommitReceipt struct {
	ProposalID string `json:"proposalId"`
	Version    int64  `json:"version"`
	Status     string `json:"status"`
	Replayed   bool   `json:"replayed"`
}

type AggregateStore interface {
	Load(context.Context, string) (model.ProfileUpdateProposal, error)
	LoadAudit(context.Context, string, model.AuditAction) (model.AuditRecord, error)
	Replay(context.Context, string, string, string) (CommitReceipt, bool, error)
	RecordNoopReceipt(
		context.Context,
		model.ProfileUpdateProposal,
		string,
		string,
	) (CommitReceipt, error)
	Commit(context.Context, int64, ChangeSet) (CommitReceipt, error)
}

type Cursor struct {
	CreatedAt time.Time
	ID        string
}

type Slice struct {
	Items      []model.ProfileUpdateProposal
	NextCursor *Cursor
}

type Reader interface {
	Get(context.Context, string) (model.ProfileUpdateProposal, error)
	ListByPersona(context.Context, string, *Cursor, int) (Slice, error)
}

// OutboxEvent keeps the metadata-owned payload_json opaque. The relay and MQ
// adapter may add transport coordinates, but must not decode or re-encode a
// second ProfileUpdateProposal event schema.
type OutboxEvent struct {
	EventID          string
	AggregateID      string
	AggregateVersion int64
	EventType        string
	PayloadJSON      json.RawMessage
	OccurredAt       time.Time
}

// TransactionalOutbox exposes only the ordered relay checkpoint contract.
// Commands append rows through AggregateStore.Commit in the same transaction.
type TransactionalOutbox interface {
	ClaimPendingOutbox(
		context.Context,
		string,
		time.Duration,
		int,
	) ([]OutboxEvent, error)
	MarkOutboxPublished(context.Context, string, string) error
	ReleaseOutboxClaim(context.Context, string, string) error
}
