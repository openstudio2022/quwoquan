package followed_subject_visit_state

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
	visitports "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/ports"
)

// OutboxEventPublisher 是已提交访问水位事实的投递边界。实现必须在返回成功
// 前完成全部持久副作用（Redis Stream 追加 + following_subjects 投影 upsert），
// 因为该确认会把 outbox 记录标记为已投递。
type OutboxEventPublisher interface {
	PublishFollowedSubjectVisited(ctx context.Context, event visitmodel.OutboxEvent) error
}

// OutboxRelay 是 FollowedSubjectVisited 的唯一投递主线。投递至少一次，
// 消费侧按 eventId 幂等。
type OutboxRelay struct {
	outbox    visitports.VisitStateOutbox
	publisher OutboxEventPublisher
	ownerID   string
}

func NewOutboxRelay(
	outbox visitports.VisitStateOutbox,
	publisher OutboxEventPublisher,
) *OutboxRelay {
	if outbox == nil || publisher == nil {
		panic("followed subject visit outbox and publisher are required")
	}
	return &OutboxRelay{outbox: outbox, publisher: publisher, ownerID: uuid.NewString()}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	events, err := r.outbox.ClaimPendingOutbox(ctx, r.ownerID, time.Minute, limit)
	if err != nil {
		return 0, err
	}
	published := 0
	for _, event := range events {
		if err := r.publisher.PublishFollowedSubjectVisited(ctx, event); err != nil {
			_ = r.outbox.ReleaseOutboxClaim(ctx, event.EventID, r.ownerID)
			return published, fmt.Errorf(
				"publish followed subject visit outbox event %s: %w", event.EventID, err,
			)
		}
		if err := r.outbox.MarkOutboxPublished(ctx, event.EventID, r.ownerID); err != nil {
			if errors.Is(err, visitports.ErrOutboxClaimLost) {
				continue
			}
			return published, err
		}
		published++
	}
	return published, nil
}

func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := r.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			// Mongo outbox 是持久重试源；瞬时故障不得终止 worker。
			slog.ErrorContext(ctx, "followed subject visit outbox drain failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}
