package ports

import (
	"context"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/model"
)

type CommandContext struct {
	ActorID        string
	Environment    string
	RequestID      string
	TraceID        string
	IdempotencyKey string
}

type Event struct {
	ID          string
	Type        string
	AggregateID string
	Payload     map[string]any
	OccurredAt  time.Time
}

type ChangeSet struct {
	Entry               model.Entry
	ExpectedRevision    int64
	Intent              string
	CommandDigest       string
	Context             CommandContext
	Before              *model.Entry
	Event               Event
	ApprovalDigest      string
	RequireDualApproval bool
}

type CommitReceipt struct {
	Entry          model.Entry
	Intent         string
	CommandDigest  string
	ApprovalDigest string
	IdempotencyKey string
	CommittedAt    time.Time
	Replayed       bool
}

type Approval struct {
	ContentID     string
	PayloadDigest string
	Decision      string
	ActorID       string
	Revision      int64
	ApprovedAt    time.Time
}

type Store interface {
	List(context.Context) ([]model.Entry, error)
	Load(context.Context, string) (model.Entry, bool, error)
	Replay(context.Context, string, string) (CommitReceipt, bool, error)
	Commit(context.Context, ChangeSet) (CommitReceipt, error)
	RecordApproval(context.Context, Approval) error
	ListApprovals(context.Context, string, string, string, int64) ([]Approval, error)
}
