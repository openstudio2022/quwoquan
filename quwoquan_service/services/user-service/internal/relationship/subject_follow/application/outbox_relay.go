package subject_follow

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
	sfports "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/ports"
)

// OutboxEventPublisher 是已提交 SubjectFollow 事实的投递边界。实现必须在
// 返回成功前完成持久追加（Redis Stream + following_subject 投影 upsert），
// 因为该确认会推进 PostgreSQL outbox checkpoint。
type OutboxEventPublisher interface {
	PublishSubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error
}

type OutboxRelay struct {
	outbox    sfports.SubjectFollowOutbox
	publisher OutboxEventPublisher
	ownerID   string
}

func NewOutboxRelay(outbox sfports.SubjectFollowOutbox, publisher OutboxEventPublisher) *OutboxRelay {
	if outbox == nil || publisher == nil {
		panic("subject follow outbox and publisher are required")
	}
	return &OutboxRelay{outbox: outbox, publisher: publisher, ownerID: uuid.NewString()}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	events, err := r.outbox.ClaimPendingOutbox(ctx, r.ownerID, time.Minute, limit)
	if err != nil {
		return 0, err
	}
	for _, event := range events {
		if err := r.publisher.PublishSubjectFollow(ctx, event); err != nil {
			_ = r.outbox.ReleaseOutboxClaim(ctx, event.EventID, r.ownerID)
			return 0, fmt.Errorf("publish subject follow outbox event %s: %w", event.EventID, err)
		}
		if err := r.outbox.MarkOutboxPublished(ctx, event.EventID, r.ownerID); err != nil {
			if errors.Is(err, sfports.ErrOutboxClaimLost) {
				continue
			}
			return 0, err
		}
	}
	return len(events), nil
}

func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := r.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			// PostgreSQL outbox 是持久重试源；瞬时故障不得终止 worker。
			slog.ErrorContext(ctx, "subject follow outbox drain failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}
