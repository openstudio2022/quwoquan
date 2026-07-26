package stream

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
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
)

const (
	RTCCallRingingStream  = "events.rtc.call_ringing"
	RTCCallAnsweredStream = "events.rtc.call_answered"
	RTCCallEndedStream    = "events.rtc.call_ended"

	rtcIncomingCallConsumerGroup = "notification-incoming-call"
	rtcIncomingCallDLQSuffix     = ".notification-dlq"
)

type RTCIncomingCallConsumer struct {
	transport   DurableMessageTransport
	coordinator *application.IncomingCallDeliveryCoordinator
	consumer    string
	logger      *slog.Logger
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewRTCIncomingCallConsumer(
	transport DurableMessageTransport,
	coordinator *application.IncomingCallDeliveryCoordinator,
	consumer string,
	logger *slog.Logger,
) (*RTCIncomingCallConsumer, error) {
	if transport == nil || coordinator == nil {
		return nil, errors.New(
			"rtc incoming call consumer requires message transport and coordinator",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "notification-incoming-call-worker"
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &RTCIncomingCallConsumer{
		transport:   transport,
		coordinator: coordinator,
		consumer:    consumer,
		logger:      logger,
	}, nil
}

func (c *RTCIncomingCallConsumer) EnsureGroups(ctx context.Context) error {
	for _, stream := range []string{
		RTCCallRingingStream,
		RTCCallAnsweredStream,
		RTCCallEndedStream,
	} {
		if err := c.transport.EnsureDurableConsumerGroup(
			ctx,
			stream,
			rtcIncomingCallConsumerGroup,
			"0",
		); err != nil {
			return err
		}
	}
	return nil
}

func (c *RTCIncomingCallConsumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if err := c.EnsureGroups(ctx); err != nil {
		c.recordFailure(err)
		return 0, err
	}
	processed := 0
	for _, stream := range []string{
		RTCCallRingingStream,
		RTCCallAnsweredStream,
		RTCCallEndedStream,
	} {
		claimed, _, err := c.transport.ReclaimDurable(
			ctx,
			stream,
			rtcIncomingCallConsumerGroup,
			c.consumer,
			30*time.Second,
			"0-0",
			50,
		)
		if err != nil {
			c.recordFailure(err)
			return processed, err
		}
		fresh, err := c.transport.ReadDurable(
			ctx,
			runtimemessaging.StreamReadRequest{
				Stream:   stream,
				Group:    rtcIncomingCallConsumerGroup,
				Consumer: c.consumer,
				Count:    50,
				Block:    10 * time.Millisecond,
			},
		)
		if err != nil {
			c.recordFailure(err)
			return processed, err
		}
		for _, message := range uniqueStreamMessages(claimed, fresh) {
			if err := c.processMessage(ctx, stream, message); err != nil {
				c.recordFailure(err)
				return processed, err
			}
			processed++
		}
	}
	c.recordSuccess()
	return processed, nil
}

func (c *RTCIncomingCallConsumer) Run(
	ctx context.Context,
	interval time.Duration,
) {
	if interval <= 0 {
		interval = 100 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := c.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			c.logger.ErrorContext(
				ctx,
				"rtc incoming call consume failed",
				slog.String("error", err.Error()),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *RTCIncomingCallConsumer) Healthy(
	maxStaleness time.Duration,
) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastSuccess.IsZero() {
		return errors.New(
			"rtc incoming call consumer has not completed a scan",
		)
	}
	if c.lastFailure != nil {
		return c.lastFailure
	}
	if time.Since(c.lastSuccess) > maxStaleness {
		return errors.New("rtc incoming call consumer heartbeat is stale")
	}
	return nil
}

func (c *RTCIncomingCallConsumer) processMessage(
	ctx context.Context,
	stream string,
	message runtimemessaging.StreamDelivery,
) error {
	values := durableFieldsToMap(message.Fields)
	eventType := strings.TrimSpace(values["eventType"])
	var err error
	switch eventType {
	case "CallRinging":
		var event notification.IncomingCallRingingEvent
		event, err = decodeRingingEvent(values)
		if err == nil {
			err = c.coordinator.HandleRinging(ctx, event)
		}
	case "CallAnswered", "CallEnded":
		var event notification.IncomingCallCancellationEvent
		event, err = decodeCancellationEvent(eventType, values)
		if err == nil {
			err = c.coordinator.HandleCancellation(ctx, event)
		}
	default:
		err = fmt.Errorf("unsupported RTC event type %q", eventType)
	}
	if err != nil {
		if isInvalidRTCContract(err) {
			if _, dlqErr := c.transport.AppendDurable(
				ctx,
				runtimemessaging.DurableMessage{
					Stream: stream + rtcIncomingCallDLQSuffix,
					Fields: []runtimemessaging.DurableField{
						{Name: "eventId", Value: values["eventId"]},
						{Name: "sourceStreamId", Value: message.ID},
						{Name: "reason", Value: err.Error()},
					},
				},
			); dlqErr != nil {
				return errors.Join(err, dlqErr)
			}
			return c.transport.AckDurable(
				ctx,
				stream,
				rtcIncomingCallConsumerGroup,
				message.ID,
			)
		}
		return err
	}
	return c.transport.AckDurable(
		ctx,
		stream,
		rtcIncomingCallConsumerGroup,
		message.ID,
	)
}

type rtcCallEventEnvelope struct {
	CallID  string                                `json:"callId"`
	ActorID string                                `json:"actorId"`
	Payload notification.IncomingCallRingingEvent `json:"payload"`
}

func decodeRingingEvent(
	values map[string]string,
) (notification.IncomingCallRingingEvent, error) {
	rawPayload := []byte(values["payloadJson"])
	var envelope rtcCallEventEnvelope
	if err := json.Unmarshal(
		rawPayload,
		&envelope,
	); err != nil {
		return notification.IncomingCallRingingEvent{},
			fmt.Errorf("invalid RTC CallRinging payload: %w", err)
	}
	var contractEnvelope struct {
		Payload map[string]json.RawMessage `json:"payload"`
	}
	if err := json.Unmarshal(rawPayload, &contractEnvelope); err != nil {
		return notification.IncomingCallRingingEvent{},
			fmt.Errorf("invalid RTC CallRinging contract: %w", err)
	}
	for _, field := range []string{
		"eventId",
		"callId",
		"targetPersonaId",
		"callType",
		"callerName",
		"callerAvatarUrl",
		"sourceLabel",
		"trustRelation",
		"expiresAt",
		"deliveryKey",
	} {
		if _, exists := contractEnvelope.Payload[field]; !exists {
			return notification.IncomingCallRingingEvent{},
				fmt.Errorf(
					"invalid RTC CallRinging missing required field %s",
					field,
				)
		}
	}
	event := envelope.Payload
	if event.EventID == "" {
		event.EventID = strings.TrimSpace(values["eventId"])
	}
	if event.CallID == "" {
		event.CallID = strings.TrimSpace(envelope.CallID)
	}
	if event.EventID == "" ||
		event.CallID == "" ||
		event.TargetPersonaID == "" ||
		event.DeliveryKey == "" {
		return notification.IncomingCallRingingEvent{},
			errors.New("invalid RTC CallRinging required fields")
	}
	if streamEventID := strings.TrimSpace(values["eventId"]); streamEventID != "" && streamEventID != event.EventID {
		return notification.IncomingCallRingingEvent{},
			errors.New("invalid RTC CallRinging eventId mismatch")
	}
	return event, nil
}

func decodeCancellationEvent(
	eventType string,
	values map[string]string,
) (notification.IncomingCallCancellationEvent, error) {
	var envelope rtcCallEventEnvelope
	if err := json.Unmarshal(
		[]byte(values["payloadJson"]),
		&envelope,
	); err != nil {
		return notification.IncomingCallCancellationEvent{},
			fmt.Errorf("invalid RTC cancellation payload: %w", err)
	}
	event := notification.IncomingCallCancellationEvent{
		EventID:   strings.TrimSpace(values["eventId"]),
		EventType: eventType,
		CallID:    strings.TrimSpace(envelope.CallID),
		ActorID:   strings.TrimSpace(envelope.ActorID),
	}
	if raw := strings.TrimSpace(values["occurredAt"]); raw != "" {
		event.OccurredAt, _ = time.Parse(time.RFC3339Nano, raw)
	}
	if event.EventID == "" || event.CallID == "" {
		return notification.IncomingCallCancellationEvent{},
			errors.New("invalid RTC cancellation required fields")
	}
	return event, nil
}

func isInvalidRTCContract(err error) bool {
	message := strings.ToLower(err.Error())
	return strings.Contains(message, "invalid rtc") ||
		strings.Contains(message, "unsupported rtc") ||
		strings.Contains(message, "deliverykey is not canonical") ||
		strings.Contains(message, " is required")
}

func (c *RTCIncomingCallConsumer) recordSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastSuccess = time.Now().UTC()
	c.lastFailure = nil
}

func (c *RTCIncomingCallConsumer) recordFailure(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastFailure = err
}
