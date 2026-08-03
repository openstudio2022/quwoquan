package ports

import (
	"context"
	"errors"
	"time"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

var (
	ErrVersionConflict            = errors.New("Gathering version conflict")
	ErrTargetNotNavigable         = errors.New("Gathering target is not navigable")
	ErrTargetAuthorityUnavailable = errors.New("Gathering target authority is unavailable")
)

type Mutation func(*model.Gathering) (model.Gathering, error)

type CommitRequest struct {
	GatheringID      string
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	EventType        string
	Mutate           Mutation
}

type CommitReceipt struct {
	Gathering model.Gathering
	Replayed  bool
}

// AggregateStore commits aggregate, command receipt and outbox event in one
// transaction. Mutate is evaluated against the latest persisted version.
type AggregateStore interface {
	Load(context.Context, string) (model.Gathering, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
}

type ReconciliationStore interface {
	ListReconciliationCandidates(context.Context, int) ([]model.Gathering, error)
	SaveReconciliationCheckpoint(context.Context, string, int64, time.Time) error
}

// TargetReader proves the referenced object currently exists and is
// navigable. Client-supplied labels and routes never substitute this check.
type TargetReader interface {
	RequireNavigable(context.Context, model.TargetRef) error
}

// ConversationPort is the only cross-domain write seam. All methods must be
// idempotent for the supplied operation key.
type ConversationPort interface {
	EnsureGroupConversation(
		ctx context.Context,
		gatheringID string,
		title string,
		ownerPersonaID string,
		maxGroupSize int64,
		operationKey string,
	) (conversationID string, err error)
	ProjectParticipant(
		ctx context.Context,
		gatheringID string,
		ownerPersonaID string,
		personaID string,
		state string,
		sourceVersion int64,
		operationKey string,
	) error
}
