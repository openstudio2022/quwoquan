// spec_ref: specs/feature-tree/notification-delivery/notification-delivery-job/spec.md
package application_test

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	deliveryapp "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	deliverymessaging "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/messaging"
)

type deliveryOutboxFixture struct {
	event     deliveryapp.OutboxEvent
	marked    int
	retried   int
	nextRetry time.Time
}

func (fixture *deliveryOutboxFixture) ClaimPendingOutbox(context.Context, string, time.Time, time.Duration) (deliveryapp.OutboxEvent, bool, error) {
	if fixture.marked > 0 {
		return deliveryapp.OutboxEvent{}, false, nil
	}
	fixture.event.AttemptCount++
	return fixture.event, true, nil
}

func (fixture *deliveryOutboxFixture) MarkPublished(context.Context, string, string, time.Time) error {
	fixture.marked++
	return nil
}

func (fixture *deliveryOutboxFixture) SchedulePublicationRetry(_ context.Context, _ string, _ string, next time.Time, digest string) error {
	if digest == "" {
		return errors.New("missing failure digest")
	}
	fixture.retried++
	fixture.nextRetry = next
	return nil
}

type deliveryTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *deliveryTransportFixture) AppendDurable(_ context.Context, message runtimemessaging.DurableMessage) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *deliveryTransportFixture) SetDurableRetention(_ context.Context, _ string, retention time.Duration) error {
	fixture.retention = retention
	return nil
}

func TestNotificationDeliveryJobRelayRetriesWithoutPrematureAcknowledgement(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	outbox := &deliveryOutboxFixture{event: deliveryapp.OutboxEvent{
		EventID: "job-1:0001:created", EventType: "NotificationDeliveryJobCreated",
		AggregateID: "job-1", AggregateVersion: 1,
		Payload:    map[string]string{"id": "job-1"},
		OccurredAt: now,
	}}
	transport := &deliveryTransportFixture{fail: true}
	publisher, err := deliverymessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := deliveryapp.NewOutboxRelay(outbox, publisher, "notification-delivery-test")
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}

	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.marked != 0 || outbox.retried != 1 || outbox.nextRetry.IsZero() {
		t.Fatalf("failed publish state: marked=%d retried=%d nextRetry=%s", outbox.marked, outbox.retried, outbox.nextRetry)
	}

	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.marked != 1 || transport.message.Stream != deliverymessaging.NotificationDeliveryJobEventStream ||
		fields["eventId"] != outbox.event.EventID || fields["aggregateVersion"] != "1" ||
		transport.retention != deliverymessaging.NotificationDeliveryJobEventStreamRetention {
		t.Fatalf("NotificationDeliveryJob delivery mismatch: marked=%d stream=%q fields=%v retention=%s", outbox.marked, transport.message.Stream, fields, transport.retention)
	}
}

func TestNotificationDeliveryPublisherEmitsEveryCanonicalPayloadField(t *testing.T) {
	providerFields := []string{
		"jobId", "callId", "deviceId", "deliveryKey", "action", "attemptId", "requestId",
		"operation", "provider", "providerRequestDigest", "resultStatus", "recoveryAction", "occurredAt", "jobStatus",
	}
	contractFields := map[string][]string{
		"NotificationDeliveryJobCreated":                      {"id"},
		"NotificationDeliveryJobDispatched":                   {"id"},
		"NotificationDeliveryJobDeadLettered":                 {"id"},
		"NotificationDeliveryJobRecovered":                    {"id"},
		"IncomingCallRealtimeDispatched":                      {"id", "callId", "targetPersonaId", "deviceId", "deliveryKey", "ackDeadlineAt"},
		"IncomingCallRealtimePresented":                       {"id", "callId", "deviceId", "deliveryKey", "presentedAt"},
		"IncomingCallPushQueued":                              {"id", "callId", "deviceId", "deliveryKey", "expiresAt"},
		"IncomingCallExternalInteractionAccepted":             {"id", "callId", "deviceId", "deliveryKey", "externalInteractionId", "externalInteractionAcceptedAt"},
		"IncomingCallSentUnconfirmed":                         providerFields,
		"IncomingCallProviderResultRecorded":                  providerFields,
		"IncomingCallDeliveryCancelled":                       {"id", "callId", "deviceId", "deliveryKey", "status"},
		"IncomingCallCancellationPushSubmitted":               {"id", "callId", "deviceId", "deliveryKey", "cancellationExternalInteractionId", "cancellationPushSubmittedAt"},
		"IncomingCallCancellationExternalInteractionAccepted": {"id", "callId", "deviceId", "deliveryKey", "cancellationExternalInteractionId", "cancellationExternalInteractionAcceptedAt"},
		"IncomingCallCancellationProviderResultRecorded":      providerFields,
		"IncomingCallCancellationRealtimeDispatched":          {"id", "callId", "targetPersonaId", "cancellationEventId", "cancellationRealtimeDispatchedAt"},
	}
	for eventType, fields := range contractFields {
		t.Run(eventType, func(t *testing.T) {
			payload := map[string]string{"notContracted": "must be filtered"}
			want := make(map[string]string, len(fields))
			for _, field := range fields {
				value := field + "-value"
				payload[field] = value
				want[field] = value
			}
			transport := &deliveryTransportFixture{}
			publisher, err := deliverymessaging.NewEventPublisher(transport)
			if err != nil {
				t.Fatalf("NewEventPublisher() error = %v", err)
			}
			err = publisher.PublishNotificationDeliveryJob(context.Background(), deliveryapp.OutboxEvent{
				EventID: "event-1", EventType: eventType, AggregateID: "job-1", AggregateVersion: 2,
				Payload: payload, OccurredAt: time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC),
			})
			if err != nil {
				t.Fatalf("PublishNotificationDeliveryJob() error = %v", err)
			}
			messageFields := runtimemessaging.DurableFieldMap(transport.message.Fields)
			var got map[string]string
			if err := json.Unmarshal([]byte(messageFields["payload"]), &got); err != nil {
				t.Fatalf("decode canonical payload: %v", err)
			}
			if !reflect.DeepEqual(got, want) {
				t.Fatalf("payload = %#v, want %#v", got, want)
			}
		})
	}
}

func TestNotificationDeliveryPublisherRejectsIncompleteCanonicalPayload(t *testing.T) {
	transport := &deliveryTransportFixture{}
	publisher, err := deliverymessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	err = publisher.PublishNotificationDeliveryJob(context.Background(), deliveryapp.OutboxEvent{
		EventID: "event-1", EventType: "IncomingCallRealtimeDispatched",
		AggregateID: "job-1", AggregateVersion: 2,
		Payload: map[string]string{"id": "job-1"}, OccurredAt: time.Now().UTC(),
	})
	if err == nil || transport.message.Stream != "" {
		t.Fatalf("incomplete PublishNotificationDeliveryJob() = %v, stream=%q", err, transport.message.Stream)
	}
}
