package persona_relationship

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

// OutboxEventPublisher is the transport boundary for committed relationship
// facts. The relay owns delivery; commands never publish before commit.
// Implementations must durably append before returning success because that
// acknowledgement advances the PostgreSQL outbox checkpoint.
type OutboxEventPublisher interface {
	PublishPersonaRelationship(ctx context.Context, event relmodel.OutboxEvent) error
}

type OutboxRelay struct {
	outbox    relports.PersonaRelationshipOutbox
	publisher OutboxEventPublisher
	ownerID   string
}

func NewOutboxRelay(outbox relports.PersonaRelationshipOutbox, publisher OutboxEventPublisher) *OutboxRelay {
	if outbox == nil || publisher == nil {
		panic("persona relationship outbox and publisher are required")
	}
	return &OutboxRelay{outbox: outbox, publisher: publisher, ownerID: uuid.NewString()}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	events, err := r.outbox.ClaimPendingOutbox(ctx, r.ownerID, time.Minute, limit)
	if err != nil {
		return 0, err
	}
	for _, event := range events {
		if err := r.publisher.PublishPersonaRelationship(ctx, event); err != nil {
			_ = r.outbox.ReleaseOutboxClaim(ctx, event.EventID, r.ownerID)
			return 0, fmt.Errorf("publish persona relationship outbox event %s: %w", event.EventID, err)
		}
		if err := r.outbox.MarkOutboxPublished(ctx, event.EventID, r.ownerID); err != nil {
			if errors.Is(err, relports.ErrOutboxClaimLost) {
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
			// The PostgreSQL outbox is the durable retry source. A transient
			// database or transport failure must not terminate the worker and
			// silently strand every later relationship event.
			slog.ErrorContext(ctx, "persona relationship outbox drain failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}
