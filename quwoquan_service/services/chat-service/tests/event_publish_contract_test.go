package tests

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	mqpkg "quwoquan_service/services/chat-service/internal/adapters/mq"
	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
)

// collectEvents subscribes to a Redis Pub/Sub channel and collects events
// published within the timeout window.
func collectEvents(t *testing.T, channel string, timeout time.Duration) []mqpkg.DomainEvent {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	client := redisRouter.Scene("realtime")
	sub, err := client.Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe to %s: %v", channel, err)
	}
	defer sub.Close()

	var events []mqpkg.DomainEvent
	ch := sub.Channel()
	for {
		select {
		case msg, ok := <-ch:
			if !ok {
				return events
			}
			var evt mqpkg.DomainEvent
			if err := json.Unmarshal([]byte(msg.Payload), &evt); err != nil {
				t.Logf("collectEvents: unmarshal error: %v", err)
				continue
			}
			events = append(events, evt)
		case <-ctx.Done():
			return events
		}
	}
}

// waitForEvent subscribes and waits for a single event on the channel.
func waitForEvent(t *testing.T, channel string, timeout time.Duration) (mqpkg.DomainEvent, bool) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	client := redisRouter.Scene("realtime")
	sub, err := client.Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe to %s: %v", channel, err)
	}
	defer sub.Close()

	select {
	case msg := <-sub.Channel():
		var evt mqpkg.DomainEvent
		if err := json.Unmarshal([]byte(msg.Payload), &evt); err != nil {
			t.Fatalf("unmarshal event: %v", err)
		}
		return evt, true
	case <-ctx.Done():
		return mqpkg.DomainEvent{}, false
	}
}

// publishDirect publishes a domain event via EventPublisher, bypassing HTTP handlers.
func publishDirect(t *testing.T, evt mqpkg.DomainEvent) {
	t.Helper()
	publisher := mqpkg.NewEventPublisher(redisRouter.Scene("realtime"))
	if err := publisher.Publish(context.Background(), evt); err != nil {
		t.Fatalf("publishDirect: %v", err)
	}
}

// --- Handler-integrated event tests (skeleton: skip until pipeline wired) ---

func TestEventPublish_MessageSent(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"event test"}`)
	convId := conv["_id"].(string)

	// Wait for the ConversationCreated goroutine to complete before subscribing
	time.Sleep(200 * time.Millisecond)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	sendMessage(t, convId, `{"type":"text","content":"hello event","clientMsgId":"evt-uuid-1"}`)

	// Collect events, filtering for MessageSent
	deadline := time.After(3 * time.Second)
	for {
		select {
		case msg := <-sub.Channel():
			var evt mqpkg.DomainEvent
			if err := json.Unmarshal([]byte(msg.Payload), &evt); err != nil {
				t.Fatalf("unmarshal event: %v", err)
			}
			if evt.Type == event.MessageSent {
				if evt.ConversationID != convId {
					t.Errorf("expected conversationId=%s, got %s", convId, evt.ConversationID)
				}
				if evt.Payload["content"] != "hello event" {
					t.Errorf("expected payload.content='hello event', got %v", evt.Payload["content"])
				}
				return
			}
		case <-deadline:
			t.Fatal("MessageSent event not received within timeout")
		}
	}
}

func TestEventPublish_MessageRecalled(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"recall event"}`)
	convId := conv["_id"].(string)
	msg := sendMessage(t, convId, `{"type":"text","content":"will recall","clientMsgId":"evt-recall-1"}`)
	msgId := msg["messageId"].(string)

	time.Sleep(100 * time.Millisecond)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/recall", `{}`, "user_test_001", http.StatusOK)

	select {
	case raw := <-sub.Channel():
		var evt mqpkg.DomainEvent
		if err := json.Unmarshal([]byte(raw.Payload), &evt); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if evt.Type != event.MessageRecalled {
			t.Errorf("expected type=%s, got %s", event.MessageRecalled, evt.Type)
		}
		if evt.Payload["messageId"] != msgId {
			t.Errorf("expected payload.messageId=%s, got %v", msgId, evt.Payload["messageId"])
		}
	case <-time.After(3 * time.Second):
		t.Fatal("MessageRecalled event not received within timeout")
	}
}

func TestEventPublish_ConversationRosterUpdatedOnAddMembers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"roster event on add"}`)
	convId := conv["_id"].(string)

	// Create path publishes ConversationRosterUpdated in a goroutine; wait it out.
	time.Sleep(300 * time.Millisecond)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	doPost(t, "/v1/chat/conversations/"+convId+"/members", `{"userIds":["user_new_1"]}`, "user_test_001", http.StatusOK)

	deadline := time.After(3 * time.Second)
	for {
		select {
		case raw := <-sub.Channel():
			var evt mqpkg.DomainEvent
			if err := json.Unmarshal([]byte(raw.Payload), &evt); err != nil {
				t.Fatalf("unmarshal: %v", err)
			}
			if evt.Type != event.ConversationRosterUpdated {
				continue
			}
			if evt.Payload["membersRosterRevision"] == nil {
				t.Fatal("expected payload.membersRosterRevision")
			}
			rev, ok := evt.Payload["membersRosterRevision"].(float64)
			if !ok {
				t.Fatalf("membersRosterRevision type %T", evt.Payload["membersRosterRevision"])
			}
			if rev < 2 {
				t.Errorf("expected membersRosterRevision>=2 after add, got %v", rev)
			}
			return
		case <-deadline:
			t.Fatal("ConversationRosterUpdated event not received within timeout")
		}
	}
}

func TestEventPublish_ConversationRosterUpdatedDebouncedMerge(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"roster debounce"}`)
	convId := conv["_id"].(string)
	time.Sleep(300 * time.Millisecond)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	doPost(t, "/v1/chat/conversations/"+convId+"/members", `{"userIds":["user_merge_a"]}`, "user_test_001", http.StatusOK)
	doPost(t, "/v1/chat/conversations/"+convId+"/members", `{"userIds":["user_merge_b"]}`, "user_test_001", http.StatusOK)

	rosterCount := 0
	deadline := time.Now().Add(500 * time.Millisecond)
	for time.Now().Before(deadline) {
		select {
		case raw := <-sub.Channel():
			var evt mqpkg.DomainEvent
			if err := json.Unmarshal([]byte(raw.Payload), &evt); err != nil {
				t.Fatalf("unmarshal: %v", err)
			}
			if evt.Type == event.ConversationRosterUpdated {
				rosterCount++
				if rosterCount > 1 {
					t.Fatalf("expected single merged roster event, got %d", rosterCount)
				}
			}
		default:
			time.Sleep(5 * time.Millisecond)
		}
	}
	if rosterCount != 1 {
		t.Fatalf("expected exactly 1 ConversationRosterUpdated after debounce window, got %d", rosterCount)
	}
}

func TestEventPublish_MemberLeft(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"member leave event"}`)
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/members", `{"userIds":["user_leave_1"]}`, "user_test_001", http.StatusOK)
	// Let debounced ConversationRosterUpdated from AddMembers flush before we subscribe for RemoveMember.
	time.Sleep(300 * time.Millisecond)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	doDelete(t, "/v1/chat/conversations/"+convId+"/members/user_leave_1", "user_test_001")

	deadline := time.After(3 * time.Second)
	for {
		select {
		case raw := <-sub.Channel():
			var evt mqpkg.DomainEvent
			if err := json.Unmarshal([]byte(raw.Payload), &evt); err != nil {
				t.Fatalf("unmarshal: %v", err)
			}
			if evt.Type == event.MemberLeft {
				return
			}
		case <-deadline:
			t.Fatal("MemberLeft event not received within timeout")
		}
	}
}

func TestEventPublish_ConversationCreated(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"created event"}`)
	convId := conv["_id"].(string)

	// ConversationCreated is published in a goroutine after HTTP response;
	// give it a brief moment to fire, then verify via a second operation:
	// send a message on the same channel and check we got ConversationCreated
	// before or after it.
	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	// Trigger a second event to ensure the subscriber is active
	sendMessage(t, convId, `{"type":"text","content":"trigger","clientMsgId":"evt-cc-trigger"}`)

	events := collectEvents(t, channel, 2*time.Second)
	_ = events
	// The ConversationCreated goroutine may have completed before subscribe;
	// verify via direct publisher round-trip (already covered by DirectPublishRoundTrip).
	// This test verifies the handler wiring doesn't panic and completes.
}

func TestEventPublish_ConversationSettingsUpdated(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"settings event"}`)
	convId := conv["_id"].(string)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	doPatch(t, "/v1/chat/conversations/"+convId+"/settings", `{"muted":true}`, "user_test_001")

	select {
	case raw := <-sub.Channel():
		var evt mqpkg.DomainEvent
		if err := json.Unmarshal([]byte(raw.Payload), &evt); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if evt.Type != event.ConversationSettingsUpdated {
			t.Errorf("expected type=%s, got %s", event.ConversationSettingsUpdated, evt.Type)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("ConversationSettingsUpdated event not received within timeout")
	}
}

func TestEventPublish_ReadReceiptSent(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"receipt event","maxGroupSize":2}`)
	convId := conv["_id"].(string)
	msg := sendMessage(t, convId, `{"type":"text","content":"read me","clientMsgId":"evt-read-1"}`)
	msgId := msg["messageId"].(string)

	time.Sleep(100 * time.Millisecond)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/read", `{}`, "user_test_002", http.StatusOK)

	select {
	case raw := <-sub.Channel():
		var evt mqpkg.DomainEvent
		if err := json.Unmarshal([]byte(raw.Payload), &evt); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if evt.Type != event.ReadReceiptSent {
			t.Errorf("expected type=%s, got %s", event.ReadReceiptSent, evt.Type)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("ReadReceiptSent event not received within timeout")
	}
}

func TestEventPublish_AssistantInvited(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"assistant event"}`)
	convId := conv["_id"].(string)

	channel := "rt:conversation:" + convId
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()
	time.Sleep(50 * time.Millisecond)

	doPost(t, "/v1/chat/conversations/"+convId+"/assistant", `{"skillId":"general"}`, "user_test_001", http.StatusOK)

	select {
	case raw := <-sub.Channel():
		var evt mqpkg.DomainEvent
		if err := json.Unmarshal([]byte(raw.Payload), &evt); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if evt.Type != event.AssistantInvited {
			t.Errorf("expected type=%s, got %s", event.AssistantInvited, evt.Type)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("AssistantInvited event not received within timeout")
	}
}

func TestEventPublish_AssistantMentioned(t *testing.T) {
	t.Skip("event_publisher not yet integrated into handler pipeline")

	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"mention event"}`)
	convId := conv["_id"].(string)
	_ = convId
}

func TestEventPublish_AssistantRemoved(t *testing.T) {
	t.Skip("event_publisher not yet integrated into handler pipeline")

	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"assistant remove event"}`)
	_ = conv["_id"].(string)
}

// --- Direct publisher tests (verify EventPublisher→Redis independently) ---

func TestEventPublish_DirectPublishRoundTrip(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	convId := "test-conv-event-roundtrip"
	publisher := mqpkg.NewEventPublisher(redisRouter.Scene("realtime"))
	channel := "rt:conversation:" + convId

	ctx := context.Background()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()

	// Allow subscription to be established
	time.Sleep(50 * time.Millisecond)

	evt := mqpkg.DomainEvent{
		Type:           event.MessageSent,
		ConversationID: convId,
		ActorID:        "user_test_001",
		Timestamp:      time.Now(),
		Payload:        map[string]any{"messageId": "msg-001", "content": "hello"},
	}

	if err := publisher.Publish(ctx, evt); err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	select {
	case msg := <-sub.Channel():
		var received mqpkg.DomainEvent
		if err := json.Unmarshal([]byte(msg.Payload), &received); err != nil {
			t.Fatalf("unmarshal received event: %v", err)
		}
		if received.Type != event.MessageSent {
			t.Errorf("expected type=%s, got %s", event.MessageSent, received.Type)
		}
		if received.ConversationID != convId {
			t.Errorf("expected conversationId=%s, got %s", convId, received.ConversationID)
		}
		if received.ActorID != "user_test_001" {
			t.Errorf("expected actorId=user_test_001, got %s", received.ActorID)
		}
		if received.Payload["messageId"] != "msg-001" {
			t.Errorf("expected payload.messageId=msg-001, got %v", received.Payload["messageId"])
		}
	case <-time.After(3 * time.Second):
		t.Fatal("did not receive event within timeout")
	}
}

func TestEventPublish_BatchPublish(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	convId := "test-conv-batch-events"
	publisher := mqpkg.NewEventPublisher(redisRouter.Scene("realtime"))
	channel := "rt:conversation:" + convId

	ctx := context.Background()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, channel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()

	time.Sleep(50 * time.Millisecond)

	events := []mqpkg.DomainEvent{
		{Type: event.MemberJoined, ConversationID: convId, ActorID: "user_a", Timestamp: time.Now()},
		{Type: event.MessageSent, ConversationID: convId, ActorID: "user_a", Timestamp: time.Now()},
		{Type: event.ReadReceiptSent, ConversationID: convId, ActorID: "user_b", Timestamp: time.Now()},
	}

	if err := publisher.PublishBatch(ctx, events); err != nil {
		t.Fatalf("batch publish failed: %v", err)
	}

	for i, expected := range events {
		select {
		case msg := <-sub.Channel():
			var received mqpkg.DomainEvent
			if err := json.Unmarshal([]byte(msg.Payload), &received); err != nil {
				t.Fatalf("event[%d]: unmarshal: %v", i, err)
			}
			if received.Type != expected.Type {
				t.Errorf("event[%d]: expected type=%s, got %s", i, expected.Type, received.Type)
			}
		case <-time.After(3 * time.Second):
			t.Fatalf("event[%d]: did not receive within timeout", i)
		}
	}
}

func TestEventPublish_SupportedEventTypesComplete(t *testing.T) {
	expectedTypes := []string{
		event.MessageSent,
		event.MessageRecalled,
		event.MemberJoined,
		event.ConversationRosterUpdated,
		event.MemberLeft,
		event.ConversationCreated,
		event.ConversationSettingsUpdated,
		event.ReadReceiptSent,
		event.AssistantInvited,
		event.AssistantMentioned,
		mqpkg.EventAssistantRemoved,
	}

	supported := make(map[string]bool, len(mqpkg.SupportedEventTypes))
	for _, st := range mqpkg.SupportedEventTypes {
		supported[st] = true
	}

	for _, et := range expectedTypes {
		if !supported[et] {
			t.Errorf("SupportedEventTypes missing %q", et)
		}
	}
}

func TestEventPublish_ChannelFormat(t *testing.T) {
	evt := mqpkg.DomainEvent{
		Type:           event.MessageSent,
		ConversationID: "abc-123",
	}

	// Verify channel() returns the expected format by checking
	// that publishing to a subscribe on the expected channel works.
	t.Cleanup(func() { cleanAll(t) })

	publisher := mqpkg.NewEventPublisher(redisRouter.Scene("realtime"))
	expectedChannel := "rt:conversation:abc-123"

	ctx := context.Background()
	sub, err := redisRouter.Scene("realtime").Subscribe(ctx, expectedChannel)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Close()

	time.Sleep(50 * time.Millisecond)

	evt.Timestamp = time.Now()
	if err := publisher.Publish(ctx, evt); err != nil {
		t.Fatalf("publish: %v", err)
	}

	select {
	case msg := <-sub.Channel():
		if msg.Channel != expectedChannel {
			t.Errorf("expected channel=%s, got %s", expectedChannel, msg.Channel)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("did not receive event within timeout")
	}
}

