package persona_relationship

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

const defaultPersonaRelationshipOutboxConsumer = "persona-relationship-runtime-events"

// OutboxEventPublisher is the transport boundary for committed relationship
// facts. The relay attaches the same stable partition envelope for every sink.
type OutboxEventPublisher interface {
	PublishPersonaRelationship(ctx context.Context, event relmodel.OutboxEvent) error
}

type OutboxRelay struct {
	outbox    relports.PartitionedPersonaRelationshipOutbox
	publisher OutboxEventPublisher
	consumer  string
	ownerID   string
	drainMu   sync.Mutex
}

func NewOutboxRelay(
	outbox relports.PartitionedPersonaRelationshipOutbox,
	publisher OutboxEventPublisher,
) *OutboxRelay {
	if outbox == nil || publisher == nil {
		panic("persona relationship outbox and publisher are required")
	}
	return &OutboxRelay{
		outbox: outbox, publisher: publisher,
		consumer: defaultPersonaRelationshipOutboxConsumer, ownerID: uuid.NewString(),
	}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	r.drainMu.Lock()
	defer r.drainMu.Unlock()
	leases, err := r.outbox.ClaimOutboxPartitions(
		ctx, r.consumer, r.ownerID, time.Minute,
		relports.PersonaRelationshipOutboxPartitionCount,
	)
	if err != nil {
		return 0, err
	}
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	type partitionResult struct {
		processed int
		err       error
	}
	results := make(chan partitionResult, len(leases))
	var workers sync.WaitGroup
	for _, claimedLease := range leases {
		lease := claimedLease
		workers.Add(1)
		go func() {
			defer workers.Done()
			events, readErr := r.outbox.ReadOutboxPartition(ctx, lease, limit)
			if readErr != nil {
				results <- partitionResult{err: readErr}
				return
			}
			processed := 0
			for _, event := range events {
				publishCtx := relports.WithOutboxEnvelope(ctx, event)
				if publishErr := r.publisher.PublishPersonaRelationship(publishCtx, event.Event); publishErr != nil {
					results <- partitionResult{processed: processed, err: fmt.Errorf(
						"publish persona relationship partition %d sequence %d event %s: %w",
						event.PartitionID, event.PartitionSequence, event.Event.EventID, publishErr,
					)}
					return
				}
				if advanceErr := r.outbox.AdvanceOutboxCheckpoint(ctx, lease, event); advanceErr != nil {
					if errors.Is(advanceErr, relports.ErrOutboxLeaseLost) {
						results <- partitionResult{processed: processed}
					} else {
						results <- partitionResult{processed: processed, err: advanceErr}
					}
					return
				}
				lease.Sequence = event.PartitionSequence
				processed++
			}
			results <- partitionResult{processed: processed}
		}()
	}
	workers.Wait()
	close(results)
	processed := 0
	var firstErr error
	for result := range results {
		processed += result.processed
		if firstErr == nil && result.err != nil {
			firstErr = result.err
		}
	}
	return processed, firstErr
}

func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := r.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "persona relationship outbox drain failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}
