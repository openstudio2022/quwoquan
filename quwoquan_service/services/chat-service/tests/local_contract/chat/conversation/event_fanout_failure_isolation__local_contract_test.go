// 群会话事件分发的单点失败隔离契约：一个接收方的分发通道不可用时，
// 其余接收方仍收到事件（durable resume + ephemeral），失败被单独记录
// 而不中断整批。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-003.t2
package local_contract

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
)

// faultyEphemeralClient 让指定接收方的 Pub/Sub 通道不可用，其余转发真实
// memory client；成功发布的通道被记录用于送达断言。
type faultyEphemeralClient struct {
	rtredis.Client

	failChannel string

	mu        sync.Mutex
	published []string
}

func (c *faultyEphemeralClient) Publish(ctx context.Context, channel string, message string) error {
	if channel == c.failChannel {
		return errors.New("recipient delivery channel unavailable")
	}
	c.mu.Lock()
	c.published = append(c.published, channel)
	c.mu.Unlock()
	return c.Client.Publish(ctx, channel, message)
}

func (c *faultyEphemeralClient) publishedChannels() []string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]string(nil), c.published...)
}

func TestGroupFanoutIsolatesSingleRecipientFailure(t *testing.T) {
	ctx := context.Background()
	realtime := &faultyEphemeralClient{
		Client:      rtredis.NewMemoryClient(),
		failChannel: "rt:user:user-b",
	}
	general := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		realtime,
		general,
	)
	if err != nil {
		t.Fatal(err)
	}
	resumeTransport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api-resume",
		runtimemessaging.RedisMessageTransportAdapter,
		realtime,
		realtime,
	)
	if err != nil {
		t.Fatal(err)
	}
	publisher := NewEventPublisherWithTransports(
		transport,
		resumeTransport,
		NewMemberRecipientResolver(func(context.Context, string) ([]string, error) {
			return []string{"user-a", "user-b", "user-c"}, nil
		}),
	)

	publishErr := publisher.PublishRecordedDomainEvent(
		ctx,
		"event-fanout-1",
		messageevent.MessageSent,
		"conversation-1",
		"user-a",
		map[string]any{"messageId": "message-1", "seq": int64(11)},
	)

	if publishErr == nil {
		t.Fatal("single recipient failure must be recorded, not swallowed")
	}
	if !strings.Contains(publishErr.Error(), "rt:user:user-b") {
		t.Fatalf("failure must identify the failed recipient, got: %v", publishErr)
	}
	if strings.Contains(publishErr.Error(), "rt:user:user-a") ||
		strings.Contains(publishErr.Error(), "rt:user:user-c") {
		t.Fatalf("healthy recipients must not be reported as failed: %v", publishErr)
	}

	// 其余接收方的 durable resume stream 均收到事件（断连补洞的读回坐标）。
	for _, userID := range []string{"user-a", "user-c"} {
		messages, readErr := realtime.XRead(
			ctx,
			map[string]string{RealtimeResumeStream(userID): "0-0"},
			10,
			0,
		)
		if readErr != nil {
			t.Fatalf("read %s resume stream: %v", userID, readErr)
		}
		if len(messages) != 1 || messages[0].Values["eventId"] != "event-fanout-1" {
			t.Fatalf("%s must still receive the durable event, got %#v", userID, messages)
		}
	}

	// 其余接收方的 ephemeral 即时通道仍被投递。
	delivered := realtime.publishedChannels()
	for _, channel := range []string{"rt:user:user-a", "rt:user:user-c"} {
		found := false
		for _, published := range delivered {
			if published == channel {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("%s must still receive the ephemeral event, published=%v", channel, delivered)
		}
	}
}
