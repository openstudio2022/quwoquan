// spec_ref: specs/feature-tree/circle-community/activity-member-governance/circle-lifecycle/spec.md#gwt-001
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
	circleapp "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	circlemessaging "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
)

type circleOutboxFixture struct {
	event      circleports.OutboxEvent
	checkpoint string
	saves      int
}

func (fixture *circleOutboxFixture) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]circleports.OutboxEvent, error) {
	if checkpoint == fixture.event.Checkpoint {
		return nil, nil
	}
	return []circleports.OutboxEvent{fixture.event}, nil
}

func (fixture *circleOutboxFixture) LoadCheckpoint(
	context.Context,
	string,
) (string, error) {
	return fixture.checkpoint, nil
}

func (fixture *circleOutboxFixture) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	fixture.checkpoint = checkpoint
	fixture.saves++
	return nil
}

type circleTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *circleTransportFixture) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *circleTransportFixture) SetDurableRetention(
	_ context.Context,
	_ string,
	retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestCircleOutboxRelayAcknowledgesOnlyAfterDurablePublish(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	outbox := &circleOutboxFixture{event: circleports.OutboxEvent{
		EventID: "circle-1:1", EventType: "CircleCreated",
		AggregateID: "circle-1", AggregateVersion: 1,
		Payload: []byte(`{"id":"circle-1","name":"同行圈","ownerId":"persona-1",` +
			`"category":"travel","tags":["city"],"rulesText":"友善交流",` +
			`"welcomeMessage":"欢迎","iconUrl":"https://media.example/circle.png","autoSyncChat":true}`),
		OccurredAt: now, Checkpoint: "1",
	}}
	transport := &circleTransportFixture{fail: true}
	publisher, err := circlemessaging.NewCircleEventStreamPublisher(transport)
	if err != nil {
		t.Fatalf("NewCircleEventStreamPublisher() error = %v", err)
	}
	relay := circleapp.NewCircleOutboxRelay(
		outbox,
		outbox,
		publisher,
		"circle-event-stream-test",
	)

	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.saves != 0 || outbox.checkpoint != "" {
		t.Fatalf("failed publish advanced checkpoint: saves=%d checkpoint=%q", outbox.saves, outbox.checkpoint)
	}

	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.saves != 1 || outbox.checkpoint != "1" ||
		transport.message.Stream != circlemessaging.CircleEventStream ||
		fields["eventId"] != outbox.event.EventID ||
		fields["aggregateVersion"] != "1" || transport.retention <= 0 {
		t.Fatalf("Circle delivery mismatch: saves=%d checkpoint=%q stream=%q fields=%v retention=%s", outbox.saves, outbox.checkpoint, transport.message.Stream, fields, transport.retention)
	}
}

func TestCirclePublisherEmitsExactCanonicalPayloadForEveryContractEvent(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		eventType string
		payload   string
		want      string
	}{
		{
			eventType: "CircleCreated",
			payload:   `{"id":"circle-1","name":"同行圈","ownerId":"persona-1","category":"travel","tags":["city"],"rulesText":"友善交流","welcomeMessage":"欢迎","iconUrl":"https://media.example/circle.png","autoSyncChat":true,"description":"not contracted"}`,
			want:      `{"id":"circle-1","name":"同行圈","ownerId":"persona-1","category":"travel","tags":["city"],"rulesText":"友善交流","welcomeMessage":"欢迎","iconUrl":"https://media.example/circle.png","autoSyncChat":true}`,
		},
		{
			eventType: "CircleUpdated",
			payload:   `{"id":"circle-1","name":"同行圈","description":"周末同行","rulesText":"友善交流","welcomeMessage":"欢迎","iconUrl":"https://media.example/circle.png","autoSyncChat":false,"tags":["city"],"category":"travel","ownerId":"not contracted"}`,
			want:      `{"id":"circle-1","name":"同行圈","description":"周末同行","rulesText":"友善交流","welcomeMessage":"欢迎","iconUrl":"https://media.example/circle.png","autoSyncChat":false,"tags":["city"],"category":"travel"}`,
		},
		{eventType: "CircleArchived", payload: `{"id":"circle-1","status":"archived","name":"not contracted"}`, want: `{"id":"circle-1","status":"archived"}`},
		{eventType: "CircleSectionsUpdated", payload: `{"circleId":"circle-1","sectionConfig":{"feed":true},"status":"not contracted"}`, want: `{"circleId":"circle-1","sectionConfig":{"feed":true}}`},
	}
	for _, test := range tests {
		t.Run(test.eventType, func(t *testing.T) {
			transport := &circleTransportFixture{}
			publisher, err := circlemessaging.NewCircleEventStreamPublisher(transport)
			if err != nil {
				t.Fatalf("NewCircleEventStreamPublisher() error = %v", err)
			}
			err = publisher.Publish(context.Background(), circleports.OutboxEvent{
				EventID: "event-1", EventType: test.eventType, AggregateID: "circle-1",
				AggregateVersion: 7, Payload: []byte(test.payload), OccurredAt: now, Checkpoint: "7",
			})
			if err != nil {
				t.Fatalf("Publish() error = %v", err)
			}
			fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
			assertCircleJSON(t, fields["payload"], test.want)
		})
	}
}

func assertCircleJSON(t *testing.T, got, want string) {
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
