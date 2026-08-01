package stream

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
)

const (
	AssignmentObservedStream        = "events.ops.experiment_assignment_observed"
	AssignmentObservedConsumerGroup = "product-ops-service"
	AssignmentObservedDLQ           = "events.ops.experiment_assignment_observed.product_ops.dlq"
	assignmentObservedRetention     = 7 * 24 * time.Hour
)

type Consumer struct {
	transport runtimemessaging.DurableDeliveryTransport
	facade    *assignmentapp.Facade
	consumer  string
	logger    *slog.Logger
	mu        sync.RWMutex
	lastScan  time.Time
	lastError error
}

func NewConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	facade *assignmentapp.Facade,
	consumer string,
	logger *slog.Logger,
) (*Consumer, error) {
	if transport == nil || facade == nil {
		return nil, errors.New("experiment assignment consumer requires transport and facade")
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "experiment-assignment-projector"
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Consumer{transport: transport, facade: facade, consumer: consumer, logger: logger}, nil
}

func (c *Consumer) EnsureGroup(ctx context.Context) error {
	return c.transport.EnsureDurableConsumerGroup(
		ctx, AssignmentObservedStream, AssignmentObservedConsumerGroup, "0",
	)
}

func (c *Consumer) ProcessOnce(ctx context.Context) (int, error) {
	if err := c.EnsureGroup(ctx); err != nil {
		c.record(err)
		return 0, err
	}
	claimed, _, err := c.transport.ReclaimDurable(
		ctx, AssignmentObservedStream, AssignmentObservedConsumerGroup,
		c.consumer, 30*time.Second, "0-0", 50,
	)
	if err != nil {
		c.record(err)
		return 0, err
	}
	fresh, err := c.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream: AssignmentObservedStream, Group: AssignmentObservedConsumerGroup,
		Consumer: c.consumer, Count: 50, Block: 200 * time.Millisecond,
	})
	if err != nil {
		c.record(err)
		return 0, err
	}
	processed := 0
	for _, message := range uniqueMessages(claimed, fresh) {
		if err := c.process(ctx, message); err != nil {
			c.record(err)
			return processed, err
		}
		processed++
	}
	c.record(nil)
	return processed, nil
}

func (c *Consumer) Run(ctx context.Context) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		if _, err := c.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			c.logger.ErrorContext(ctx, "experiment assignment observation consume failed", slog.String("error", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *Consumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastScan.IsZero() {
		return errors.New("experiment assignment consumer has not completed a scan")
	}
	if c.lastError != nil {
		return c.lastError
	}
	if time.Since(c.lastScan) > maxStaleness {
		return errors.New("experiment assignment consumer heartbeat is stale")
	}
	return nil
}

func (c *Consumer) process(ctx context.Context, message runtimemessaging.StreamDelivery) error {
	observation, err := decodeObservation(message.Fields)
	if err == nil {
		_, _, err = c.facade.AppendObserved(ctx, observation)
	}
	if err != nil && (errors.Is(err, ErrInvalidContract) || errors.Is(err, assignmentapp.ErrInvalidObservation)) {
		if _, dlqErr := c.transport.PublishDeadLetter(ctx, runtimemessaging.DeadLetterMessage{
			SourceStream: AssignmentObservedStream, DestinationStream: AssignmentObservedDLQ,
			SourceID: message.ID, Reason: "invalid_assignment_observation",
			Fields: message.Fields,
		}); dlqErr != nil {
			return errors.Join(err, dlqErr)
		}
		if retentionErr := c.transport.SetDurableRetention(ctx, AssignmentObservedDLQ, assignmentObservedRetention); retentionErr != nil {
			return errors.Join(err, retentionErr)
		}
		return c.transport.AckDurable(ctx, AssignmentObservedStream, AssignmentObservedConsumerGroup, message.ID)
	}
	if err != nil {
		return err
	}
	return c.transport.AckDurable(ctx, AssignmentObservedStream, AssignmentObservedConsumerGroup, message.ID)
}

var ErrInvalidContract = errors.New("invalid ExperimentAssignmentObserved contract")

func decodeObservation(fields []runtimemessaging.DurableField) (assignmentapp.AssignmentObservation, error) {
	values := map[string]string{}
	for _, field := range fields {
		values[field.Name] = strings.TrimSpace(field.Value)
	}
	if values["eventType"] != "ExperimentAssignmentObserved" || values["eventId"] == "" {
		return assignmentapp.AssignmentObservation{}, fmt.Errorf("%w: event identity is missing", ErrInvalidContract)
	}
	if values["producer"] != "recommendation-service" && values["producer"] != "search-service" {
		return assignmentapp.AssignmentObservation{}, fmt.Errorf("%w: producer is not authorized", ErrInvalidContract)
	}
	revision, err := strconv.ParseInt(values["experimentRevision"], 10, 64)
	if err != nil || revision <= 0 {
		return assignmentapp.AssignmentObservation{}, fmt.Errorf("%w: experimentRevision is invalid", ErrInvalidContract)
	}
	assignedAt, err := time.Parse(time.RFC3339Nano, values["assignedAt"])
	if err != nil {
		return assignmentapp.AssignmentObservation{}, fmt.Errorf("%w: assignedAt is invalid", ErrInvalidContract)
	}
	if values["experimentId"] == "" || values["subjectKey"] == "" || values["variant"] == "" {
		return assignmentapp.AssignmentObservation{}, fmt.Errorf("%w: payload fields are missing", ErrInvalidContract)
	}
	return assignmentapp.AssignmentObservation{
		ExperimentID: values["experimentId"], ExperimentRevision: revision,
		SubjectKey: values["subjectKey"], Variant: values["variant"], ObservedAt: assignedAt,
	}, nil
}

func uniqueMessages(groups ...[]runtimemessaging.StreamDelivery) []runtimemessaging.StreamDelivery {
	seen := map[string]struct{}{}
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, message := range group {
			if _, exists := seen[message.ID]; exists {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func (c *Consumer) record(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastScan = time.Now().UTC()
	c.lastError = err
}
