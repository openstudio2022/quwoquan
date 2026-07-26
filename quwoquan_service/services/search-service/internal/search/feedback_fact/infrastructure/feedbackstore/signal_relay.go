package feedbackstore

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
)

const (
	feedbackSignalRelayPollInterval = 500 * time.Millisecond
	feedbackSignalRelayMaxBackoff   = 30 * time.Second
	feedbackSignalRelayLease        = 15 * time.Second
)

type SignalRelayObserver interface {
	ObserveFeedbackSignalRelay(outcome string)
	SetFeedbackSignalPendingAge(seconds float64)
}

// SignalRelay publishes delivery rows created atomically with committed click
// facts. A crash or acknowledgement failure leaves the row replayable with the
// same semantic signal id; it never mutates the immutable feedback fact.
type SignalRelay struct {
	store     *Store
	publisher signalapplication.Publisher
	observer  SignalRelayObserver
	logger    *slog.Logger
	relayID   string

	healthMu       sync.RWMutex
	lastScan       time.Time
	lastRelayError error
}

func NewSignalRelay(
	store *Store,
	publisher signalapplication.Publisher,
	observer SignalRelayObserver,
	logger *slog.Logger,
) (*SignalRelay, error) {
	if store == nil ||
		store.signalDeliveries == nil ||
		publisher == nil ||
		observer == nil {
		return nil, fmt.Errorf(
			"search feedback signal relay requires store, publisher, and observer",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &SignalRelay{
		store:     store,
		publisher: publisher,
		observer:  observer,
		logger:    logger,
		relayID:   "feedback-signal-relay-" + bson.NewObjectID().Hex(),
	}, nil
}

// ProcessOnce publishes at most one leased delivery row.
func (relay *SignalRelay) ProcessOnce(
	ctx context.Context,
) (bool, error) {
	if relay == nil ||
		relay.store == nil ||
		relay.publisher == nil ||
		relay.observer == nil {
		return false, fmt.Errorf(
			"search feedback signal relay is not configured",
		)
	}
	delivery, found, err := relay.store.leaseNextSignalDelivery(
		ctx,
		relay.relayID,
		feedbackSignalRelayLease,
	)
	if err != nil {
		relay.observer.ObserveFeedbackSignalRelay("read_error")
		relay.recordFailure(err)
		return false, err
	}
	if !found {
		relay.observer.SetFeedbackSignalPendingAge(0)
		relay.recordSuccess()
		return false, nil
	}
	pendingAge := time.Since(delivery.CreatedAt).Seconds()
	if pendingAge < 0 {
		pendingAge = 0
	}
	relay.observer.SetFeedbackSignalPendingAge(pendingAge)
	var signal signalapplication.Signal
	if err := json.Unmarshal(
		[]byte(delivery.SignalPayloadJSON),
		&signal,
	); err != nil {
		err = fmt.Errorf("decode committed feedback signal delivery: %w", err)
		_ = relay.store.releaseSignalDelivery(ctx, delivery.ID, relay.relayID)
		relay.observer.ObserveFeedbackSignalRelay("invalid_fact")
		relay.recordFailure(err)
		return true, err
	}
	if err := relay.publisher.PublishSearchSignal(ctx, signal); err != nil {
		err = fmt.Errorf("publish feedback recommendation signal: %w", err)
		if releaseErr := relay.store.releaseSignalDelivery(
			ctx,
			delivery.ID,
			relay.relayID,
		); releaseErr != nil {
			err = fmt.Errorf("%w; release delivery lease: %v", err, releaseErr)
		}
		relay.observer.ObserveFeedbackSignalRelay("publish_error")
		relay.recordFailure(err)
		return true, err
	}
	acknowledged, err := relay.store.acknowledgeSignalDelivery(
		ctx,
		delivery.ID,
		relay.relayID,
	)
	if err != nil {
		err = fmt.Errorf("acknowledge feedback recommendation signal: %w", err)
		relay.observer.ObserveFeedbackSignalRelay("ack_error")
		relay.recordFailure(err)
		return true, err
	}
	if !acknowledged {
		err = fmt.Errorf("feedback recommendation signal delivery lease lost")
		relay.observer.ObserveFeedbackSignalRelay("ack_error")
		relay.recordFailure(err)
		return true, err
	}
	relay.observer.ObserveFeedbackSignalRelay("published")
	relay.recordSuccess()
	return true, nil
}

func (relay *SignalRelay) Run(ctx context.Context) {
	retryDelay := feedbackSignalRelayPollInterval
	for {
		didWork, err := relay.ProcessOnce(ctx)
		if err != nil {
			if ctx.Err() == nil {
				relay.logger.ErrorContext(
					ctx,
					"search feedback signal relay failed",
					slog.String("err", err.Error()),
				)
			}
			if !waitForFeedbackSignalRelay(ctx, retryDelay) {
				return
			}
			retryDelay = min(
				retryDelay*2,
				feedbackSignalRelayMaxBackoff,
			)
			continue
		}
		retryDelay = feedbackSignalRelayPollInterval
		if didWork {
			continue
		}
		if !waitForFeedbackSignalRelay(
			ctx,
			feedbackSignalRelayPollInterval,
		) {
			return
		}
	}
}

func waitForFeedbackSignalRelay(
	ctx context.Context,
	delay time.Duration,
) bool {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}

func (relay *SignalRelay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return fmt.Errorf("search feedback signal relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.healthMu.RLock()
	lastScan := relay.lastScan
	lastErr := relay.lastRelayError
	relay.healthMu.RUnlock()
	if lastErr != nil {
		return fmt.Errorf("search feedback signal relay unhealthy: %w", lastErr)
	}
	if lastScan.IsZero() ||
		time.Since(lastScan) > maxStaleness {
		return fmt.Errorf("search feedback signal relay heartbeat is stale")
	}
	return nil
}

func (relay *SignalRelay) recordSuccess() {
	relay.healthMu.Lock()
	relay.lastScan = time.Now().UTC()
	relay.lastRelayError = nil
	relay.healthMu.Unlock()
}

func (relay *SignalRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastScan = time.Now().UTC()
	relay.lastRelayError = err
	relay.healthMu.Unlock()
}
