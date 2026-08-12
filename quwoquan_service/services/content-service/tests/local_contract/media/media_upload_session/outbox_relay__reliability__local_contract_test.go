// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
package media_upload_session_test

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	uploadapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	uploadports "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
	uploadmessaging "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/messaging"
)

type uploadOutboxFixture struct {
	event      uploadports.OutboxEvent
	available  bool
	marked     int
	retried    int
	claimOwner string
}

func (fixture *uploadOutboxFixture) ClaimPendingOutbox(
	_ context.Context, owner string, _ time.Time, _ time.Duration,
) (uploadports.OutboxEvent, bool, error) {
	fixture.claimOwner = owner
	return fixture.event, fixture.available, nil
}

func (fixture *uploadOutboxFixture) MarkOutboxPublished(
	_ context.Context, _ string, owner string, _ time.Time,
) error {
	if owner != fixture.claimOwner {
		return uploadports.ErrOutboxClaimLost
	}
	fixture.marked++
	fixture.available = false
	return nil
}

func (fixture *uploadOutboxFixture) ScheduleOutboxRetry(
	_ context.Context, _ string, owner string, _ time.Time, _ string,
) error {
	if owner != fixture.claimOwner {
		return uploadports.ErrOutboxClaimLost
	}
	fixture.retried++
	fixture.available = false
	return nil
}

type uploadTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *uploadTransportFixture) AppendDurable(
	_ context.Context, message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *uploadTransportFixture) SetDurableRetention(
	_ context.Context, _ string, retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestMediaUploadRelayDoesNotAdvanceBeforeDurablePublish(t *testing.T) {
	now := time.Date(2026, 8, 5, 11, 30, 0, 0, time.UTC)
	event := uploadports.OutboxEvent{
		EventID: "upload-1:1", EventType: "content.media_upload.initialized",
		AggregateType: "MediaUploadSession", AggregateID: "upload-1", AggregateVersion: 1,
		Payload:    []byte(`{"sessionId":"upload-1","ownerId":"account-1","objectKey":"uploads/account-1/object","expiresAt":"2026-08-05T11:45:00Z"}`),
		OccurredAt: now, AttemptCount: 1,
	}
	outbox := &uploadOutboxFixture{event: event, available: true}
	transport := &uploadTransportFixture{fail: true}
	publisher, err := uploadmessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := uploadapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.marked != 0 || outbox.retried != 1 || relay.Healthy(context.Background(), time.Minute) == nil {
		t.Fatalf("failed publish advanced or remained healthy: marked=%d retried=%d", outbox.marked, outbox.retried)
	}
	outbox.available = true
	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.marked != 1 || transport.message.Stream != uploadmessaging.MediaUploadSessionEventStream ||
		fields["aggregateId"] != event.AggregateID || fields["payload"] == "" || transport.retention <= 0 {
		t.Fatalf("media upload delivery mismatch: marked=%d stream=%q fields=%v retention=%s", outbox.marked, transport.message.Stream, fields, transport.retention)
	}
	if err := relay.Healthy(context.Background(), time.Minute); err != nil {
		t.Fatalf("Healthy() after recovery error = %v", err)
	}
}

func TestMediaUploadRelayClearsTransientFailureAfterSuccessfulEmptyScan(t *testing.T) {
	outbox := &uploadOutboxFixture{
		event: uploadports.OutboxEvent{
			EventID: "invalid-upload-event",
		},
		available: true,
	}
	publisher, err := uploadmessaging.NewEventPublisher(&uploadTransportFixture{})
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := uploadapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if _, err := relay.Drain(context.Background(), 1); err == nil {
		t.Fatal("invalid event Drain() succeeded")
	}
	if err := relay.Healthy(context.Background(), time.Minute); err == nil {
		t.Fatal("relay remained healthy after delivery failure")
	}
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 0 {
		t.Fatalf("empty recovery Drain() = (%d, %v), want (0, nil)", count, err)
	}
	if err := relay.Healthy(context.Background(), time.Minute); err != nil {
		t.Fatalf("Healthy() after empty recovery scan error = %v", err)
	}
}
