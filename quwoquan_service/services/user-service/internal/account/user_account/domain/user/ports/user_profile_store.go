package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

var (
	ErrUserProfileVersionConflict     = errors.New("user profile version conflict")
	ErrUserProfileCommandMetaRequired = errors.New("user profile command metadata required")
	ErrUserProfileIdempotencyConflict = errors.New("user profile idempotency conflict")
)

type UserProfileStore interface {
	FindByID(ctx context.Context, userID string) (*model.UserProfile, error)
	FindByNickname(ctx context.Context, nickname string) (*model.UserProfile, error)
	SearchProfiles(ctx context.Context, query string, limit int) ([]model.UserProfile, error)
	Create(ctx context.Context, profile *model.UserProfile) error
	Update(ctx context.Context, profile *model.UserProfile) error
	IncrementCounter(ctx context.Context, userID, field string, delta int64) error
}

type UserProfileTagProjection struct {
	EventID           string
	UserID            string
	TagRefs           []string
	TaxonomyReleaseID string
	ProfileVersion    int64
	OccurredAt        time.Time
}

// UserProfileSearchProjection is a durable, payload-free coordinate for the
// authoritative profile to be reconciled into the shared search index.
type UserProfileSearchProjection struct {
	UserID         string
	ProfileVersion int64
	EventType      string
	OccurredAt     time.Time
}

type UserProfileCommandMeta struct {
	IdempotencyKey string
	CommandDigest  string
}

type UserProfileCommandResult struct {
	ProfileVersion int64 `json:"profileVersion"`
	Replayed       bool  `json:"replayed,omitempty"`
}

// UserProfileCommandStore 将 profile state、命令回执、可选 tag projection
// outbox 与 search projection outbox 在同一 PostgreSQL 事务中提交；同一 key
// 重放不再次推进版本或重复投影。
type UserProfileCommandStore interface {
	ReplayUserProfileCommand(
		ctx context.Context,
		meta UserProfileCommandMeta,
	) (result UserProfileCommandResult, replayed bool, err error)
	CommitUserProfileCommand(
		ctx context.Context,
		profile *model.UserProfile,
		projection *UserProfileTagProjection,
		searchProjections []UserProfileSearchProjection,
		meta UserProfileCommandMeta,
	) (UserProfileCommandResult, error)
}

// UserProfileSearchOutboxEvent is a lease-claimed, replayable projection
// coordinate. EventID is the stable dedupe key for observability; ES document
// idempotency is derived from the authoritative UserProfile object ID.
type UserProfileSearchOutboxEvent struct {
	EventID         string
	UserID          string
	ProfileVersion  int64
	EventType       string
	OccurredAt      time.Time
	DeliveryAttempt int
}

type UserProfileSearchOutboxFailureCode string

const (
	UserProfileSearchOutboxFailureClaim       UserProfileSearchOutboxFailureCode = "claim"
	UserProfileSearchOutboxFailureProject     UserProfileSearchOutboxFailureCode = "search_project"
	UserProfileSearchOutboxFailurePublishAck  UserProfileSearchOutboxFailureCode = "publish_ack"
	UserProfileSearchOutboxFailureRetryRecord UserProfileSearchOutboxFailureCode = "retry_record"
	UserProfileSearchOutboxFailureHealthStore UserProfileSearchOutboxFailureCode = "health_store"
	UserProfileSearchOutboxFailureUnexpected  UserProfileSearchOutboxFailureCode = "unexpected"
)

// UserProfileSearchOutboxFailure keeps dependency failures observable without
// storing user data or raw provider errors.
type UserProfileSearchOutboxFailure struct {
	Code   UserProfileSearchOutboxFailureCode
	Digest string
}

// UserProfileSearchOutboxStore owns the durable checkpoint for ordinary
// UserProfile search projection. Failures are retryable without a terminal path:
// dropping a search projection would make ES permanently diverge from its
// authoritative profile.
type UserProfileSearchOutboxStore interface {
	ClaimReady(
		ctx context.Context,
		owner string,
		now time.Time,
		lease time.Duration,
	) (UserProfileSearchOutboxEvent, bool, error)
	MarkPublished(
		ctx context.Context,
		eventID string,
		owner string,
		publishedAt time.Time,
	) error
	MarkFailed(
		ctx context.Context,
		eventID string,
		owner string,
		failedAt time.Time,
		nextAttemptAt time.Time,
		failure UserProfileSearchOutboxFailure,
	) error
	PendingCount(ctx context.Context) (int, error)
}
