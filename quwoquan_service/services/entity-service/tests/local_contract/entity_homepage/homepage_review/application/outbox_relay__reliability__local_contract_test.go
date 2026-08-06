// spec_ref: specs/feature-tree/shared-services/shared-homepage-network/homepage-review/spec.md
package application_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
	reviewport "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
	reviewmessaging "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/infrastructure/messaging"
)

type reviewOutboxFixture struct {
	event      reviewport.OutboxEvent
	checkpoint string
	saves      int
}

func (fixture *reviewOutboxFixture) ReadAfter(_ context.Context, checkpoint string, _ int) ([]reviewport.OutboxEvent, error) {
	if checkpoint == fixture.event.EventID {
		return nil, nil
	}
	return []reviewport.OutboxEvent{fixture.event}, nil
}

func (fixture *reviewOutboxFixture) LoadCheckpoint(context.Context, string) (string, error) {
	return fixture.checkpoint, nil
}

func (fixture *reviewOutboxFixture) SaveCheckpoint(_ context.Context, _ string, checkpoint string) error {
	fixture.checkpoint = checkpoint
	fixture.saves++
	return nil
}

type reviewTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *reviewTransportFixture) AppendDurable(_ context.Context, message runtimemessaging.DurableMessage) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *reviewTransportFixture) SetDurableRetention(_ context.Context, _ string, retention time.Duration) error {
	fixture.retention = retention
	return nil
}

func TestHomepageReviewOutboxRelayAcknowledgesOnlyAfterDurablePublish(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	outbox := &reviewOutboxFixture{event: reviewport.OutboxEvent{
		EventID: "review-1:1", EventType: "HomepageReviewPublished",
		AggregateID: "review-1", AggregateVersion: 1,
		Payload: []byte(`{"reviewId":"review-1","homepageId":"homepage-1","authorPersonaId":"persona-1",` +
			`"rating":5,"tagRefs":[],"status":"active","createdAt":"2026-08-05T12:00:00Z","version":1}`),
		OccurredAt: now,
	}}
	transport := &reviewTransportFixture{fail: true}
	publisher, err := reviewmessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := reviewapp.NewOutboxRelay(outbox, outbox, publisher, "homepage-review-event-stream-test")
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}

	if count, err := relay.RunOnce(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed RunOnce() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.saves != 0 || outbox.checkpoint != "" {
		t.Fatalf("failed publish advanced checkpoint: saves=%d checkpoint=%q", outbox.saves, outbox.checkpoint)
	}

	transport.fail = false
	if count, err := relay.RunOnce(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered RunOnce() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.saves != 1 || outbox.checkpoint != outbox.event.EventID ||
		transport.message.Stream != reviewmessaging.HomepageReviewEventStream ||
		fields["eventId"] != outbox.event.EventID || fields["aggregateVersion"] != "1" ||
		transport.retention != reviewmessaging.HomepageReviewEventStreamRetention {
		t.Fatalf("HomepageReview delivery mismatch: saves=%d checkpoint=%q stream=%q fields=%v retention=%s", outbox.saves, outbox.checkpoint, transport.message.Stream, fields, transport.retention)
	}
}

func TestHomepageReviewPublisherEmitsExactCanonicalPayloads(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		eventType, payload, want string
	}{
		{
			eventType: "HomepageReviewPublished",
			payload:   `{"reviewId":"review-1","homepageId":"homepage-1","authorPersonaId":"persona-1","rating":5,"tagRefs":[],"status":"active","createdAt":"2026-08-05T12:00:00Z","version":1,"updatedAt":"not contracted"}`,
			want:      `{"reviewId":"review-1","homepageId":"homepage-1","authorPersonaId":"persona-1","rating":5,"tagRefs":[],"status":"active","createdAt":"2026-08-05T12:00:00Z","version":1}`,
		},
		{
			eventType: "HomepageReviewUpdated",
			payload:   `{"reviewId":"review-1","homepageId":"homepage-1","authorPersonaId":"persona-1","rating":4,"tagRefs":["quiet"],"status":"active","updatedAt":"2026-08-05T12:00:00Z","version":2,"createdAt":"not contracted"}`,
			want:      `{"reviewId":"review-1","homepageId":"homepage-1","authorPersonaId":"persona-1","rating":4,"tagRefs":["quiet"],"status":"active","updatedAt":"2026-08-05T12:00:00Z","version":2}`,
		},
		{
			eventType: "HomepageReviewRemoved",
			payload:   `{"reviewId":"review-1","homepageId":"homepage-1","authorPersonaId":"not contracted","rating":4,"tagRefs":[],"status":"deleted","updatedAt":"2026-08-05T12:00:00Z","version":3}`,
			want:      `{"reviewId":"review-1","homepageId":"homepage-1","status":"deleted","updatedAt":"2026-08-05T12:00:00Z","version":3}`,
		},
	}
	for _, test := range tests {
		t.Run(test.eventType, func(t *testing.T) {
			transport := &reviewTransportFixture{}
			publisher, err := reviewmessaging.NewEventPublisher(transport)
			if err != nil {
				t.Fatalf("NewEventPublisher() error = %v", err)
			}
			err = publisher.Publish(context.Background(), reviewport.OutboxEvent{
				EventID: "event-1", EventType: test.eventType, AggregateID: "review-1",
				AggregateVersion: 7, Payload: []byte(test.payload), OccurredAt: now,
			})
			if err != nil {
				t.Fatalf("Publish() error = %v", err)
			}
			fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
			assertReviewJSON(t, fields["payload"], test.want)
		})
	}
}

func assertReviewJSON(t *testing.T, got, want string) {
	t.Helper()
	decode := func(raw string) any {
		decoder := json.NewDecoder(bytes.NewBufferString(raw))
		decoder.UseNumber()
		var value any
		if err := decoder.Decode(&value); err != nil {
			t.Fatalf("decode JSON %q: %v", raw, err)
		}
		return value
	}
	if gotValue, wantValue := decode(got), decode(want); !reflect.DeepEqual(gotValue, wantValue) {
		t.Fatalf("payload = %s, want %s", got, want)
	}
}
