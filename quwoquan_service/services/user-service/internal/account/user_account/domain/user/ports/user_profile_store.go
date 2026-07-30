package ports

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

type UserProfileStore interface {
	FindByID(ctx context.Context, userID string) (*model.UserProfile, error)
	FindByNickname(ctx context.Context, nickname string) (*model.UserProfile, error)
	SearchProfiles(ctx context.Context, query string, limit int) ([]model.UserProfile, error)
	CreateAccount(ctx context.Context, command UserAccountCreate) error
	PromoteRegistration(ctx context.Context, command RegistrationPromotion) error
}

// UserAccountCreate deliberately excludes every public-profile field. Public
// presentation is authored by Persona and only materialized into user_profiles
// by PersonaProfileProjector.
type UserAccountCreate struct {
	UserID                   string
	AccountState             string
	IdentityOrigin           string
	LogicalShard             int
	AnonymousRetentionPolicy string
	Phone                    string
	PersonaCount             int
}

// RegistrationPromotion is the narrow account-state write used when an
// anonymous owner binds a registered credential. It cannot mutate Persona
// public-profile state or its UserAccount read projection.
type RegistrationPromotion struct {
	UserID string
	Phone  string
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
