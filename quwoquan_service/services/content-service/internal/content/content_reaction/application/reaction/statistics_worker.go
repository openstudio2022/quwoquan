package reaction

import (
	"context"
	"fmt"
	"log/slog"
	"time"
)

type StatisticsRollupStore interface {
	Rollup(ctx context.Context, freshFor time.Duration) (generation string, sourceCheckpoint int64, err error)
}

// StatisticsRollupWorker bounds rollup frequency independently from event
// delivery. The durable ledger remains the recovery source when a rollup fails.
type StatisticsRollupWorker struct {
	store    StatisticsRollupStore
	interval time.Duration
	freshFor time.Duration
}

func NewStatisticsRollupWorker(store StatisticsRollupStore, interval, freshFor time.Duration) *StatisticsRollupWorker {
	if interval <= 0 {
		interval = time.Second
	}
	if freshFor <= 0 {
		freshFor = 5 * time.Second
	}
	return &StatisticsRollupWorker{store: store, interval: interval, freshFor: freshFor}
}

func (w *StatisticsRollupWorker) Run(ctx context.Context) error {
	if w == nil || w.store == nil {
		return fmt.Errorf("ContentReaction statistics rollup worker is unavailable")
	}
	ticker := time.NewTicker(w.interval)
	defer ticker.Stop()
	for {
		if _, _, err := w.store.Rollup(ctx, w.freshFor); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "ContentReaction statistics rollup failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}
