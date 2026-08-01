// 打招呼被回复后的会话升级：会话必须带上破冰来源，且发起者当初写下的那句话必须
// 成为会话首条消息。空会话意味着「同意」之后双方都不知道要接什么话，破冰链路在
// 成功那一刻断掉。
package api_integration

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func TestGreetingPromotion_StampsOriginAndSeedsOpeningMessage(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	// 关系门此刻仍视双方为陌生人：升级发生在 GreetingRequest 提交为 replied 之前，
	// 所以首条消息必须能在关系门未放行的状态下写入。
	convSvc, msgSvc := newGateTestMessageService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{},
		nil,
	))
	ctx := context.Background()
	const (
		replier    = "greet_promo_replier"
		requester  = "greet_promo_requester"
		greetingID = "greet_promo_req_1"
		opening    = "看你也去过老君山，下次同行？"
	)

	resolvedAt := time.Date(2026, time.July, 31, 8, 0, 0, 0, time.UTC)
	intersection := &model.GreetingIntersectionSnapshot{
		IntersectionID: "intersection_1",
		EvidenceID:     "evidence_1",
		SourceRef:      "coVisitedEntity",
		ObjectTypeRef:  "user",
		ObjectID:       replier,
		PrimaryText:    "你们都去过老君山",
		Dimension:      "destination",
		ResolvedAt:     resolvedAt,
	}
	conv, err := convSvc.CreateOrReuseDirect(ctx, replier, requester,
		application.DirectConversationPromotion{
			GreetingRequestID: greetingID,
			Intersection:      intersection,
		})
	if err != nil {
		t.Fatalf("promote greeting to direct conversation: %v", err)
	}
	if conv.OriginType != "greeting_reply" {
		t.Fatalf("originType = %q, want greeting_reply", conv.OriginType)
	}
	if conv.OriginGreetingRequestID != greetingID {
		t.Fatalf("originGreetingRequestId = %q, want %q", conv.OriginGreetingRequestID, greetingID)
	}
	if conv.OriginIntersectionSnapshot == nil ||
		conv.OriginIntersectionSnapshot.PrimaryText != intersection.PrimaryText ||
		!conv.OriginIntersectionSnapshot.ResolvedAt.Equal(resolvedAt) {
		t.Fatalf("origin intersection snapshot was not frozen: %+v", conv.OriginIntersectionSnapshot)
	}

	if err := msgSvc.SendGreetingOpeningMessage(
		ctx, conv.ID, requester, opening, "greeting:"+greetingID,
	); err != nil {
		t.Fatalf("seed greeting opening message: %v", err)
	}
	// 同一次回复重放（用户重复点「同意」/上游重试）不得写出第二条。
	if err := msgSvc.SendGreetingOpeningMessage(
		ctx, conv.ID, requester, opening, "greeting:"+greetingID,
	); err != nil {
		t.Fatalf("replayed promotion must be idempotent: %v", err)
	}

	messages, err := msgSvc.ListMessages(ctx, application.ListMessagesRequest{
		ConversationId: conv.ID,
		ViewerID:       replier,
		Limit:          20,
	})
	if err != nil {
		t.Fatalf("list messages: %v", err)
	}
	if len(messages) != 1 {
		t.Fatalf("want exactly 1 seeded message, got %d", len(messages))
	}
	seeded := messages[0].Message
	if seeded.SenderID != requester {
		// 这句话是发起者写的，不能改署名成系统或回复方。
		t.Fatalf("opening message sender = %q, want %q", seeded.SenderID, requester)
	}
	if seeded.Content != opening {
		t.Fatalf("opening message content = %q, want %q", seeded.Content, opening)
	}
	if seeded.Type != "text" {
		t.Fatalf("opening message type = %q, want text (真人说的话不是系统消息)", seeded.Type)
	}

	// 会话预览必须已被首条消息更新，否则回复方在会话列表里看到的仍是空会话。
	refreshed, err := convSvc.GetConversation(ctx, conv.ID)
	if err != nil {
		t.Fatalf("reload conversation: %v", err)
	}
	if refreshed.LastMessagePreview == "" {
		t.Fatal("promoted conversation must expose the opening message as preview")
	}
}

// 没写话的打招呼不得凭空生成一句问候。
func TestGreetingPromotion_EmptyOpeningMessageWritesNothing(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	convSvc, msgSvc := newGateTestMessageService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{},
		nil,
	))
	ctx := context.Background()
	conv, err := convSvc.CreateOrReuseDirect(ctx, "greet_silent_replier", "greet_silent_requester",
		application.DirectConversationPromotion{GreetingRequestID: "greet_silent_1"})
	if err != nil {
		t.Fatalf("promote greeting: %v", err)
	}
	if err := msgSvc.SendGreetingOpeningMessage(
		ctx, conv.ID, "greet_silent_requester", "   ", "greeting:greet_silent_1",
	); err != nil {
		t.Fatalf("blank opening message must be a no-op, got %v", err)
	}
	messages, err := msgSvc.ListMessages(ctx, application.ListMessagesRequest{
		ConversationId: conv.ID,
		ViewerID:       "greet_silent_replier",
		Limit:          20,
	})
	if err != nil {
		t.Fatalf("list messages: %v", err)
	}
	if len(messages) != 0 {
		t.Fatalf("blank greeting must not fabricate a message, got %d", len(messages))
	}
}

// 复用既有会话时不得改写来源：老私信关系不应被后来的打招呼算成破冰新增。
func TestGreetingPromotion_ReusedConversationKeepsOriginalOrigin(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	convSvc, _ := newGateTestMessageService(t, relationshipGateForContractTest(
		t,
		application.RelationshipCapability{
			CanSendMessage:        true,
			HasFormalConversation: true,
		},
		nil,
	))
	ctx := context.Background()
	first, err := convSvc.CreateOrReuseDirect(ctx, "greet_reuse_a", "greet_reuse_b",
		application.DirectConversationPromotion{})
	if err != nil {
		t.Fatalf("create direct conversation: %v", err)
	}
	if first.OriginType != "direct_init" {
		t.Fatalf("plain direct conversation originType = %q, want direct_init", first.OriginType)
	}
	again, err := convSvc.CreateOrReuseDirect(ctx, "greet_reuse_a", "greet_reuse_b",
		application.DirectConversationPromotion{GreetingRequestID: "greet_reuse_1"})
	if err != nil {
		t.Fatalf("reuse direct conversation: %v", err)
	}
	if again.ID != first.ID {
		t.Fatalf("promotion must reuse the existing conversation, got %s want %s", again.ID, first.ID)
	}
	if again.OriginType != "direct_init" || again.OriginGreetingRequestID != "" {
		t.Fatalf("reused conversation must keep its original origin, got %q/%q",
			again.OriginType, again.OriginGreetingRequestID)
	}
}
