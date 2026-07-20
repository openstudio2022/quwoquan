package ports

import (
	"context"
	"time"

	moderationmodel "quwoquan_service/services/content-service/internal/domain/moderation/model"
)

// OutboxEvent is an immutable moderation fact written atomically with a case
// transition, receipt, and reviewer audit record.
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	Checkpoint       string
}

type AuditAction string

const (
	AuditActionOpened     AuditAction = "opened"
	AuditActionReviewed   AuditAction = "reviewed"
	AuditActionApproved   AuditAction = "approved"
	AuditActionRejected   AuditAction = "rejected"
	AuditActionSuperseded AuditAction = "superseded"
)

type AuditEntry struct {
	CaseID         string
	CaseVersion    int64
	PostID         string
	PostVersion    int64
	ContentDigest  string
	ReviewerID     string
	Action         AuditAction
	DecisionReason string
	OccurredAt     time.Time
}

type Commit struct {
	Aggregate        *moderationmodel.PostModerationCase
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Audit            AuditEntry
	Events           []OutboxEvent
}

type CommitResult struct {
	Aggregate *moderationmodel.PostModerationCase
	Replayed  bool
}

// AggregateStore is the only write boundary for PostModerationCase.
type AggregateStore interface {
	Load(
		ctx context.Context,
		caseID string,
	) (*moderationmodel.PostModerationCase, bool, error)
	LoadByPostRevision(
		ctx context.Context,
		postID string,
		postVersion int64,
		contentDigest string,
	) (*moderationmodel.PostModerationCase, bool, error)
	FindReceipt(
		ctx context.Context,
		idempotencyKey string,
		commandName string,
		commandDigest string,
	) (CommitResult, bool, error)
	Commit(ctx context.Context, commit Commit) (CommitResult, error)
}

type PublicationEligibilityQuery struct {
	PostID        string
	PostVersion   int64
	ContentDigest string
}

type PublicationEligibility struct {
	Eligible      bool
	CaseID        string
	CaseVersion   int64
	Moderation    moderationmodel.Status
	CheckedAt     time.Time
	DecisionAt    *time.Time
	FailureReason string
}

// PublicationEligibilityReader is the final Post lifecycle integration seam.
// It is deliberately read-only and returns false for missing, stale, pending,
// reviewed, rejected, or superseded cases.
type PublicationEligibilityReader interface {
	GetPublicationEligibility(
		ctx context.Context,
		query PublicationEligibilityQuery,
	) (PublicationEligibility, error)
}

// OutboxReader serves only moderation relay workers.
type OutboxReader interface {
	ReadModerationOutboxAfter(
		ctx context.Context,
		checkpoint string,
		limit int,
	) ([]OutboxEvent, error)
}

// ProjectionCheckpointStore tracks per-consumer moderation relay progress.
type ProjectionCheckpointStore interface {
	LoadModerationCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveModerationCheckpoint(ctx context.Context, consumer, checkpoint string) error
}

// OutboxPublisher delivers committed moderation facts to one consumer.
type OutboxPublisher interface {
	Publish(ctx context.Context, event OutboxEvent) error
}
