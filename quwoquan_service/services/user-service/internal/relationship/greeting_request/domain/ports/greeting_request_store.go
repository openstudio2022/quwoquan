package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
)

type GreetingRequestStore interface {
	Create(ctx context.Context, greeting *model.GreetingRequest) error
	Update(ctx context.Context, greeting *model.GreetingRequest) error
	FindByID(ctx context.Context, id string) (*model.GreetingRequest, error)
	FindPendingBetween(ctx context.Context, requesterID, targetID string) (*model.GreetingRequest, error)
	HasPendingBetween(ctx context.Context, personaA, personaB string) (bool, error)
	HasRepliedBetween(ctx context.Context, personaA, personaB string) (bool, error)
	ListInbox(ctx context.Context, targetID, status, cursor string, limit int) ([]model.GreetingRequest, string, error)
	ListOutbox(ctx context.Context, requesterID, status, cursor string, limit int) ([]model.GreetingRequest, string, error)
	MarkPendingBlockedBetween(ctx context.Context, personaA, personaB string) error
}

// GreetingCommit 是 greeting state、幂等 receipt 与 outbox 事件的单事务提交单元。
type GreetingCommit struct {
	Greeting       *model.GreetingRequest
	Insert         bool
	ActorPersonaID string
	IdempotencyKey string
	Operation      string
	EventID        string
	EventName      string
	EventPayload   map[string]any
	OccurredAt     time.Time
}

// GreetingCommandStore 补齐命令幂等与事务事件提交；实现与 GreetingRequestStore
// 同一 PostgreSQL adapter。
type GreetingCommandStore interface {
	LoadCommandReceipt(ctx context.Context, actorPersonaID, idempotencyKey, operation string) (*model.GreetingRequest, bool, error)
	CommitCommand(ctx context.Context, commit GreetingCommit) error
	CountRecentByRequester(ctx context.Context, requesterPersonaID string, window time.Duration) (int64, error)
}

var ErrGreetingOutboxClaimLost = errors.New("greeting outbox claim lost")

// GreetingOutboxEvent 是已提交的 greeting 事实。
type GreetingOutboxEvent struct {
	EventID     string
	AggregateID string
	EventName   string
	Payload     map[string]any
	OccurredAt  time.Time
}

// GreetingOutbox 供 relay checkpoint/replay 已提交的事实。
type GreetingOutbox interface {
	ClaimPendingOutbox(ctx context.Context, ownerID string, lease time.Duration, limit int) ([]GreetingOutboxEvent, error)
	MarkOutboxPublished(ctx context.Context, eventID, ownerID string) error
	ReleaseOutboxClaim(ctx context.Context, eventID, ownerID string) error
}
