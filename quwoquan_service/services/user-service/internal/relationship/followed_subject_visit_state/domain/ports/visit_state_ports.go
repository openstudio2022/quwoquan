// Package ports 定义 FollowedSubjectVisitState 专属的持久化与 outbox 契约。
package ports

import (
	"context"
	"errors"
	"time"

	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
)

var ErrOutboxClaimLost = errors.New("followed subject visit outbox claim lost")

// VisitStateStore 在单个 Mongo 事务内提交水位与 FollowedSubjectVisited
// outbox 记录。重复 clientRequestId 是幂等重放：返回已存结果、不推进水位、
// 不追加第二条事件。
type VisitStateStore interface {
	MarkVisited(
		ctx context.Context,
		command visitmodel.MarkVisitedCommand,
	) (visitmodel.VisitResult, error)
}

// VisitStateOutbox 供 relay 以租约认领、发布并确认已提交的事实。租约到期后
// 未确认的事件会被重新认领，因此投递语义是至少一次。
type VisitStateOutbox interface {
	ClaimPendingOutbox(
		ctx context.Context,
		ownerID string,
		lease time.Duration,
		limit int,
	) ([]visitmodel.OutboxEvent, error)
	MarkOutboxPublished(ctx context.Context, eventID, ownerID string) error
	ReleaseOutboxClaim(ctx context.Context, eventID, ownerID string) error
}
