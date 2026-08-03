package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	domaineventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/eventing"
	timelineapplication "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/application"
)

const (
	ConsumerGroup          = "travel-service-trip-timeline-map-projector"
	projectionDLQSuffix    = ".travel-projection.dlq"
	projectionDLQRetention = 7 * 24 * time.Hour
)

var ErrInvalidProjectionEventContract = errors.New("invalid Travel projection event contract")

type Projector interface {
	Apply(context.Context, timelineapplication.SourceEvent) error
}

type Consumer struct {
	transport runtimemessaging.DurableDeliveryTransport
	projector Projector
	consumer  string
	logger    *slog.Logger

	mu          sync.RWMutex
	lastScan    time.Time
	lastFailure error
}

func NewConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	projector Projector,
	consumer string,
	logger *slog.Logger,
) (*Consumer, error) {
	consumer = strings.TrimSpace(consumer)
	if transport == nil || projector == nil {
		return nil, errors.New("Travel projection consumer requires transport and projector")
	}
	if consumer == "" {
		consumer = "travel-projection-worker"
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Consumer{transport: transport, projector: projector, consumer: consumer, logger: logger}, nil
}

func (consumer *Consumer) EnsureGroups(ctx context.Context) error {
	for _, stream := range domaineventing.ProjectionStreams() {
		if err := consumer.transport.EnsureDurableConsumerGroup(ctx, stream, ConsumerGroup, "0"); err != nil {
			return fmt.Errorf("ensure Travel projection group for %s: %w", stream, err)
		}
	}
	return nil
}

func (consumer *Consumer) ProcessOnce(ctx context.Context) (int, error) {
	if consumer == nil || consumer.transport == nil || consumer.projector == nil {
		return 0, errors.New("Travel projection consumer is not configured")
	}
	if err := consumer.EnsureGroups(ctx); err != nil {
		consumer.record(err)
		return 0, err
	}
	processed := 0
	for _, stream := range domaineventing.ProjectionStreams() {
		claimed, _, err := consumer.transport.ReclaimDurable(
			ctx, stream, ConsumerGroup, consumer.consumer, 30*time.Second, "0-0", 50,
		)
		if err != nil {
			consumer.record(err)
			return processed, err
		}
		fresh, err := consumer.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
			Stream: stream, Group: ConsumerGroup, Consumer: consumer.consumer,
			Count: 50, Block: 50 * time.Millisecond,
		})
		if err != nil {
			consumer.record(err)
			return processed, err
		}
		for _, delivery := range uniqueDeliveries(claimed, fresh) {
			if err := consumer.process(ctx, stream, delivery); err != nil {
				consumer.record(err)
				return processed, err
			}
			processed++
		}
	}
	consumer.record(nil)
	return processed, nil
}

func (consumer *Consumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(ctx, "Travel projection consume failed", slog.String("error", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *Consumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastScan.IsZero() {
		return errors.New("Travel projection consumer has not completed a scan")
	}
	if consumer.lastFailure != nil {
		return consumer.lastFailure
	}
	if time.Since(consumer.lastScan) > maxStaleness {
		return errors.New("Travel projection consumer heartbeat is stale")
	}
	return nil
}

func (consumer *Consumer) process(
	ctx context.Context,
	stream string,
	delivery runtimemessaging.StreamDelivery,
) error {
	event, err := decodeProjectionEvent(stream, delivery.Fields)
	if err == nil {
		err = consumer.projector.Apply(ctx, event)
	}
	if err != nil && errors.Is(err, ErrInvalidProjectionEventContract) {
		dlq := stream + projectionDLQSuffix
		if _, dlqErr := consumer.transport.PublishDeadLetter(ctx, runtimemessaging.DeadLetterMessage{
			SourceStream: stream, DestinationStream: dlq, SourceID: delivery.ID,
			Reason: "invalid_travel_projection_event", Fields: delivery.Fields,
		}); dlqErr != nil {
			return errors.Join(err, dlqErr)
		}
		if retentionErr := consumer.transport.SetDurableRetention(ctx, dlq, projectionDLQRetention); retentionErr != nil {
			return errors.Join(err, retentionErr)
		}
		return consumer.transport.AckDurable(ctx, stream, ConsumerGroup, delivery.ID)
	}
	if err != nil {
		return err
	}
	return consumer.transport.AckDurable(ctx, stream, ConsumerGroup, delivery.ID)
}

func decodeProjectionEvent(
	stream string,
	fields []runtimemessaging.DurableField,
) (timelineapplication.SourceEvent, error) {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[strings.TrimSpace(field.Name)] = strings.TrimSpace(field.Value)
	}
	route, found := domaineventing.RouteForEvent(values["eventType"])
	if !found || route.Stream != strings.TrimSpace(stream) ||
		values["eventId"] == "" || values["aggregateId"] == "" ||
		values["aggregateType"] != route.AggregateType || values["producer"] != "travel-service" {
		return timelineapplication.SourceEvent{}, fmt.Errorf(
			"%w: event identity or route is invalid", ErrInvalidProjectionEventContract,
		)
	}
	var payload struct {
		TripID string `json:"tripId"`
	}
	if err := json.Unmarshal([]byte(values["payloadJson"]), &payload); err != nil || strings.TrimSpace(payload.TripID) == "" {
		return timelineapplication.SourceEvent{}, fmt.Errorf(
			"%w: tripId payload is invalid", ErrInvalidProjectionEventContract,
		)
	}
	return timelineapplication.SourceEvent{
		EventID:   values["eventId"],
		EventType: "travel." + values["eventType"],
		TripID:    strings.TrimSpace(payload.TripID),
	}, nil
}

func uniqueDeliveries(groups ...[]runtimemessaging.StreamDelivery) []runtimemessaging.StreamDelivery {
	seen := map[string]struct{}{}
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, delivery := range group {
			key := strings.TrimSpace(delivery.Stream) + ":" + delivery.ID
			if _, found := seen[key]; found {
				continue
			}
			seen[key] = struct{}{}
			result = append(result, delivery)
		}
	}
	return result
}

func (consumer *Consumer) record(err error) {
	consumer.mu.Lock()
	consumer.lastScan = time.Now().UTC()
	consumer.lastFailure = err
	consumer.mu.Unlock()
}
