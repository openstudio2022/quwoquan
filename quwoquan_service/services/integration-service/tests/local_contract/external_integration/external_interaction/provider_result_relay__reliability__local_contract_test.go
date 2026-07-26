// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-005

package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/resultrelay"
)

type resultOutboxStoreFixture struct {
	record       reliabletask.ExternalInteractionResultOutboxRecord
	available    bool
	releaseCount int
	ackCount     int
}

func (store *resultOutboxStoreFixture) LeaseNextExternalInteractionResultOutbox(
	context.Context,
	string,
	time.Duration,
) (reliabletask.ExternalInteractionResultOutboxRecord, bool, error) {
	if !store.available {
		return reliabletask.ExternalInteractionResultOutboxRecord{}, false, nil
	}
	return store.record, true, nil
}

func (store *resultOutboxStoreFixture) AcknowledgeExternalInteractionResultOutbox(
	_ context.Context,
	eventID string,
	_ string,
) (bool, error) {
	if eventID != store.record.EventID {
		return false, nil
	}
	store.ackCount++
	store.available = false
	return true, nil
}

func (store *resultOutboxStoreFixture) ReleaseExternalInteractionResultOutboxLease(
	_ context.Context,
	eventID string,
	_ string,
) error {
	if eventID == store.record.EventID {
		store.releaseCount++
	}
	return nil
}

type resultTransportFixture struct {
	failAppend bool
	messages   []runtimemessaging.DurableMessage
	retention  time.Duration
}

func (transport *resultTransportFixture) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.messages = append(transport.messages, message)
	if transport.failAppend {
		return "", errors.New("redis unavailable")
	}
	return "1-0", nil
}

func (transport *resultTransportFixture) SetDurableRetention(
	_ context.Context,
	_ string,
	retention time.Duration,
) error {
	transport.retention = retention
	return nil
}

func TestProviderResultRelayRetriesTransportWithoutProviderCredentials(t *testing.T) {
	store := &resultOutboxStoreFixture{
		available: true,
		record: reliabletask.ExternalInteractionResultOutboxRecord{
			EventID:               "attempt-1",
			RequestID:             "request-1",
			Operation:             reliabletask.ExternalInteractionOperationPush,
			ResultStatus:          reliabletask.ExternalInteractionStatusSentUnconfirmed,
			Provider:              "apns_voip",
			ProviderRequestDigest: "sha256:provider-request",
			RecoveryAction:        "none",
			OccurredAt:            time.Date(2026, 7, 26, 8, 0, 0, 0, time.UTC),
		},
	}
	transport := &resultTransportFixture{failAppend: true}
	relay, err := resultrelay.New(store, transport, nil)
	if err != nil {
		t.Fatalf("new provider result relay: %v", err)
	}
	if worked, err := relay.ProcessOnce(context.Background()); !worked || err == nil {
		t.Fatalf("failed append = (%v, %v), want work with error", worked, err)
	}
	if store.releaseCount != 1 || store.ackCount != 0 {
		t.Fatalf("failed append store state release=%d ack=%d", store.releaseCount, store.ackCount)
	}

	transport.failAppend = false
	if worked, err := relay.ProcessOnce(context.Background()); !worked || err != nil {
		t.Fatalf("replayed append = (%v, %v), want success", worked, err)
	}
	if store.ackCount != 1 || transport.retention != resultrelay.ResultStreamRetention {
		t.Fatalf("successful append ack=%d retention=%s", store.ackCount, transport.retention)
	}
	if len(transport.messages) != 2 {
		t.Fatalf("transport append count = %d, want replayed delivery", len(transport.messages))
	}
	fields := map[string]string{}
	for _, field := range transport.messages[1].Fields {
		fields[field.Name] = field.Value
	}
	if fields["eventId"] != "attempt-1" || fields["attemptId"] != "attempt-1" {
		t.Fatalf("result event does not preserve deterministic attempt id: %#v", fields)
	}
	if fields["providerRequestDigest"] != "sha256:provider-request" {
		t.Fatalf("result event lacks provider request digest: %#v", fields)
	}
	for _, forbidden := range []string{"providerRequestId", "callbackUrl", "payload", "secret"} {
		if _, found := fields[forbidden]; found {
			t.Fatalf("result event leaks forbidden field %s", forbidden)
		}
	}
}
