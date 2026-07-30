package application

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

type DispatcherConfig struct {
	Owner          string
	PollInterval   time.Duration
	LeaseDuration  time.Duration
	RequestTimeout time.Duration
	InitialBackoff time.Duration
	MaxBackoff     time.Duration
	MaxPendingAge  time.Duration
	MaxAttempts    int
	BatchSize      int
}

type Dispatcher struct {
	store   ports.DeliveryStore
	target  ports.EnforcementTarget
	metrics ports.Metrics
	config  DispatcherConfig
	now     func() time.Time
}

func NewDispatcher(
	store ports.DeliveryStore,
	target ports.EnforcementTarget,
	metrics ports.Metrics,
	config DispatcherConfig,
) (*Dispatcher, error) {
	config.Owner = strings.TrimSpace(config.Owner)
	if store == nil || target == nil || config.Owner == "" ||
		config.PollInterval <= 0 || config.LeaseDuration <= 0 ||
		config.RequestTimeout <= 0 || config.InitialBackoff <= 0 ||
		config.MaxBackoff < config.InitialBackoff || config.MaxPendingAge <= 0 ||
		config.MaxAttempts < 1 || config.MaxAttempts > 20 ||
		config.BatchSize < 1 || config.BatchSize > 100 {
		return nil, errors.New("account enforcement dispatcher config is invalid")
	}
	if metrics == nil {
		metrics = noopMetrics{}
	}
	return &Dispatcher{store: store, target: target, metrics: metrics, config: config, now: time.Now}, nil
}

func (dispatcher *Dispatcher) Run(ctx context.Context) {
	ticker := time.NewTicker(dispatcher.config.PollInterval)
	defer ticker.Stop()
	for {
		if _, err := dispatcher.DispatchOnce(ctx); err != nil && !errors.Is(err, context.Canceled) {
			slog.ErrorContext(ctx, "account enforcement delivery pass failed", "error_class", "store_unavailable")
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (dispatcher *Dispatcher) DispatchOnce(ctx context.Context) (int, error) {
	now := dispatcher.now().UTC()
	jobs, err := dispatcher.store.ClaimDue(
		ctx,
		dispatcher.config.Owner,
		now,
		dispatcher.config.LeaseDuration,
		dispatcher.config.BatchSize,
	)
	if err != nil {
		return 0, err
	}
	delivered := 0
	for _, job := range jobs {
		started := time.Now()
		requestContext, cancel := context.WithTimeout(ctx, dispatcher.config.RequestTimeout)
		receipt, applyErr := dispatcher.target.Apply(requestContext, job.Decision)
		cancel()
		if applyErr == nil {
			receipt.DecisionID = job.Decision.ID
			receipt.DeliveredAt = dispatcher.now().UTC()
			if err := dispatcher.store.MarkDelivered(ctx, dispatcher.config.Owner, receipt); err != nil {
				dispatcher.metrics.ObserveDelivery(string(job.Decision.Action), "receipt_failed", time.Since(started))
				return delivered, err
			}
			dispatcher.metrics.ObserveDelivery(string(job.Decision.Action), "delivered", time.Since(started))
			delivered++
			continue
		}

		errorClass, permanent := classifyDeliveryError(applyErr)
		nextAttemptAt := now.Add(dispatcher.backoff(job.Attempts))
		status, markErr := dispatcher.store.MarkFailed(
			ctx,
			dispatcher.config.Owner,
			job,
			errorClass,
			permanent,
			dispatcher.config.MaxAttempts,
			nextAttemptAt,
			dispatcher.now().UTC(),
		)
		if markErr != nil {
			dispatcher.metrics.ObserveDelivery(string(job.Decision.Action), "failure_receipt_failed", time.Since(started))
			return delivered, markErr
		}
		outcome := "retry_scheduled"
		if status == model.DeliveryStatusDeadLetter {
			outcome = "dead_letter"
		}
		dispatcher.metrics.ObserveDelivery(string(job.Decision.Action), outcome, time.Since(started))
		slog.WarnContext(
			ctx,
			"account enforcement delivery failed",
			"action", job.Decision.Action,
			"outcome", outcome,
			"error_class", errorClass,
		)
	}
	dispatcher.observeBacklog(ctx)
	return delivered, nil
}

func (dispatcher *Dispatcher) CheckReadiness(ctx context.Context) error {
	backlog, err := dispatcher.store.Backlog(ctx, dispatcher.now().UTC())
	if err != nil {
		return fmt.Errorf("account enforcement backlog unavailable: %w", err)
	}
	dispatcher.publishBacklog(backlog)
	if backlog.DeadLetter > 0 {
		return fmt.Errorf("account enforcement terminal delivery backlog is non-zero")
	}
	if backlog.OldestDue != nil &&
		dispatcher.now().UTC().Sub(backlog.OldestDue.UTC()) > dispatcher.config.MaxPendingAge {
		return fmt.Errorf("account enforcement pending delivery exceeded readiness age")
	}
	return nil
}

func (dispatcher *Dispatcher) observeBacklog(ctx context.Context) {
	backlog, err := dispatcher.store.Backlog(ctx, dispatcher.now().UTC())
	if err == nil {
		dispatcher.publishBacklog(backlog)
	}
}

func (dispatcher *Dispatcher) publishBacklog(backlog ports.DeliveryBacklog) {
	dispatcher.metrics.SetDeliveryBacklog(string(model.DeliveryStatusPending), float64(backlog.Pending))
	dispatcher.metrics.SetDeliveryBacklog(string(model.DeliveryStatusRetrying), float64(backlog.Retrying))
	dispatcher.metrics.SetDeliveryBacklog(string(model.DeliveryStatusDeadLetter), float64(backlog.DeadLetter))
}

func (dispatcher *Dispatcher) backoff(attempts int) time.Duration {
	backoff := dispatcher.config.InitialBackoff
	for current := 0; current < attempts && backoff < dispatcher.config.MaxBackoff; current++ {
		backoff *= 2
		if backoff > dispatcher.config.MaxBackoff {
			return dispatcher.config.MaxBackoff
		}
	}
	return backoff
}

func classifyDeliveryError(err error) (string, bool) {
	var classified ports.ClassifiedDeliveryError
	if errors.As(err, &classified) {
		value := strings.TrimSpace(classified.ErrorClass())
		if value == "" {
			value = "transport_unavailable"
		}
		return value, classified.Permanent()
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return "timeout", false
	}
	if errors.Is(err, context.Canceled) {
		return "canceled", false
	}
	return "transport_unavailable", false
}
