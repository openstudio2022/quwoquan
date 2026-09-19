package reaction

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/outboxrelay"
)

const defaultReactionOutboxConsumer = "content-reaction-runtime-events"

// OutboxRelay drains every claimed partition independently. A poison event or
// gap stops only that partition and never advances its continuous checkpoint.
type OutboxRelay struct {
	reader      reactionports.OutboxReader
	checkpoints reactionports.ProjectionCheckpointStore
	publisher   reactionports.OutboxPublisher
	consumer    string
	ownerID     string
	drainMu     sync.Mutex
	supervisor  *outboxrelay.Supervisor
}

func NewOutboxRelay(
	reader reactionports.OutboxReader,
	checkpoints reactionports.ProjectionCheckpointStore,
	publisher reactionports.OutboxPublisher,
	consumer string,
) *OutboxRelay {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = defaultReactionOutboxConsumer
	}
	return &OutboxRelay{
		reader: reader, checkpoints: checkpoints, publisher: publisher,
		consumer: consumer, ownerID: uuid.NewString(),
		supervisor: outboxrelay.NewSupervisor(consumer),
	}
}

func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	r.drainMu.Lock()
	defer r.drainMu.Unlock()
	if r == nil || r.reader == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, fmt.Errorf("content reaction outbox relay is not fully configured")
	}
	leases, err := r.reader.ClaimOutboxPartitions(
		ctx, r.consumer, r.ownerID, time.Minute,
		reactionports.ContentReactionOutboxPartitionCount,
	)
	if err != nil {
		return 0, fmt.Errorf("claim ContentReaction outbox partitions: %w", err)
	}
	if limit <= 0 || limit > 1000 {
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
			facts, readErr := r.reader.ReadOutboxPartition(ctx, lease, limit)
			if readErr != nil {
				results <- partitionResult{err: readErr}
				return
			}
			processed := 0
			for _, fact := range facts {
				if fact.PartitionKey == "" || fact.PartitionID != lease.PartitionID ||
					fact.PartitionSequence != lease.Sequence+1 {
					results <- partitionResult{processed: processed, err: fmt.Errorf(
						"ContentReaction partition %d has non-contiguous fact %q",
						lease.PartitionID, fact.EventID,
					)}
					return
				}
				if publishErr := r.publisher.Publish(ctx, fact); publishErr != nil {
					results <- partitionResult{processed: processed, err: fmt.Errorf(
						"publish ContentReaction partition %d sequence %d fact %q: %w",
						fact.PartitionID, fact.PartitionSequence, fact.EventID, publishErr,
					)}
					return
				}
				if advanceErr := r.checkpoints.AdvanceOutboxCheckpoint(ctx, lease, fact); advanceErr != nil {
					if errors.Is(advanceErr, reactionports.ErrOutboxLeaseLost) {
						results <- partitionResult{processed: processed}
					} else {
						results <- partitionResult{processed: processed, err: advanceErr}
					}
					return
				}
				lease.Sequence = fact.PartitionSequence
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
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("content reaction outbox relay is not configured")
	}
	return r.supervisor.Run(ctx, interval, func(scanCtx context.Context) (int, error) {
		return r.Drain(scanCtx, 100)
	})
}

func (r *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil || r.supervisor == nil {
		return fmt.Errorf("content reaction outbox relay is not configured")
	}
	return r.supervisor.Healthy(maxStaleness)
}
