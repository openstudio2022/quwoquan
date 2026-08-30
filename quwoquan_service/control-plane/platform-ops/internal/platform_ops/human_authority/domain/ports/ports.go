package ports

import (
	"context"
	"time"

	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
)

type IdempotencyRecord struct {
	Operation     string
	Key           string
	RequestDigest string
	StatusCode    int
	ResponseBytes []byte
}

type OutboxRecord struct {
	EventID      string
	EventType    string
	AggregateID  string
	Payload      []byte
	OccurredAt   time.Time
	DispatchedAt *time.Time
	RetryCount   int
	LastError    string
}

type CommitPacket struct {
	Unit          model.DecisionUnit
	Events        []model.Event
	AuditAction   string
	AuditActor    string
	Receipt       *model.AuthorizationReceipt
	OutboxType    string
	OutboxPayload any
}

type Store interface {
	EnsureSchema(context.Context) error
	Load(context.Context, string) (model.DecisionUnit, error)
	Events(context.Context, string) ([]model.Event, error)
	Create(context.Context, CommitPacket) error
	Append(context.Context, int64, CommitPacket) error
	TransitionReceipt(context.Context, string, string, string, string, string, string, string, string, model.CanonicalScope, string, time.Time, string) (model.AuthorizationReceipt, error)
	List(context.Context) ([]model.DecisionUnit, error)
	Receipt(context.Context, string) (model.AuthorizationReceipt, error)
	RecordGitHub(context.Context, model.GitHubApproval) (model.GitHubApproval, bool, error)
	Idempotency(context.Context, string, string) (IdempotencyRecord, bool, error)
	SaveIdempotency(context.Context, IdempotencyRecord) error
	Outbox(context.Context, int) ([]OutboxRecord, error)
}

type Signer interface {
	KeyID() string
	PublicKey() []byte
	Sign([]byte) ([]byte, error)
	TestKey() bool
}
