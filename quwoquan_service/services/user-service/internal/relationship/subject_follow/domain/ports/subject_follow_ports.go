// Package ports 定义 SubjectFollow 专属的持久化与 outbox 契约。
package ports

import (
	"context"
	"errors"
	"time"

	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
)

var ErrOutboxClaimLost = errors.New("subject follow outbox claim lost")

// SubjectFollowStore 在单个 PostgreSQL 事务内提交 state/version、幂等 receipt
// 与 outbox；目标状态已满足时持久化 no-op receipt 且不推进版本、不追加事件。
type SubjectFollowStore interface {
	Apply(ctx context.Context, command sfmodel.Command) (sfmodel.MutationResult, error)
	Get(ctx context.Context, personaID, subjectType, subjectID string) (sfmodel.SubjectFollow, bool, error)
	ListFollowingByPersona(ctx context.Context, personaID string) ([]sfmodel.SubjectFollow, error)
}

// SubjectFollowOutbox 供 relay checkpoint/replay 已提交的事实。
type SubjectFollowOutbox interface {
	ClaimPendingOutbox(ctx context.Context, ownerID string, lease time.Duration, limit int) ([]sfmodel.OutboxEvent, error)
	MarkOutboxPublished(ctx context.Context, eventID, ownerID string) error
	ReleaseOutboxClaim(ctx context.Context, eventID, ownerID string) error
}
