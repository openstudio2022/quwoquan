package projection

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const defaultProjectionBatchSize = 256

var (
	assistantLearningProjectionTickTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "assistant_learning_projection_tick_total",
			Help: "Assistant learning projection scheduler outcomes.",
		},
		[]string{"outcome"},
	)
	assistantLearningProjectionEventsTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "assistant_learning_projection_events_total",
			Help: "Canonical learning facts committed to the active projection.",
		},
	)
)

// FactProjector processes the authoritative append-only fact sequence into the
// redacted learning projection read model.
type FactProjector interface {
	ProjectAvailable(context.Context, int) (int, error)
}

// FactProjectionRebuilder atomically replaces an obsolete projection
// definition with a complete replay of the canonical fact sequence.
type FactProjectionRebuilder interface {
	FactProjector
	Rebuild(context.Context) (int, error)
}

// Scheduler keeps the projection eventually consistent without making the
// user-facing append path depend on projection availability.
type Scheduler struct {
	projector FactProjector
	interval  time.Duration
	batchSize int
	logger    *slog.Logger
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewScheduler(
	projector FactProjector,
	interval time.Duration,
	batchSize int,
	logger *slog.Logger,
) (*Scheduler, error) {
	if projector == nil {
		return nil, errors.New("assistant learning fact projector is required")
	}
	if interval <= 0 {
		return nil, errors.New("assistant learning projection interval must be positive")
	}
	if batchSize <= 0 {
		batchSize = defaultProjectionBatchSize
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Scheduler{
		projector: projector,
		interval:  interval,
		batchSize: batchSize,
		logger:    logger,
		now:       time.Now,
	}, nil
}

func (scheduler *Scheduler) Run(ctx context.Context) {
	scheduler.projectAndObserve(ctx)
	ticker := time.NewTicker(scheduler.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			scheduler.projectAndObserve(ctx)
		}
	}
}

func (scheduler *Scheduler) RunOnce(ctx context.Context) (int, error) {
	return scheduler.projector.ProjectAvailable(ctx, scheduler.batchSize)
}

func (scheduler *Scheduler) projectAndObserve(ctx context.Context) {
	projected, err := scheduler.RunOnce(ctx)
	if err != nil {
		if errors.Is(err, ErrDefinitionMismatch) {
			if rebuilder, ok := scheduler.projector.(FactProjectionRebuilder); ok {
				rebuilt, rebuildErr := rebuilder.Rebuild(ctx)
				if rebuildErr == nil {
					assistantLearningProjectionTickTotal.WithLabelValues("rebuilt").Inc()
					scheduler.recordSuccessfulScan()
					scheduler.logger.InfoContext(
						ctx,
						"assistant learning projection definition rebuilt",
						slog.Int("replayedFacts", rebuilt),
					)
					return
				}
				err = rebuildErr
			}
		}
		assistantLearningProjectionTickTotal.WithLabelValues("failed").Inc()
		scheduler.logger.ErrorContext(
			ctx,
			"assistant learning projection tick failed",
			slog.String("error", err.Error()),
		)
		scheduler.recordFailure(err)
		return
	}
	assistantLearningProjectionTickTotal.WithLabelValues("succeeded").Inc()
	assistantLearningProjectionEventsTotal.Add(float64(projected))
	scheduler.recordSuccessfulScan()
	if projected == scheduler.batchSize {
		scheduler.logger.WarnContext(
			ctx,
			"assistant learning projection remains backlogged",
			slog.Int("batchSize", scheduler.batchSize),
		)
	}
}

func (scheduler *Scheduler) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if scheduler == nil {
		return errors.New("assistant learning projection scheduler is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	scheduler.healthMu.RLock()
	lastSuccessfulScan := scheduler.lastSuccessfulScan
	lastFailure := scheduler.lastFailure
	scheduler.healthMu.RUnlock()
	if lastFailure != nil {
		return lastFailure
	}
	if lastSuccessfulScan.IsZero() {
		return errors.New("assistant learning projection scheduler has not completed a scan")
	}
	if scheduler.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("assistant learning projection scheduler heartbeat is stale")
	}
	return nil
}

func (scheduler *Scheduler) recordSuccessfulScan() {
	scheduler.healthMu.Lock()
	defer scheduler.healthMu.Unlock()
	scheduler.lastSuccessfulScan = scheduler.now().UTC()
	scheduler.lastFailure = nil
}

func (scheduler *Scheduler) recordFailure(err error) {
	scheduler.healthMu.Lock()
	defer scheduler.healthMu.Unlock()
	scheduler.lastFailure = err
}
