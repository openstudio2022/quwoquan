package stream

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/reliabletask"
	deliveryapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

const (
	ExternalInteractionResultStream       = "events.integration.external_interaction"
	externalInteractionResultGroup        = "notification-external-interaction-result"
	externalInteractionResultDLQ          = "events.integration.external_interaction.notification-dlq"
	externalInteractionResultMaxAttempts  = int64(5)
	externalInteractionResultRetention    = 7 * 24 * time.Hour
	externalInteractionResultPollInterval = 250 * time.Millisecond
)

var errIrrelevantExternalInteractionResult = errors.New("irrelevant external interaction result")

type ExternalInteractionResultConsumer struct {
	transport DurableMessageTransport
	recorder  deliveryapplication.ExternalInteractionResultRecorder
	failures  InteractionFailureStore
	consumer  string
	logger    *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewExternalInteractionResultConsumer(
	transport DurableMessageTransport,
	recorder deliveryapplication.ExternalInteractionResultRecorder,
	failures InteractionFailureStore,
	consumer string,
	logger *slog.Logger,
) (*ExternalInteractionResultConsumer, error) {
	if transport == nil || recorder == nil || failures == nil {
		return nil, errors.New(
			"external interaction result consumer requires transport, recorder, and failure store",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "notification-external-result-projector"
	}
	return &ExternalInteractionResultConsumer{
		transport: transport, recorder: recorder, failures: failures,
		consumer: consumer, logger: logger,
	}, nil
}

func (consumer *ExternalInteractionResultConsumer) EnsureGroup(ctx context.Context) error {
	return consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		ExternalInteractionResultStream,
		externalInteractionResultGroup,
		"0",
	)
}

func (consumer *ExternalInteractionResultConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		ExternalInteractionResultStream,
		externalInteractionResultGroup,
		consumer.consumer,
		30*time.Second,
		"0-0",
		50,
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream: ExternalInteractionResultStream, Group: externalInteractionResultGroup,
		Consumer: consumer.consumer, Count: 50, Block: 100 * time.Millisecond,
	})
	if err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueStreamMessages(claimed, fresh) {
		if err := consumer.processMessage(ctx, message); err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		processed++
	}
	if firstErr != nil {
		consumer.recordFailure(firstErr)
		return processed, firstErr
	}
	consumer.recordSuccess()
	return processed, nil
}

func (consumer *ExternalInteractionResultConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	deadLettered, err := consumer.failures.IsInteractionDeadLettered(
		ctx,
		ExternalInteractionResultStream,
		message.ID,
	)
	if err != nil {
		return err
	}
	if deadLettered {
		// The DLQ holds only a privacy-safe reference. Keep the source PEL
		// unacknowledged so a controlled recovery can replay its original
		// payload without reconstructing a second message.
		return nil
	}
	event, err := decodeExternalInteractionResult(message.Fields)
	if errors.Is(err, errIrrelevantExternalInteractionResult) {
		return consumer.ackAndClear(ctx, message.ID)
	}
	if err == nil {
		err = consumer.recorder.RecordExternalInteractionResult(
			ctx,
			event,
			time.Now().UTC(),
		)
	}
	if err != nil {
		attempts, recordErr := consumer.failures.RecordInteractionFailure(
			ctx,
			ExternalInteractionResultStream,
			message.ID,
			durableFieldValue(message.Fields, "eventId"),
			"external_result_projection_failed",
			err,
		)
		if recordErr != nil {
			return recordErr
		}
		if attempts < externalInteractionResultMaxAttempts {
			return fmt.Errorf("external interaction result attempt %d: %w", attempts, err)
		}
		if _, dlqErr := consumer.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
			Stream: externalInteractionResultDLQ,
			Fields: interactionDLQFields(
				ExternalInteractionResultStream,
				message,
				err,
				attempts,
				"external_result_projection_failed",
			),
		}); dlqErr != nil {
			return dlqErr
		}
		if err := consumer.transport.SetDurableRetention(
			ctx,
			externalInteractionResultDLQ,
			externalInteractionResultRetention,
		); err != nil {
			return err
		}
		return consumer.failures.MarkInteractionDeadLettered(
			ctx,
			ExternalInteractionResultStream,
			message.ID,
		)
	}
	return consumer.ackAndClear(ctx, message.ID)
}

// RecoverDeadLetter releases the held source PEL for one new bounded retry
// cycle. It never reconstructs an event from the DLQ, whose payload is
// deliberately privacy-safe and incomplete.
func (consumer *ExternalInteractionResultConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if consumer == nil || consumer.failures == nil {
		return errors.New("external interaction result consumer is not configured")
	}
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return errors.New("external interaction result dead-letter source stream ID is required")
	}
	deadLettered, err := consumer.failures.IsInteractionDeadLettered(
		ctx,
		ExternalInteractionResultStream,
		sourceStreamID,
	)
	if err != nil {
		return fmt.Errorf("verify external interaction result dead-letter state: %w", err)
	}
	if !deadLettered {
		return errors.New("external interaction result source is not dead-lettered")
	}
	return consumer.failures.ClearInteractionFailure(
		ctx,
		ExternalInteractionResultStream,
		sourceStreamID,
	)
}

func (consumer *ExternalInteractionResultConsumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.transport.AckDurable(
		ctx,
		ExternalInteractionResultStream,
		externalInteractionResultGroup,
		messageID,
	); err != nil {
		return err
	}
	return consumer.failures.ClearInteractionFailure(
		ctx,
		ExternalInteractionResultStream,
		messageID,
	)
}

func decodeExternalInteractionResult(
	fields []runtimemessaging.DurableField,
) (deliveryapplication.ExternalInteractionResultEvent, error) {
	values := durableFieldsToMap(fields)
	if strings.TrimSpace(values["eventType"]) != "ExternalInteractionResultReported" ||
		!strings.HasPrefix(strings.TrimSpace(values["requestId"]), "incoming-call-") {
		return deliveryapplication.ExternalInteractionResultEvent{}, errIrrelevantExternalInteractionResult
	}
	for _, forbidden := range []string{"providerRequestId", "callbackUrl", "payload", "secret"} {
		if strings.TrimSpace(values[forbidden]) != "" {
			return deliveryapplication.ExternalInteractionResultEvent{},
				fmt.Errorf("external interaction result contains forbidden field %s", forbidden)
		}
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return deliveryapplication.ExternalInteractionResultEvent{}, fmt.Errorf("invalid result occurredAt: %w", err)
	}
	event := deliveryapplication.ExternalInteractionResultEvent{
		AttemptID: strings.TrimSpace(values["attemptId"]), RequestID: strings.TrimSpace(values["requestId"]),
		Operation: strings.TrimSpace(values["operation"]), Status: strings.TrimSpace(values["status"]),
		Provider: strings.TrimSpace(values["provider"]), ProviderRequestDigest: strings.TrimSpace(values["providerRequestDigest"]),
		NormalizedError: strings.TrimSpace(values["normalizedError"]), RecoveryAction: strings.TrimSpace(values["recoveryAction"]),
		OccurredAt: occurredAt.UTC(),
	}
	if event.AttemptID == "" || event.Operation != reliabletask.ExternalInteractionOperationPush ||
		event.Status == "" || event.Provider == "" || event.ProviderRequestDigest == "" ||
		event.RecoveryAction == "" {
		return deliveryapplication.ExternalInteractionResultEvent{}, errors.New("external interaction result is incomplete")
	}
	if strings.TrimSpace(values["eventId"]) != event.AttemptID {
		return deliveryapplication.ExternalInteractionResultEvent{},
			errors.New("external interaction result eventId must equal attemptId")
	}
	switch event.Status {
	case reliabletask.ExternalInteractionStatusSentUnconfirmed:
		if event.RecoveryAction != "none" {
			return deliveryapplication.ExternalInteractionResultEvent{},
				errors.New("accepted provider result must have recoveryAction none")
		}
	case reliabletask.ExternalInteractionStatusFailed:
		if event.RecoveryAction != "retry" && event.RecoveryAction != "escalate" {
			return deliveryapplication.ExternalInteractionResultEvent{},
				errors.New("failed provider result must declare retry or escalate")
		}
	default:
		return deliveryapplication.ExternalInteractionResultEvent{},
			fmt.Errorf("provider result status %q is not permitted", event.Status)
	}
	return event, nil
}

func (consumer *ExternalInteractionResultConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(externalInteractionResultPollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(ctx, "external interaction result consume failed",
				slog.String("errorDigest", irreversibleStreamDigest(err.Error())))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *ExternalInteractionResultConsumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() || time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("external interaction result consumer heartbeat is stale")
	}
	if consumer.lastFailure != nil {
		return fmt.Errorf("external interaction result consumer failed: %w", consumer.lastFailure)
	}
	return nil
}

func (consumer *ExternalInteractionResultConsumer) recordSuccess() {
	consumer.mu.Lock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = nil
	consumer.mu.Unlock()
}

func (consumer *ExternalInteractionResultConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	consumer.lastFailure = err
	consumer.mu.Unlock()
}
