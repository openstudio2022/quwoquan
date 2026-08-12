// Package stream consumes Integration durable delivery facts for
// AuthenticationChallenge. It is the only provider-result ingress for OTP.
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
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
)

const (
	externalInteractionResultStream = "events.integration.external_interaction"
	externalInteractionResultGroup  = "user-authentication-challenge-delivery-result"
	externalInteractionPollInterval = 250 * time.Millisecond
)

var errIrrelevantExternalInteractionResult = errors.New(
	"irrelevant external interaction result",
)

type DurableMessageTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

// AuthenticationChallengeDeliveryResultConsumer projects the durable
// ExternalInteractionResultReported fact into the challenge authoritative row.
// ACK happens only after the object CAS commits (or reports a stable no-op).
type AuthenticationChallengeDeliveryResultConsumer struct {
	transport DurableMessageTransport
	commands  challengeapp.CommandFacet
	consumer  string
	logger    *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewAuthenticationChallengeDeliveryResultConsumer(
	transport DurableMessageTransport,
	commands challengeapp.CommandFacet,
	consumer string,
	logger *slog.Logger,
) (*AuthenticationChallengeDeliveryResultConsumer, error) {
	if transport == nil || commands == nil {
		return nil, errors.New(
			"authentication challenge delivery consumer requires transport and commands",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "user-authentication-challenge-delivery-projector"
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &AuthenticationChallengeDeliveryResultConsumer{
		transport: transport,
		commands:  commands,
		consumer:  consumer,
		logger:    logger,
	}, nil
}

func (consumer *AuthenticationChallengeDeliveryResultConsumer) EnsureGroup(
	ctx context.Context,
) error {
	return consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		externalInteractionResultStream,
		externalInteractionResultGroup,
		"0",
	)
}

func (consumer *AuthenticationChallengeDeliveryResultConsumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		externalInteractionResultStream,
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
	fresh, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   externalInteractionResultStream,
			Group:    externalInteractionResultGroup,
			Consumer: consumer.consumer,
			Count:    50,
			Block:    100 * time.Millisecond,
		},
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueDeliveries(claimed, fresh) {
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

func (consumer *AuthenticationChallengeDeliveryResultConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	command, err := decodeExternalInteractionResult(message.Fields)
	if errors.Is(err, errIrrelevantExternalInteractionResult) {
		return consumer.transport.AckDurable(
			ctx,
			externalInteractionResultStream,
			externalInteractionResultGroup,
			message.ID,
		)
	}
	if err != nil {
		return err
	}
	if _, err := consumer.commands.ReportDeliveryResult(ctx, command); err != nil {
		return err
	}
	return consumer.transport.AckDurable(
		ctx,
		externalInteractionResultStream,
		externalInteractionResultGroup,
		message.ID,
	)
}

func decodeExternalInteractionResult(
	fields []runtimemessaging.DurableField,
) (challengeapp.ReportDeliveryResultCommand, error) {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[strings.TrimSpace(field.Name)] = strings.TrimSpace(field.Value)
	}
	if values["eventType"] != "ExternalInteractionResultReported" ||
		values["operation"] != reliabletask.ExternalInteractionOperationSmsOTP ||
		!strings.HasPrefix(values["requestId"], "otp_req_") {
		return challengeapp.ReportDeliveryResultCommand{},
			errIrrelevantExternalInteractionResult
	}
	eventID := values["eventId"]
	requestID := values["requestId"]
	if eventID == "" || requestID == "" {
		return challengeapp.ReportDeliveryResultCommand{},
			errors.New("otp delivery result identity is incomplete")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, values["occurredAt"])
	if err != nil {
		return challengeapp.ReportDeliveryResultCommand{},
			fmt.Errorf("invalid otp delivery result occurredAt: %w", err)
	}
	var status challengemodel.DeliveryStatus
	switch values["status"] {
	case reliabletask.ExternalInteractionStatusAccepted,
		reliabletask.ExternalInteractionStatusPendingDispatch:
		status = challengemodel.DeliveryStatusQueued
	case reliabletask.ExternalInteractionStatusSentUnconfirmed:
		status = challengemodel.DeliveryStatusSentUnconfirmed
	case reliabletask.ExternalInteractionStatusDelivered:
		status = challengemodel.DeliveryStatusDelivered
	case reliabletask.ExternalInteractionStatusFailed,
		reliabletask.ExternalInteractionStatusDeadLetter:
		status = challengemodel.DeliveryStatusFailed
	default:
		return challengeapp.ReportDeliveryResultCommand{}, fmt.Errorf(
			"unsupported otp delivery result status %q",
			values["status"],
		)
	}
	return challengeapp.ReportDeliveryResultCommand{
		EventID:    eventID,
		RequestID:  requestID,
		Status:     status,
		OccurredAt: occurredAt.UTC(),
	}, nil
}

func uniqueDeliveries(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, message := range group {
			key := message.Stream + "\x00" + message.ID
			if _, exists := seen[key]; exists {
				continue
			}
			seen[key] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func (consumer *AuthenticationChallengeDeliveryResultConsumer) Run(
	ctx context.Context,
) {
	ticker := time.NewTicker(externalInteractionPollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"authentication challenge delivery result consume failed",
				slog.String("failureKind", "delivery_result_projection_failed"),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *AuthenticationChallengeDeliveryResultConsumer) Healthy(
	maxStaleness time.Duration,
) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() ||
		time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("authentication challenge delivery consumer heartbeat is stale")
	}
	if consumer.lastFailure != nil {
		return fmt.Errorf(
			"authentication challenge delivery consumer failed: %w",
			consumer.lastFailure,
		)
	}
	return nil
}

func (consumer *AuthenticationChallengeDeliveryResultConsumer) recordSuccess() {
	consumer.mu.Lock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = nil
	consumer.mu.Unlock()
}

func (consumer *AuthenticationChallengeDeliveryResultConsumer) recordFailure(
	err error,
) {
	consumer.mu.Lock()
	consumer.lastFailure = err
	consumer.mu.Unlock()
}
