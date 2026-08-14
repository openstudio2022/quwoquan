package application_test

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	gatheringports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
	gatheringmessaging "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/messaging"
)

type gatheringOutboxFixture struct {
	event      gatheringports.OutboxEvent
	checkpoint int64
	available  bool
	saved      int
}

func (fixture *gatheringOutboxFixture) ReadPublicationOutboxAfter(
	_ context.Context, after int64, _ int,
) ([]gatheringports.OutboxEvent, error) {
	if !fixture.available || fixture.event.Sequence <= after {
		return nil, nil
	}
	return []gatheringports.OutboxEvent{fixture.event}, nil
}

func (fixture *gatheringOutboxFixture) LoadPublicationCheckpoint(
	context.Context, string,
) (int64, error) {
	return fixture.checkpoint, nil
}

func (fixture *gatheringOutboxFixture) SavePublicationCheckpoint(
	_ context.Context, _ string, sequence int64, _ time.Time,
) error {
	fixture.checkpoint = sequence
	fixture.saved++
	return nil
}

type gatheringTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *gatheringTransportFixture) AppendDurable(
	_ context.Context, message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *gatheringTransportFixture) SetDurableRetention(
	_ context.Context, _ string, retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestGatheringRelayUsesPublicationCheckpointAfterDurableHandoff(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	event := gatheringports.OutboxEvent{
		EventID: "gathering-1:GatheringDraftCreated:1", EventType: "GatheringDraftCreated",
		AggregateID: "gathering-1", AggregateVersion: 1, Sequence: 7,
		Payload: []byte(`{"gatheringId":"gathering-1","aggregateVersion":1,` +
			`"lifecycleStatus":"draft","actorPersonaId":"persona-1",` +
			`"revisionId":"revision-1","revisionNumber":1,"revisionDigest":"digest-1",` +
			`"roomBindingStatus":"pending","occurredAt":"2026-08-05T12:00:00Z"}`),
		OccurredAt: now,
	}
	outbox := &gatheringOutboxFixture{event: event, available: true}
	transport := &gatheringTransportFixture{fail: true}
	publisher, err := gatheringmessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := gatheringapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.saved != 0 || outbox.checkpoint != 0 || relay.Healthy(context.Background(), time.Minute) == nil {
		t.Fatalf("failed delivery advanced or remained healthy: saved=%d checkpoint=%d", outbox.saved, outbox.checkpoint)
	}
	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.saved != 1 || outbox.checkpoint != event.Sequence ||
		transport.message.Stream != gatheringmessaging.GatheringEventStream ||
		fields["aggregateId"] != event.AggregateID || transport.retention <= 0 {
		t.Fatalf("Gathering delivery mismatch: saved=%d checkpoint=%d stream=%q fields=%v retention=%s", outbox.saved, outbox.checkpoint, transport.message.Stream, fields, transport.retention)
	}
	if err := relay.Healthy(context.Background(), time.Minute); err != nil {
		t.Fatalf("Healthy() after recovery error = %v", err)
	}
}

func TestGatheringRelayRecoversHealthAfterEmptySuccessfulScan(t *testing.T) {
	event := gatheringports.OutboxEvent{
		EventID: "gathering-1:GatheringDraftCreated:1", EventType: "GatheringDraftCreated",
		AggregateID: "gathering-1", AggregateVersion: 1, Sequence: 7,
		Payload:    []byte(`{}`),
		OccurredAt: time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC),
	}
	outbox := &gatheringOutboxFixture{event: event, available: true}
	transport := &gatheringTransportFixture{fail: true}
	publisher, err := gatheringmessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := gatheringapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if _, err := relay.Drain(context.Background(), 1); err == nil {
		t.Fatal("failed Drain() must return an error")
	}
	if relay.Healthy(context.Background(), time.Minute) == nil {
		t.Fatal("Healthy() must fail right after a drain failure")
	}
	// 瞬时故障结束后 outbox 为空：一次成功的空扫描必须恢复健康态，
	// 不得把空 outbox 的服务永久卡在 unhealthy。
	outbox.available = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 0 {
		t.Fatalf("empty Drain() = (%d, %v), want (0, nil)", count, err)
	}
	if err := relay.Healthy(context.Background(), time.Minute); err != nil {
		t.Fatalf("Healthy() after empty successful scan error = %v", err)
	}
}
