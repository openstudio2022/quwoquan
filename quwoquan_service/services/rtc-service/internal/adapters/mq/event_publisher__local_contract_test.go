package mq

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/rtc-service/internal/application"
	event "quwoquan_service/services/rtc-service/internal/domain/call_session/event"
)

func TestCallRingingUsesDurableStreamWithoutUserAliasPubSub(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	publisher := NewRealtimePublisher(client)
	personaSub, err := client.Subscribe(ctx, "rt:rtc:persona:persona-target")
	if err != nil {
		t.Fatal(err)
	}
	defer personaSub.Close()
	userAliasSub, err := client.Subscribe(ctx, "rt:rtc:user:persona-target")
	if err != nil {
		t.Fatal(err)
	}
	defer userAliasSub.Close()

	ringing := application.CallOutboxEvent{
		EventID:     "rtc-event-ringing",
		EventType:   event.CallRinging,
		AggregateID: "2477a8d9-37c9-4b6c-8e63-e1903aaf91f1",
		DeliveryKey: "sha256:ringing",
		Payload:     []byte(`{"type":"call.ringing"}`),
		OccurredAt:  time.Now().UTC(),
	}
	if err := publisher.PublishToPersonas(
		ctx,
		[]string{"persona-target"},
		"call.ringing",
		ringing,
	); err != nil {
		t.Fatalf("publish CallRinging: %v", err)
	}
	if err := client.XGroupCreateMkStream(
		ctx,
		RtcCallRingingStream,
		"notification-service-test",
		"0",
	); err != nil {
		t.Fatal(err)
	}
	messages, err := client.XReadGroup(
		ctx,
		"notification-service-test",
		"consumer",
		map[string]string{RtcCallRingingStream: ">"},
		10,
		0,
	)
	if err != nil || len(messages) != 1 {
		t.Fatalf("durable CallRinging messages=%v err=%v", messages, err)
	}
	if messages[0].Values["eventId"] != ringing.EventID ||
		messages[0].Values["deliveryKey"] != ringing.DeliveryKey {
		t.Fatalf("durable stream payload=%v", messages[0].Values)
	}
	assertNoPubSubMessage(t, personaSub.Channel(), "CallRinging persona Pub/Sub")
	assertNoPubSubMessage(t, userAliasSub.Channel(), "CallRinging user alias")

	answered := application.CallOutboxEvent{
		EventID:     "rtc-event-answered",
		EventType:   event.CallAnswered,
		AggregateID: ringing.AggregateID,
		Payload:     []byte(`{"type":"call.answered"}`),
		OccurredAt:  time.Now().UTC(),
	}
	if err := publisher.PublishToPersonas(
		ctx,
		[]string{"persona-target"},
		"call.answered",
		answered,
	); err != nil {
		t.Fatalf("publish CallAnswered: %v", err)
	}
	select {
	case message := <-personaSub.Channel():
		if message.Payload != string(answered.Payload) {
			t.Fatalf("persona payload=%q", message.Payload)
		}
	case <-time.After(time.Second):
		t.Fatal("persona channel did not receive CallAnswered")
	}
	assertNoPubSubMessage(t, userAliasSub.Channel(), "CallAnswered user alias")
	assertDurableRTCEvent(
		t,
		client,
		RtcCallAnsweredStream,
		"answered-observer",
		answered.EventID,
	)

	ended := application.CallOutboxEvent{
		EventID:     "rtc-event-ended",
		EventType:   event.CallEnded,
		AggregateID: ringing.AggregateID,
		Payload:     []byte(`{"type":"call.ended"}`),
		OccurredAt:  time.Now().UTC(),
	}
	if err := publisher.PublishToPersonas(
		ctx,
		[]string{"persona-target"},
		"call.ended",
		ended,
	); err != nil {
		t.Fatalf("publish CallEnded: %v", err)
	}
	assertDurableRTCEvent(
		t,
		client,
		RtcCallEndedStream,
		"ended-observer",
		ended.EventID,
	)
}

func assertNoPubSubMessage(
	t *testing.T,
	channel <-chan rtredis.Message,
	description string,
) {
	t.Helper()
	select {
	case message := <-channel:
		t.Fatalf("%s unexpectedly received %+v", description, message)
	case <-time.After(10 * time.Millisecond):
	}
}

func assertDurableRTCEvent(
	t *testing.T,
	client rtredis.Client,
	stream string,
	group string,
	eventID string,
) {
	t.Helper()
	ctx := context.Background()
	if err := client.XGroupCreateMkStream(ctx, stream, group, "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := client.XReadGroup(
		ctx,
		group,
		"observer",
		map[string]string{stream: ">"},
		10,
		0,
	)
	if err != nil || len(messages) != 1 ||
		messages[0].Values["eventId"] != eventID {
		t.Fatalf(
			"durable stream %s messages=%v err=%v",
			stream,
			messages,
			err,
		)
	}
}
