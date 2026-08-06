package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	deliveryapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

const (
	NotificationDeliveryJobEventStream          = "events.notification.delivery_jobs"
	NotificationDeliveryJobEventStreamRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(transport runtimemessaging.DurableRecordAppender) (*EventPublisher, error) {
	if transport == nil {
		return nil, errors.New("NotificationDeliveryJob durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) PublishNotificationDeliveryJob(
	ctx context.Context,
	event deliveryapplication.OutboxEvent,
) error {
	if publisher == nil || publisher.transport == nil {
		return errors.New("NotificationDeliveryJob event publisher is not configured")
	}
	payload, err := canonicalNotificationDeliveryPayload(event.EventType, event.Payload)
	if err != nil {
		return fmt.Errorf("marshal NotificationDeliveryJob event payload: %w", err)
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 || event.OccurredAt.IsZero() {
		return errors.New("NotificationDeliveryJob event identity is invalid")
	}
	if err := runtimemessaging.AppendDurableRecord(
		ctx,
		publisher.transport,
		NotificationDeliveryJobEventStream,
		map[string]string{
			"eventId": event.EventID, "eventType": event.EventType,
			"aggregateType": "NotificationDeliveryJob", "aggregateId": event.AggregateID,
			"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
			"payload":          string(payload), "occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
		},
		NotificationDeliveryJobEventStreamRetention,
	); err != nil {
		return fmt.Errorf("append NotificationDeliveryJob event stream: %w", err)
	}
	return nil
}

func canonicalNotificationDeliveryPayload(eventType string, source map[string]string) ([]byte, error) {
	providerResultFields := []string{
		"jobId", "callId", "deviceId", "deliveryKey", "action", "attemptId", "requestId",
		"operation", "provider", "providerRequestDigest", "resultStatus", "recoveryAction", "occurredAt", "jobStatus",
	}
	fieldsByEvent := map[string][]string{
		"NotificationDeliveryJobCreated":                      {"id"},
		"NotificationDeliveryJobDispatched":                   {"id"},
		"NotificationDeliveryJobDeadLettered":                 {"id"},
		"NotificationDeliveryJobRecovered":                    {"id"},
		"IncomingCallRealtimeDispatched":                      {"id", "callId", "targetPersonaId", "deviceId", "deliveryKey", "ackDeadlineAt"},
		"IncomingCallRealtimePresented":                       {"id", "callId", "deviceId", "deliveryKey", "presentedAt"},
		"IncomingCallPushQueued":                              {"id", "callId", "deviceId", "deliveryKey", "expiresAt"},
		"IncomingCallExternalInteractionAccepted":             {"id", "callId", "deviceId", "deliveryKey", "externalInteractionId", "externalInteractionAcceptedAt"},
		"IncomingCallSentUnconfirmed":                         providerResultFields,
		"IncomingCallProviderResultRecorded":                  providerResultFields,
		"IncomingCallDeliveryCancelled":                       {"id", "callId", "deviceId", "deliveryKey", "status"},
		"IncomingCallCancellationPushSubmitted":               {"id", "callId", "deviceId", "deliveryKey", "cancellationExternalInteractionId", "cancellationPushSubmittedAt"},
		"IncomingCallCancellationExternalInteractionAccepted": {"id", "callId", "deviceId", "deliveryKey", "cancellationExternalInteractionId", "cancellationExternalInteractionAcceptedAt"},
		"IncomingCallCancellationProviderResultRecorded":      providerResultFields,
		"IncomingCallCancellationRealtimeDispatched":          {"id", "callId", "targetPersonaId", "cancellationEventId", "cancellationRealtimeDispatchedAt"},
	}
	fields, supported := fieldsByEvent[eventType]
	if !supported {
		return nil, fmt.Errorf("NotificationDeliveryJob event type %q is not canonical", eventType)
	}
	canonical := make(map[string]string, len(fields))
	for _, field := range fields {
		value, found := source[field]
		if !found {
			return nil, fmt.Errorf("NotificationDeliveryJob %s payload is missing %s", eventType, field)
		}
		canonical[field] = value
	}
	payload, err := json.Marshal(canonical)
	if err != nil {
		return nil, fmt.Errorf("marshal NotificationDeliveryJob event payload: %w", err)
	}
	return payload, nil
}

var _ deliveryapplication.OutboxPublisher = (*EventPublisher)(nil)
