package runruntime

import (
	"context"
	"errors"
	"time"
)

// Healthy derives readiness from the latest durable queue round trip or
// active claim heartbeat. Goroutine existence is never treated as liveness.
func (w *DurableWorker) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if w == nil {
		return errors.New("assistant durable run worker is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	w.healthMu.RLock()
	lastSuccessfulPoll := w.lastSuccessfulPoll
	lastFailure := w.lastFailure
	w.healthMu.RUnlock()
	if lastFailure != nil {
		return lastFailure
	}
	if lastSuccessfulPoll.IsZero() {
		return errors.New("assistant durable run worker has not completed a poll")
	}
	if w.now().UTC().Sub(lastSuccessfulPoll) > maxStaleness {
		return errors.New("assistant durable run worker heartbeat is stale")
	}
	return nil
}

func (w *DurableWorker) recordPoll(err error) {
	if w == nil {
		return
	}
	w.healthMu.Lock()
	defer w.healthMu.Unlock()
	if err != nil {
		w.lastFailure = err
		return
	}
	w.lastSuccessfulPoll = w.now().UTC()
	w.lastFailure = nil
}
