// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
// readiness_case: record-external-interaction-result-local
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	application "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

type externalInteractionResultStoreStub struct {
	event notification.ExternalInteractionResultEvent
	at    time.Time
}

func (s *externalInteractionResultStoreStub) ApplyExternalInteractionResult(
	_ context.Context,
	event notification.ExternalInteractionResultEvent,
	at time.Time,
) error {
	s.event = event
	s.at = at
	return nil
}

func TestExternalInteractionResultRecorderPreservesTypedProviderReceipt(t *testing.T) {
	store := &externalInteractionResultStoreStub{}
	recorder, err := application.NewExternalInteractionResultRecorder(store)
	if err != nil {
		t.Fatalf("construct recorder: %v", err)
	}
	occurredAt := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	event := notification.ExternalInteractionResultEvent{
		AttemptID:             "attempt-notification-local-1",
		RequestID:             "incoming-call-request-local-1",
		Operation:             reliabletask.ExternalInteractionOperationPush,
		Status:                reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:              "apns_voip",
		ProviderRequestDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		RecoveryAction:        "none",
		OccurredAt:            occurredAt,
	}
	if err := recorder.RecordExternalInteractionResult(t.Context(), event, occurredAt); err != nil {
		t.Fatalf("record external interaction result: %v", err)
	}
	if store.event != event || !store.at.Equal(occurredAt) {
		t.Fatalf("typed provider receipt drifted: event=%+v at=%s", store.event, store.at)
	}
}
