package ports

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

var (
	ErrVersionConflict            = errors.New("Gathering version conflict")
	ErrTargetNotNavigable         = errors.New("Gathering target is not navigable")
	ErrTargetAuthorityUnavailable = errors.New("Gathering target authority is unavailable")
)

type Mutation func(*model.Gathering) (model.Gathering, error)

type CommitRequest struct {
	GatheringID          string
	ReceiptKey           string
	CommandDigest        string
	ReceiptExpiresAt     time.Time
	EventType            string
	AdditionalEventTypes []string
	Mutate               Mutation
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

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	Sequence         int64
}

// PublicationOutbox owns Gathering's durable event delivery progress. It is
// intentionally distinct from ReconciliationStore: Chat convergence is a
// downstream projection and cannot acknowledge publication.
type PublicationOutbox interface {
	ReadPublicationOutboxAfter(context.Context, int64, int) ([]OutboxEvent, error)
	LoadPublicationCheckpoint(context.Context, string) (int64, error)
	SavePublicationCheckpoint(context.Context, string, int64, time.Time) error
}

// TargetReader proves the referenced object currently exists and is
// navigable. Client-supplied labels and routes never substitute this check.
type TargetReader interface {
	RequireNavigable(context.Context, contract.GatheringSourceRef) error
}

type EnsureGatheringConversationCommand struct {
	GatheringID    string
	SourceEventID  string
	SourceVersion  int64
	OwnerPersonaID string
	Title          string
	AccessMode     string
	PostingPolicy  string
}

type ProjectGatheringMembershipCommand struct {
	GatheringID   string
	PersonaID     string
	SourceEventID string
	SourceVersion int64
	SourceType    string
	State         string
}

// ConversationPort is the only cross-domain write seam. Chat consumes
// versioned Gathering source facts and owns room/access projection.
type ConversationPort interface {
	EnsureGatheringConversation(
		ctx context.Context,
		command EnsureGatheringConversationCommand,
	) (conversationID string, err error)
	ProjectGatheringMembership(
		ctx context.Context,
		command ProjectGatheringMembershipCommand,
	) error
}
