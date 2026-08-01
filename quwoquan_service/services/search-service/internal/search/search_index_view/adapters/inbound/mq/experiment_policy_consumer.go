package mq

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
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

const (
	ExperimentPolicyStream        = "events.ops.experiment_policy_activated"
	ExperimentPolicyConsumerGroup = "search-service"
	ExperimentPolicyDLQ           = "events.ops.experiment_policy_activated.search.dlq"
	experimentPolicyRetention     = 7 * 24 * time.Hour
)

type ExperimentPolicyRepository interface {
	Apply(context.Context, application.ExperimentPolicy) (application.ExperimentPolicy, bool, error)
}

type ExperimentPolicyConsumer struct {
	transport   runtimemessaging.DurableDeliveryTransport
	repository  ExperimentPolicyRepository
	experiments *application.Experiments
	consumer    string
	logger      *slog.Logger
	mu          sync.RWMutex
	lastScan    time.Time
	lastError   error
}

func NewExperimentPolicyConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	repository ExperimentPolicyRepository,
	experiments *application.Experiments,
	consumer string,
	logger *slog.Logger,
) (*ExperimentPolicyConsumer, error) {
	if transport == nil || repository == nil || experiments == nil {
		return nil, errors.New("search experiment policy consumer requires transport, repository and resolver")
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "search-experiment-policy-projector"
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &ExperimentPolicyConsumer{
		transport: transport, repository: repository, experiments: experiments,
		consumer: consumer, logger: logger,
	}, nil
}

func (c *ExperimentPolicyConsumer) EnsureGroup(ctx context.Context) error {
	return c.transport.EnsureDurableConsumerGroup(
		ctx, ExperimentPolicyStream, ExperimentPolicyConsumerGroup, "0",
	)
}

func (c *ExperimentPolicyConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if err := c.EnsureGroup(ctx); err != nil {
		c.record(err)
		return 0, err
	}
	claimed, _, err := c.transport.ReclaimDurable(
		ctx, ExperimentPolicyStream, ExperimentPolicyConsumerGroup,
		c.consumer, 30*time.Second, "0-0", 50,
	)
	if err != nil {
		c.record(err)
		return 0, err
	}
	fresh, err := c.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream: ExperimentPolicyStream, Group: ExperimentPolicyConsumerGroup,
		Consumer: c.consumer, Count: 50, Block: 200 * time.Millisecond,
	})
	if err != nil {
		c.record(err)
		return 0, err
	}
	processed := 0
	for _, message := range uniquePolicyMessages(claimed, fresh) {
		if err := c.process(ctx, message); err != nil {
			c.record(err)
			return processed, err
		}
		processed++
	}
	c.record(nil)
	return processed, nil
}

func (c *ExperimentPolicyConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		if _, err := c.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			c.logger.ErrorContext(ctx, "search Experiment policy consume failed", slog.String("error", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *ExperimentPolicyConsumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastScan.IsZero() {
		return errors.New("search Experiment policy consumer has not completed a scan")
	}
	if c.lastError != nil {
		return c.lastError
	}
	if time.Since(c.lastScan) > maxStaleness {
		return errors.New("search Experiment policy consumer heartbeat is stale")
	}
	return nil
}

func (c *ExperimentPolicyConsumer) process(ctx context.Context, message runtimemessaging.StreamDelivery) error {
	policy, relevant, err := decodeExperimentPolicy(message.Fields)
	if err == nil && relevant {
		var effective application.ExperimentPolicy
		effective, _, err = c.repository.Apply(ctx, policy)
		if err == nil {
			err = c.experiments.ApplyPolicy(effective)
		}
	}
	if err != nil && errors.Is(err, ErrInvalidExperimentPolicyContract) {
		if _, dlqErr := c.transport.PublishDeadLetter(ctx, runtimemessaging.DeadLetterMessage{
			SourceStream: ExperimentPolicyStream, DestinationStream: ExperimentPolicyDLQ,
			SourceID: message.ID, Reason: "invalid_experiment_policy", Fields: message.Fields,
		}); dlqErr != nil {
			return errors.Join(err, dlqErr)
		}
		if retentionErr := c.transport.SetDurableRetention(ctx, ExperimentPolicyDLQ, experimentPolicyRetention); retentionErr != nil {
			return errors.Join(err, retentionErr)
		}
		return c.transport.AckDurable(ctx, ExperimentPolicyStream, ExperimentPolicyConsumerGroup, message.ID)
	}
	if err != nil {
		return err
	}
	return c.transport.AckDurable(ctx, ExperimentPolicyStream, ExperimentPolicyConsumerGroup, message.ID)
}

var ErrInvalidExperimentPolicyContract = errors.New("invalid ExperimentPolicyActivated contract")

func decodeExperimentPolicy(fields []runtimemessaging.DurableField) (application.ExperimentPolicy, bool, error) {
	values := map[string]string{}
	for _, field := range fields {
		values[field.Name] = strings.TrimSpace(field.Value)
	}
	if values["eventType"] != "ExperimentPolicyActivated" || values["eventId"] == "" || values["producer"] != "product-ops-service" {
		return application.ExperimentPolicy{}, false, fmt.Errorf("%w: event identity is invalid", ErrInvalidExperimentPolicyContract)
	}
	if values["aggregateType"] != "Experiment" || values["experimentId"] == "" {
		return application.ExperimentPolicy{}, false, fmt.Errorf("%w: aggregate identity is invalid", ErrInvalidExperimentPolicyContract)
	}
	var payload struct {
		ID        string                                `json:"id"`
		Version   int64                                 `json:"version"`
		Status    string                                `json:"status"`
		Variants  []application.ExperimentPolicyVariant `json:"variants"`
		StartsAt  string                                `json:"startsAt"`
		EndsAt    string                                `json:"endsAt"`
		UpdatedAt string                                `json:"updatedAt"`
	}
	if err := json.Unmarshal([]byte(values["payloadJson"]), &payload); err != nil {
		return application.ExperimentPolicy{}, false, fmt.Errorf("%w: payload is invalid: %v", ErrInvalidExperimentPolicyContract, err)
	}
	if payload.ID != values["experimentId"] {
		return application.ExperimentPolicy{}, false, fmt.Errorf("%w: payload identity mismatch", ErrInvalidExperimentPolicyContract)
	}
	if payload.ID != application.SearchRankingExperimentID {
		return application.ExperimentPolicy{}, false, nil
	}
	policy, err := application.CanonicalExperimentPolicy(application.ExperimentPolicy{
		ID: payload.ID, Revision: payload.Version, Status: payload.Status,
		Variants: payload.Variants, StartsAt: payload.StartsAt, EndsAt: payload.EndsAt,
		UpdatedAt: payload.UpdatedAt,
	})
	if err != nil {
		return application.ExperimentPolicy{}, false, fmt.Errorf("%w: %v", ErrInvalidExperimentPolicyContract, err)
	}
	return policy, true, nil
}

func uniquePolicyMessages(groups ...[]runtimemessaging.StreamDelivery) []runtimemessaging.StreamDelivery {
	seen := map[string]struct{}{}
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, message := range group {
			if _, ok := seen[message.ID]; ok {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func (c *ExperimentPolicyConsumer) record(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastScan = time.Now().UTC()
	c.lastError = err
}
