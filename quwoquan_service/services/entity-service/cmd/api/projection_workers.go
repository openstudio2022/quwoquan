package bootstrap

import (
	"context"
	"log"
	"time"
)

type projectionRunner interface {
	RunOnce(ctx context.Context, limit int) (int, error)
}

type namedProjectionRunner struct {
	name   string
	runner projectionRunner
}

func projectionWorkerStarts(runners []namedProjectionRunner) []func(context.Context) {
	starts := make([]func(context.Context), 0, len(runners))
	for _, runner := range runners {
		runner := runner
		starts = append(starts, func(ctx context.Context) {
			runProjectionLoop(ctx, runner)
		})
	}
	return starts
}

func runProjectionLoop(ctx context.Context, named namedProjectionRunner) {
	const (
		interval  = 2 * time.Second
		batchSize = 100
	)
	delay := time.Duration(0)
	consecutiveFailures := 0
	for {
		if delay > 0 {
			timer := time.NewTimer(delay)
			select {
			case <-ctx.Done():
				timer.Stop()
				return
			case <-timer.C:
			}
		}
		if _, err := named.runner.RunOnce(ctx, batchSize); err != nil && ctx.Err() == nil {
			log.Printf("entity-service projection %s failed: %v", named.name, err)
			consecutiveFailures++
			delay = projectionRetryDelay(interval, consecutiveFailures)
		} else {
			consecutiveFailures = 0
			delay = interval
		}
	}
}

func projectionRetryDelay(base time.Duration, attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 5 {
		attempt = 5
	}
	delay := base * time.Duration(1<<(attempt-1))
	if delay > 30*time.Second {
		return 30 * time.Second
	}
	return delay
}
