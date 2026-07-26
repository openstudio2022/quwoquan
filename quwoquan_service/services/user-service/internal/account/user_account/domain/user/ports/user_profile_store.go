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

type UserProfileCommandMeta struct {
	IdempotencyKey string
	CommandDigest  string
}

type UserProfileCommandResult struct {
	ProfileVersion int64 `json:"profileVersion"`
	Replayed       bool  `json:"replayed,omitempty"`
}

// UserProfileCommandStore 将 profile state、命令回执和可选 tag projection
// outbox 在同一 PostgreSQL 事务中提交；同一 key 重放不再次推进版本。
type UserProfileCommandStore interface {
	ReplayUserProfileCommand(
		ctx context.Context,
		meta UserProfileCommandMeta,
	) (result UserProfileCommandResult, replayed bool, err error)
	CommitUserProfileCommand(
		ctx context.Context,
		profile *model.UserProfile,
		projection *UserProfileTagProjection,
		meta UserProfileCommandMeta,
	) (UserProfileCommandResult, error)
}
