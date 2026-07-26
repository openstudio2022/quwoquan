package profile_update_proposal

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	proposalevent "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/event"
	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
)

const profileProposalOutboxLease = time.Minute

var (
	profileProposalOutboxDrainTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "user_profile_update_proposal_outbox_drain_total",
			Help: "ProfileUpdateProposal transactional outbox drain outcomes.",
		},
		[]string{"outcome"},
	)
	profileProposalOutboxPublishedTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "user_profile_update_proposal_outbox_published_total",
			Help: "ProfileUpdateProposal domain events confirmed by durable transport.",
		},
	)
)

// OutboxEventPublisher must durably append the metadata-owned public event
// before returning success. That acknowledgement advances the PostgreSQL
// checkpoint, so an error must leave the row replayable.
type OutboxEventPublisher interface {
	PublishProfileUpdateProposal(context.Context, ports.OutboxEvent) error
}

type OutboxRelay struct {
	outbox    ports.TransactionalOutbox
	publisher OutboxEventPublisher
	ownerID   string
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewOutboxRelay(
	outbox ports.TransactionalOutbox,
	publisher OutboxEventPublisher,
) (*OutboxRelay, error) {
	if outbox == nil || publisher == nil {
		return nil, errors.New("profile proposal outbox and publisher are required")
	}
	return &OutboxRelay{
		outbox:    outbox,
		publisher: publisher,
		ownerID:   uuid.NewString(),
		now:       time.Now,
	}, nil
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	events, err := relay.outbox.ClaimPendingOutbox(
		ctx,
		relay.ownerID,
		profileProposalOutboxLease,
		limit,
	)
	if err != nil {
		relay.recordFailure(err)
		return 0, err
	}
	published := 0
	for index, event := range events {
		if !isProfileUpdateProposalPublicEvent(event.EventType) {
			err := fmt.Errorf(
				"unsupported ProfileUpdateProposal outbox event %q",
				event.EventType,
			)
			relay.releaseClaims(ctx, events[index:])
			relay.recordFailure(err)
			return published, err
		}
		if err := relay.publisher.PublishProfileUpdateProposal(ctx, event); err != nil {
			releaseErr := relay.releaseClaims(ctx, events[index:])
			publishErr := fmt.Errorf(
				"publish profile proposal outbox event %s: %w",
				event.EventID,
				err,
			)
			if releaseErr != nil {
				publishErr = errors.Join(publishErr, releaseErr)
			}
			relay.recordFailure(publishErr)
			return published, publishErr
		}
		if err := relay.outbox.MarkOutboxPublished(
			ctx,
			event.EventID,
			relay.ownerID,
		); err != nil {
			if errors.Is(err, ports.ErrOutboxClaimLost) {
				continue
			}
			releaseErr := relay.releaseClaims(ctx, events[index:])
			checkpointErr := fmt.Errorf(
				"checkpoint profile proposal outbox event %s: %w",
				event.EventID,
				err,
			)
			if releaseErr != nil {
				checkpointErr = errors.Join(checkpointErr, releaseErr)
			}
			relay.recordFailure(checkpointErr)
			return published, checkpointErr
		}
		published++
		profileProposalOutboxPublishedTotal.Inc()
	}
	relay.recordSuccessfulScan()
	return published, nil
}

func (relay *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			slog.ErrorContext(
				ctx,
				"ProfileUpdateProposal outbox drain failed",
				"err",
				err,
			)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

// Healthy is the readiness heartbeat for the relay. A publish/checkpoint
// failure makes the process unready until a later ordered scan succeeds.
func (relay *OutboxRelay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return errors.New("ProfileUpdateProposal outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.healthMu.RLock()
	lastSuccessfulScan := relay.lastSuccessfulScan
	lastFailure := relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return fmt.Errorf("ProfileUpdateProposal outbox relay failed: %w", lastFailure)
	}
	if lastSuccessfulScan.IsZero() {
		return errors.New("ProfileUpdateProposal outbox relay has not completed a scan")
	}
	if relay.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("ProfileUpdateProposal outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) releaseClaims(
	ctx context.Context,
	events []ports.OutboxEvent,
) error {
	var result error
	for _, event := range events {
		if err := relay.outbox.ReleaseOutboxClaim(
			ctx,
			event.EventID,
			relay.ownerID,
		); err != nil {
			result = errors.Join(result, err)
		}
	}
	return result
}

func (relay *OutboxRelay) recordSuccessfulScan() {
	profileProposalOutboxDrainTotal.WithLabelValues("succeeded").Inc()
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastSuccessfulScan = relay.now().UTC()
	relay.lastFailure = nil
}

func (relay *OutboxRelay) recordFailure(err error) {
	profileProposalOutboxDrainTotal.WithLabelValues("failed").Inc()
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastFailure = err
}

func isProfileUpdateProposalPublicEvent(eventType string) bool {
	switch eventType {
	case proposalevent.ProfileUpdateProposalCreated,
		proposalevent.ProfileUpdateProposalConfirmed,
		proposalevent.ProfileUpdateProposalApplyStarted,
		proposalevent.ProfileUpdateProposalApplied,
		proposalevent.ProfileUpdateProposalRollbackStarted,
		proposalevent.ProfileUpdateProposalRollbackAborted,
		proposalevent.ProfileUpdateProposalRolledBack,
		proposalevent.ProfileUpdateProposalRejected,
		proposalevent.ProfileUpdateProposalExpired:
		return true
	default:
		return false
	}
}
