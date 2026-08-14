package gathering

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const gatheringPublicationConsumer = "circle-service-gathering-domain-events"

type OutboxEventPublisher interface {
	PublishGathering(context.Context, ports.OutboxEvent) error
}

type OutboxRelay struct {
	outbox    ports.PublicationOutbox
	publisher OutboxEventPublisher
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewOutboxRelay(
	outbox ports.PublicationOutbox,
	publisher OutboxEventPublisher,
) (*OutboxRelay, error) {
	if outbox == nil || publisher == nil {
		return nil, errors.New("Gathering publication outbox and publisher are required")
	}
	return &OutboxRelay{outbox: outbox, publisher: publisher, now: time.Now}, nil
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	checkpoint, err := relay.outbox.LoadPublicationCheckpoint(ctx, gatheringPublicationConsumer)
	if err != nil {
		relay.recordFailure(err)
		return 0, fmt.Errorf("load Gathering publication checkpoint: %w", err)
	}
	events, err := relay.outbox.ReadPublicationOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		relay.recordFailure(err)
		return 0, fmt.Errorf("read Gathering outbox: %w", err)
	}
	for index, event := range events {
		if err := validateGatheringOutboxEvent(event, checkpoint); err != nil {
			relay.recordFailure(err)
			return index, err
		}
		if err := relay.publisher.PublishGathering(ctx, event); err != nil {
			wrapped := fmt.Errorf("publish Gathering event %s: %w", event.EventID, err)
			relay.recordFailure(wrapped)
			return index, wrapped
		}
		if err := relay.outbox.SavePublicationCheckpoint(
			ctx, gatheringPublicationConsumer, event.Sequence, relay.now().UTC(),
		); err != nil {
			wrapped := fmt.Errorf("checkpoint Gathering event %s: %w", event.EventID, err)
			relay.recordFailure(wrapped)
			return index, wrapped
		}
		checkpoint = event.Sequence
	}
	relay.recordSuccessfulScan(relay.now().UTC())
	return len(events), nil
}

func (relay *OutboxRelay) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = time.Second
	}
	relay.drainAndObserve(ctx)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			relay.drainAndObserve(ctx)
		}
	}
}

func (relay *OutboxRelay) Healthy(_ context.Context, maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	relay.healthMu.RLock()
	lastScan, lastFailure := relay.lastSuccessfulScan, relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return fmt.Errorf("Gathering outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("Gathering outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) drainAndObserve(ctx context.Context) {
	if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
		slog.ErrorContext(ctx, "Gathering outbox drain failed", "err", err)
	}
}

func validateGatheringOutboxEvent(event ports.OutboxEvent, checkpoint int64) error {
	declared := map[string]struct{}{
		gatheringevent.GatheringDraftCreated:             {},
		gatheringevent.GatheringRoomBindingChanged:       {},
		gatheringevent.GatheringPublished:                {},
		gatheringevent.GatheringRevisionAppended:         {},
		gatheringevent.GatheringParticipationChanged:     {},
		gatheringevent.GatheringInvitationChanged:        {},
		gatheringevent.GatheringAdmissionControlChanged:  {},
		gatheringevent.GatheringCancelled:                {},
		gatheringevent.GatheringEndedEarly:               {},
		gatheringevent.GatheringSafetyTerminated:         {},
		gatheringevent.GatheringCompleted:                {},
		gatheringevent.GatheringOutcomeCalculated:        {},
		gatheringevent.GatheringAvailabilityWatchChanged: {},
	}
	if _, ok := declared[event.EventType]; !ok {
		return fmt.Errorf("Gathering event type %q is not declared", event.EventType)
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.Sequence <= checkpoint || event.OccurredAt.IsZero() ||
		len(event.Payload) == 0 || !json.Valid(event.Payload) {
		return errors.New("Gathering outbox event is incomplete or non-monotonic")
	}
	return nil
}

// recordSuccessfulScan 无条件清除失败态：一次成功扫描已证明 checkpoint 与
// outbox 存储链路恢复；空 outbox 的服务不得因瞬时故障永久卡在 unhealthy。
// 若发布链路仍不可用，下一个事件会重新记录失败。
func (relay *OutboxRelay) recordSuccessfulScan(at time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = at
	relay.lastFailure = nil
	relay.healthMu.Unlock()
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastFailure = err
	relay.healthMu.Unlock()
}
