package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
)

type credentialAuditOutbox struct {
	event       bindingports.SecurityAuditEvent
	found       bool
	published   string
	retryDigest string
}

func (outbox *credentialAuditOutbox) ClaimPendingOutbox(
	context.Context,
	time.Time,
	time.Duration,
) (bindingports.SecurityAuditEvent, bool, error) {
	if !outbox.found {
		return bindingports.SecurityAuditEvent{}, false, nil
	}
	outbox.found = false
	return outbox.event, true, nil
}

func (outbox *credentialAuditOutbox) MarkOutboxPublished(
	_ context.Context,
	eventID string,
	_ time.Time,
	publishedAt time.Time,
) error {
	if publishedAt.IsZero() {
		return errors.New("publishedAt is required")
	}
	outbox.published = eventID
	return nil
}

func (outbox *credentialAuditOutbox) ScheduleOutboxRetry(
	_ context.Context,
	_ string,
	_ time.Time,
	_ time.Time,
	failureDigest string,
) error {
	outbox.retryDigest = failureDigest
	return nil
}

type credentialAuditPublisher struct {
	eventID string
	err     error
}

func (publisher *credentialAuditPublisher) PublishCredentialAudit(
	_ context.Context,
	event bindingports.SecurityAuditEvent,
) error {
	publisher.eventID = event.EventID
	return publisher.err
}

func TestCredentialBindingSecurityAuditRelayPublishesBeforeCheckpoint(t *testing.T) {
	claimUntil := time.Now().UTC().Add(time.Minute)
	outbox := &credentialAuditOutbox{
		found: true,
		event: bindingports.SecurityAuditEvent{
			EventID: "credential-event-1", AggregateID: "binding-1",
			AggregateVersion: 1, EventType: bindingmodel.CredentialBoundEvent,
			PayloadJSON: []byte(`{"id":"binding-1"}`),
			OccurredAt:  time.Now().UTC(), AttemptCount: 1, ClaimUntil: claimUntil,
		},
	}
	publisher := &credentialAuditPublisher{}
	relay, err := bindingapp.NewSecurityAuditRelay(outbox, publisher)
	if err != nil {
		t.Fatal(err)
	}
	published, err := relay.Drain(t.Context(), 10)
	if err != nil || published != 1 {
		t.Fatalf("Drain() published=%d err=%v", published, err)
	}
	if publisher.eventID != "credential-event-1" || outbox.published != "credential-event-1" {
		t.Fatalf("publish=%q checkpoint=%q", publisher.eventID, outbox.published)
	}
}

func TestCredentialBindingSecurityAuditRelayDoesNotCheckpointFailedAppend(t *testing.T) {
	outbox := &credentialAuditOutbox{
		found: true,
		event: bindingports.SecurityAuditEvent{
			EventID: "credential-event-2", AggregateID: "binding-2",
			AggregateVersion: 2, EventType: bindingmodel.CredentialRevokedEvent,
			PayloadJSON: []byte(`{"id":"binding-2"}`),
			OccurredAt:  time.Now().UTC(), AttemptCount: 1,
			ClaimUntil: time.Now().UTC().Add(time.Minute),
		},
	}
	publisher := &credentialAuditPublisher{err: errors.New("durable transport unavailable")}
	relay, err := bindingapp.NewSecurityAuditRelay(outbox, publisher)
	if err != nil {
		t.Fatal(err)
	}
	published, err := relay.Drain(t.Context(), 10)
	if err == nil || published != 0 {
		t.Fatalf("Drain() published=%d err=%v", published, err)
	}
	if outbox.published != "" || outbox.retryDigest == "" {
		t.Fatalf("failed append checkpoint=%q retryDigest=%q", outbox.published, outbox.retryDigest)
	}
}
