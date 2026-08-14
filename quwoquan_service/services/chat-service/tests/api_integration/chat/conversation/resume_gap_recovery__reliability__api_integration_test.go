// 断连补洞真链（SIT-002）：断连窗口内连续发布的会话事件必须按序落入
// 接收方的 rt:resume:chat:user:{id} 持久流（真实 Redis），恢复侧按游标
// 续读时无缺号、无重复且有序；从中间游标续读只返回缺口之后的事件。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/spec.md#sit-002.t1
// readiness_case: send-message-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
)

func TestResumeStreamRecoversDisconnectWindowWithoutGapsOrDuplicates(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	defer cancel()

	const (
		senderID   = "user-gap-sender"
		receiverID = "user-gap-receiver"
		convID     = "conversation-gap-recovery"
	)
	realtimeScene := redisRouter.Scene("realtime")
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		realtimeScene,
		redisRouter.Scene("general"),
	)
	if err != nil {
		t.Fatal(err)
	}
	resumeTransport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api-resume",
		runtimemessaging.RedisMessageTransportAdapter,
		realtimeScene,
		realtimeScene,
	)
	if err != nil {
		t.Fatal(err)
	}
	publisher := mq.NewEventPublisherWithTransports(
		transport,
		resumeTransport,
		mq.NewMemberRecipientResolver(func(context.Context, string) ([]string, error) {
			return []string{senderID, receiverID}, nil
		}),
	)

	// 断连窗口：接收方无任何订阅/轮询，发送方连续发出 5 条消息。
	const totalEvents = 5
	for seq := 1; seq <= totalEvents; seq++ {
		if err := publisher.Publish(ctx, mq.DomainEvent{
			EventID:        fmt.Sprintf("gap-event-%d", seq),
			Type:           messageevent.MessageSent,
			ConversationID: convID,
			ActorID:        senderID,
			Timestamp:      time.Date(2026, 8, 13, 12, 0, seq, 0, time.UTC),
			Payload: map[string]any{
				"messageId":      fmt.Sprintf("gap-message-%d", seq),
				"conversationId": convID,
				"seq":            int64(seq),
				"clientMsgId":    fmt.Sprintf("gap-client-%d", seq),
				"senderId":       senderID,
				"type":           "text",
				"content":        fmt.Sprintf("断连窗口消息 %d", seq),
			},
		}); err != nil {
			t.Fatalf("publish event %d during disconnect window: %v", seq, err)
		}
	}

	stream := runtimemessaging.RealtimeChatResumeStream(receiverID)
	entries, err := realtimeScene.XRead(ctx, map[string]string{stream: "0-0"}, 50, 0)
	if err != nil {
		t.Fatalf("read resume stream after reconnect: %v", err)
	}
	if len(entries) != totalEvents {
		t.Fatalf(
			"resume stream must retain the full disconnect window, got %d entries",
			len(entries),
		)
	}
	// 无缺号、无重复且按发布序有序。
	seenEventIDs := map[string]bool{}
	for index, entry := range entries {
		wantEventID := fmt.Sprintf("gap-event-%d", index+1)
		if entry.Values["eventId"] != wantEventID {
			t.Fatalf(
				"entry %d out of order: eventId=%v want=%s",
				index, entry.Values["eventId"], wantEventID,
			)
		}
		if seenEventIDs[wantEventID] {
			t.Fatalf("duplicate eventId %s in resume stream", wantEventID)
		}
		seenEventIDs[wantEventID] = true
		wantSeq := fmt.Sprintf("%d", index+1)
		if entry.Values["seq"] != wantSeq {
			t.Fatalf("entry %d seq=%v want=%s", index, entry.Values["seq"], wantSeq)
		}
		// payload 保持 canonical client realtime envelope，可被端侧直接消费。
		var envelope map[string]any
		if err := json.Unmarshal([]byte(entry.Values["payload"]), &envelope); err != nil {
			t.Fatalf("entry %d payload is not canonical JSON: %v", index, err)
		}
		if envelope["type"] != "MessageSent" {
			t.Fatalf("entry %d envelope type=%v", index, envelope["type"])
		}
	}

	// 恢复侧持有第 2 条的游标：续读只返回缺口之后的 3..5，无重复。
	resumeCursor := entries[1].ID
	tail, err := realtimeScene.XRead(ctx, map[string]string{stream: resumeCursor}, 50, 0)
	if err != nil {
		t.Fatalf("cursor resume read: %v", err)
	}
	if len(tail) != totalEvents-2 {
		t.Fatalf("cursor resume must return only the gap tail, got %d entries", len(tail))
	}
	for index, entry := range tail {
		wantEventID := fmt.Sprintf("gap-event-%d", index+3)
		if entry.Values["eventId"] != wantEventID {
			t.Fatalf(
				"tail entry %d eventId=%v want=%s",
				index, entry.Values["eventId"], wantEventID,
			)
		}
	}

	// 发送方自身的 resume 流同样成立（多设备补洞语义），互不串号。
	senderEntries, err := realtimeScene.XRead(
		ctx,
		map[string]string{runtimemessaging.RealtimeChatResumeStream(senderID): "0-0"},
		50,
		0,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(senderEntries) != totalEvents {
		t.Fatalf("sender resume stream entries = %d", len(senderEntries))
	}
}
