package local_contract

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func TestCircleGroupChatSyncConsumerAppliesAndAcknowledges(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	projector := &memoryCircleGroupChatSyncProjector{}
	failures := &memoryCircleGroupChatSyncFailures{}
	consumer := newCircleGroupChatSyncConsumerForTest(t, client, projector, failures, slog.Default(), 2)
	if _, err := client.XAdd(ctx, CircleGroupEventStream, validCircleGroupCreatedValues("group-created-1")); err != nil {
		t.Fatal(err)
	}
	if _, err := client.XAdd(ctx, CircleGroupEventStream, map[string]string{
		"eventId": "group-updated-ignored", "eventType": "CircleGroupUpdated",
		"aggregateVersion": "2", "payload": `{}`, "occurredAt": "2026-07-21T01:02:04Z",
	}); err != nil {
		t.Fatal(err)
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 2 {
		t.Fatalf("process result=%d err=%v", processed, err)
	}
	if len(projector.events) != 1 || projector.events[0].EventType != "CircleGroupCreated" {
		t.Fatalf("only supported source event may reach application: %#v", projector.events)
	}
	pending, _, err := client.XAutoClaim(
		ctx,
		CircleGroupEventStream,
		CircleGroupProvisionerConsumerGroup,
		"observer",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(pending) != 0 {
		t.Fatalf("successful and ignored messages must be ACKed, pending=%d", len(pending))
	}
}

func TestCircleGroupChatSyncConsumerRetriesThenDeadLettersWithoutLeakingCause(t *testing.T) {
	ctx := context.Background()
	client := &circleGroupChatSyncExpireTrackingRedis{Client: rtredis.NewMemoryClient()}
	secret := "circle-group-private-cause"
	projector := &memoryCircleGroupChatSyncProjector{err: errors.New("projection failed " + secret)}
	failures := &memoryCircleGroupChatSyncFailures{}
	var logOutput bytes.Buffer
	consumer := newCircleGroupChatSyncConsumerForTest(
		t,
		client,
		projector,
		failures,
		slog.New(slog.NewTextHandler(&logOutput, nil)),
		2,
	)
	messageID, err := client.XAdd(ctx, CircleGroupEventStream, validCircleGroupCreatedValues("group-created-failure"))
	if err != nil {
		t.Fatal(err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err == nil || processed != 0 {
		t.Fatalf("first failure must remain pending, processed=%d err=%v", processed, err)
	}
	if _, err := consumer.ProcessOnce(ctx); err != nil {
		t.Fatalf("second failure must be retained then ACKed through DLQ: %v", err)
	}
	if got := client.expired[circleGroupChatSyncTestDLQ]; got <= 0 {
		t.Fatalf("DLQ retention must be configured, got %v", got)
	}
	pending, _, err := client.XAutoClaim(
		ctx,
		CircleGroupEventStream,
		CircleGroupProvisionerConsumerGroup,
		"observer",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(pending) != 0 {
		t.Fatalf("DLQ'd message must ACK only after DLQ append, pending=%d", len(pending))
	}
	if err := client.XGroupCreateMkStream(ctx, circleGroupChatSyncTestDLQ, "dlq-observer", "0"); err != nil {
		t.Fatal(err)
	}
	dlq, err := client.XReadGroup(
		ctx,
		"dlq-observer",
		"dlq-observer-1",
		map[string]string{circleGroupChatSyncTestDLQ: ">"},
		10,
		0,
	)
	if err != nil || len(dlq) != 1 {
		t.Fatalf("DLQ must contain one sanitized retained record, records=%v err=%v", dlq, err)
	}
	for _, value := range dlq[0].Values {
		if strings.Contains(value, secret) {
			t.Fatalf("DLQ must store only digest, got %q", value)
		}
	}
	_ = messageID
	if strings.Contains(logOutput.String(), secret) {
		t.Fatalf("raw projection cause must not leak to logs: %s", logOutput.String())
	}
}

type memoryCircleGroupChatSyncProjector struct {
	events []application.CircleGroupChatSourceEvent
	err    error
}

func (p *memoryCircleGroupChatSyncProjector) Apply(
	_ context.Context,
	event application.CircleGroupChatSourceEvent,
) error {
	p.events = append(p.events, event)
	return p.err
}

type memoryCircleGroupChatSyncFailures struct {
	attempts map[string]int64
}

func (s *memoryCircleGroupChatSyncFailures) RecordCircleGroupChatSyncFailure(
	_ context.Context,
	messageKey string,
	_ string,
	_ string,
) (int64, error) {
	if s.attempts == nil {
		s.attempts = map[string]int64{}
	}
	s.attempts[messageKey]++
	return s.attempts[messageKey], nil
}

func (s *memoryCircleGroupChatSyncFailures) ClearCircleGroupChatSyncFailure(
	_ context.Context,
	messageKey string,
) error {
	delete(s.attempts, messageKey)
	return nil
}

type circleGroupChatSyncExpireTrackingRedis struct {
	rtredis.Client
	expired map[string]time.Duration
}

func (c *circleGroupChatSyncExpireTrackingRedis) Expire(
	ctx context.Context,
	key string,
	ttl time.Duration,
) error {
	if c.expired == nil {
		c.expired = map[string]time.Duration{}
	}
	c.expired[key] = ttl
	return c.Client.Expire(ctx, key, ttl)
}

func newCircleGroupChatSyncConsumerForTest(
	t *testing.T,
	client rtredis.Client,
	projector application.CircleGroupChatSyncProjector,
	failures CircleGroupChatSyncFailureStore,
	logger *slog.Logger,
	maxAttempts int64,
) *CircleGroupChatSyncConsumer {
	t.Helper()
	consumer, err := NewCircleGroupChatSyncConsumer(
		client,
		projector,
		failures,
		"chat-circle-group-sync-test",
		logger,
		CircleGroupChatSyncConsumerConfig{
			Stream:       CircleGroupEventStream,
			Group:        CircleGroupProvisionerConsumerGroup,
			DLQ:          circleGroupChatSyncTestDLQ,
			BatchSize:    10,
			MaxAttempts:  maxAttempts,
			MinIdle:      0,
			PollInterval: time.Millisecond,
			ReadBlock:    0,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := consumer.EnsureGroup(context.Background()); err != nil {
		t.Fatal(err)
	}
	return consumer
}

const circleGroupChatSyncTestDLQ = "events.circle.groups.chat-circle-group-sync-test.dlq"

func validCircleGroupCreatedValues(eventID string) map[string]string {
	return map[string]string{
		"eventId":          eventID,
		"eventType":        "CircleGroupCreated",
		"aggregateType":    "CircleGroup",
		"aggregateId":      "group-1",
		"aggregateVersion": "1",
		"payload": `{
			"groupId":"group-1",
			"version":1,
			"circleId":"circle-1",
			"name":"摄影小组",
			"createdByPersonaId":"owner-1",
			"status":"active",
			"createdAt":"2026-07-21T01:02:03Z"
		}`,
		"occurredAt": "2026-07-21T01:02:03Z",
	}
}
