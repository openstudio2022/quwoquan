package reliabletask

import (
	"context"
	"errors"
	"fmt"
	"sync/atomic"
	"time"
)

// RemainingDataContentFleetBatchDuration projects the frozen absolute batch
// deadline onto the time this process may still consume. The deadline is frozen
// once per execution, so a restart, a lease renewal or a rebuilt child process
// can only ever receive what is left of it; none of them may re-inject the full
// batch budget. An exhausted deadline is a failure of this run rather than a
// zero-length budget, because no new job may start once nothing is left.
func RemainingDataContentFleetBatchDuration(
	deadlineEpochSeconds int64,
	now time.Time,
) (time.Duration, error) {
	if deadlineEpochSeconds < 1 {
		return 0, errors.New(
			"data content fleetBatchDeadlineEpochSeconds must be a frozen absolute epoch second",
		)
	}
	remaining := time.Unix(deadlineEpochSeconds, 0).UTC().Sub(now.UTC())
	if remaining <= 0 {
		return 0, fmt.Errorf(
			"data content fleet batch deadline is exhausted: deadline=%d now=%d",
			deadlineEpochSeconds,
			now.UTC().Unix(),
		)
	}
	return remaining, nil
}

// DataContentConcurrencyObserver measures how many object executions run at the
// same time. It is an observation only: it never admits, delays or rejects work,
// so a run that stays below the frozen cap produces the same object outcomes as
// one that reaches it. The zero value is ready to use.
type DataContentConcurrencyObserver struct {
	active atomic.Int64
	peak   atomic.Int64
}

// Observe wraps one executor so every object execution passing through it is
// counted. A missing executor is a composition failure, so the wrapper reports
// it per call instead of counting a run that cannot execute anything.
func (o *DataContentConcurrencyObserver) Observe(
	executor DataContentExecutor,
) DataContentExecutor {
	return DataContentExecutorFunc(func(
		ctx context.Context,
		item DataContentWorkItem,
	) (DataContentExecutionResult, error) {
		if executor == nil {
			return DataContentExecutionResult{}, errors.New(
				"data content concurrency observer requires an executor",
			)
		}
		o.enter()
		defer o.active.Add(-1)
		return executor.ExecuteDataContentObject(ctx, item)
	})
}

func (o *DataContentConcurrencyObserver) enter() {
	current := o.active.Add(1)
	for {
		peak := o.peak.Load()
		if current <= peak || o.peak.CompareAndSwap(peak, current) {
			return
		}
	}
}

// Peak returns the highest number of object executions observed running at the
// same time. It stays at zero until at least one execution has been observed,
// which is why callers must pass it explicitly into the fleet report rather than
// letting an unobserved run report a peak of zero as if it were measured.
func (o *DataContentConcurrencyObserver) Peak() int {
	return int(o.peak.Load())
}
