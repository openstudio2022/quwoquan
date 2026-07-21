package api_integration

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	streamadapter "quwoquan_service/services/notification-service/internal/adapters/stream"
	"quwoquan_service/services/notification-service/internal/application"
	"quwoquan_service/services/notification-service/internal/infrastructure/persistence"
)

// GWT1（interaction-notification-inbox）：真实 Redis Stream + Mongo 链路上，
// 七源事件一次且仅一次生成 AppMessage，read 推进后 unread 收敛。
func TestInteractionNotificationStreamProjectsOnce(t *testing.T) {
	resetNotificationCollections(t)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("interaction notification api_integration requires real Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancelCleanup()
		_ = realRedis.Close(cleanupCtx)
	})
	if err := realRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush redis: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: realRedis.Addr,
				Password: realRedis.Password, DB: 0, TLS: realRedis.TLS,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		t.Fatalf("redis router: %v", err)
	}
	redisClient := redisRouter.Scene("general")

	commands, err := application.NewAppMessageCommandFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("command facade: %v", err)
	}
	queries, err := application.NewAppMessageQueryFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationAppMessageStore,
	)
	if err != nil {
		t.Fatalf("query facade: %v", err)
	}
	failures := persistence.NewMongoInteractionFailureStore(notificationMongoDB)
	if err := failures.EnsureIndexes(ctx); err != nil {
		t.Fatalf("failure store indexes: %v", err)
	}
	messageTransport, err := runtimemessaging.NewRedisMessageTransport(
		redisClient,
		redisClient,
	)
	if err != nil {
		t.Fatalf("message transport: %v", err)
	}
	consumer, err := streamadapter.NewInteractionNotificationConsumer(
		messageTransport, commands, failures, "api-integration-consumer", nil,
	)
	if err != nil {
		t.Fatalf("consumer: %v", err)
	}

	payload, err := json.Marshal(map[string]any{
		"commentId": "cmt-api-1", "postId": "post-api-1", "version": 1,
		"postAuthorId": "recipient-api-1", "authorId": "actor-api-1",
		"createdAt": time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	appendEvent := func() {
		if _, err := redisClient.XAdd(ctx, "events.content.comment_lifecycle", map[string]string{
			"eventId":          "evt-api-comment-1",
			"eventType":        "CommentCreated",
			"aggregateType":    "Comment",
			"aggregateId":      "cmt-api-1",
			"aggregateVersion": "1",
			"payload":          string(payload),
			"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
		}); err != nil {
			t.Fatalf("xadd: %v", err)
		}
	}
	appendEvent()
	appendEvent() // at-least-once 重放
	replyPayload, err := json.Marshal(map[string]any{
		"commentId":        "cmt-api-reply-1",
		"postId":           "post-api-1",
		"version":          1,
		"postAuthorId":     "recipient-api-1",
		"authorId":         "actor-api-1",
		"replyToUserId":    "recipient-api-reply",
		"mentionedUserIds": []string{"recipient-api-reply", "recipient-api-mention", "actor-api-1"},
		"createdAt":        time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("marshal reply payload: %v", err)
	}
	if _, err := redisClient.XAdd(ctx, "events.content.comment_lifecycle", map[string]string{
		"eventId":          "evt-api-comment-reply-1",
		"eventType":        "CommentCreated",
		"aggregateType":    "Comment",
		"aggregateId":      "cmt-api-reply-1",
		"aggregateVersion": "1",
		"payload":          string(replyPayload),
		"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd Comment reply: %v", err)
	}
	pinPayload, err := json.Marshal(map[string]any{
		"commentId":       "cmt-api-pin-1",
		"postId":          "post-api-1",
		"commentAuthorId": "recipient-api-pin",
		"operatorId":      "recipient-api-1",
		"isPinned":        true,
	})
	if err != nil {
		t.Fatalf("marshal Comment pin payload: %v", err)
	}
	if _, err := redisClient.XAdd(ctx, "events.content.comment_lifecycle", map[string]string{
		"eventId":          "evt-api-comment-pin-1",
		"eventType":        "CommentPinChanged",
		"aggregateType":    "Comment",
		"aggregateId":      "cmt-api-pin-1",
		"aggregateVersion": "2",
		"payload":          string(pinPayload),
		"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd Comment pin: %v", err)
	}

	greetingValues := map[string]string{
		"eventId":                      "greeting:g-api-1:GreetingRequestSent",
		"eventName":                    "GreetingRequestSent",
		"id":                           "g-api-1",
		"requesterSubAccountId":        "actor-api-1",
		"targetSubAccountId":           "recipient-api-1",
		"targetAllowsStrangerGreeting": "true",
		"occurredAt":                   time.Now().UTC().Format(time.RFC3339Nano),
	}
	if _, err := redisClient.XAdd(ctx, "events.user.greeting", greetingValues); err != nil {
		t.Fatalf("xadd greeting: %v", err)
	}
	reportPayload, err := json.Marshal(map[string]any{
		"reportId":          "report-api-1",
		"reporterAccountId": "recipient-api-1",
		"targetType":        "post",
		"targetId":          "post-api-1",
		"resolution":        "delete_content",
	})
	if err != nil {
		t.Fatalf("marshal report payload: %v", err)
	}
	if _, err := redisClient.XAdd(ctx, "events.content.report_lifecycle", map[string]string{
		"eventId":     "evt-api-report-1",
		"eventType":   "content.report.resolved",
		"aggregateId": "report-api-1",
		"payload":     string(reportPayload),
		"occurredAt":  time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd report result: %v", err)
	}
	homepageClaimPayload, err := json.Marshal(map[string]any{
		"claimRequestId":     "claim-api-1",
		"homepageId":         "homepage-api-1",
		"requesterPersonaId": "recipient-api-1",
		"status":             "approved",
	})
	if err != nil {
		t.Fatalf("marshal homepage claim payload: %v", err)
	}
	if _, err := redisClient.XAdd(ctx, "events.entity.homepage_lifecycle", map[string]string{
		"eventId":          "evt-api-homepage-claim-1",
		"eventType":        "HomepageClaimReviewed",
		"aggregateType":    "HomepageClaimRequest",
		"aggregateId":      "claim-api-1",
		"aggregateVersion": "2",
		"payload":          string(homepageClaimPayload),
		"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd homepage claim result: %v", err)
	}
	homepageStatusPayload, err := json.Marshal(map[string]any{
		"reportId":          "status-api-1",
		"homepageId":        "homepage-api-1",
		"reporterPersonaId": "recipient-api-1",
		"status":            "confirmed_offline",
	})
	if err != nil {
		t.Fatalf("marshal homepage status payload: %v", err)
	}
	if _, err := redisClient.XAdd(ctx, "events.entity.homepage_lifecycle", map[string]string{
		"eventId":          "evt-api-homepage-status-1",
		"eventType":        "HomepageStatusReportReviewed",
		"aggregateType":    "HomepageStatusReport",
		"aggregateId":      "status-api-1",
		"aggregateVersion": "2",
		"payload":          string(homepageStatusPayload),
		"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
	}); err != nil {
		t.Fatalf("xadd homepage status result: %v", err)
	}

	deadline := time.Now().Add(20 * time.Second)
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil {
			t.Fatalf("consume: %v", err)
		}
		unread, err := queries.GetUnreadCount(ctx, "recipient-api-1")
		if err != nil {
			t.Fatalf("unread: %v", err)
		}
		replyUnread, replyErr := queries.GetUnreadCount(ctx, "recipient-api-reply")
		mentionUnread, mentionErr := queries.GetUnreadCount(ctx, "recipient-api-mention")
		pinUnread, pinErr := queries.GetUnreadCount(ctx, "recipient-api-pin")
		if replyErr != nil || mentionErr != nil || pinErr != nil {
			t.Fatalf(
				"read Comment fan-out unread counts: reply=%v mention=%v pin=%v",
				replyErr,
				mentionErr,
				pinErr,
			)
		}
		if unread.UnreadCount == 5 &&
			replyUnread.UnreadCount == 1 &&
			mentionUnread.UnreadCount == 1 &&
			pinUnread.UnreadCount == 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf(
				"unexpected unread fan-out main=%d reply=%d mention=%d pin=%d",
				unread.UnreadCount,
				replyUnread.UnreadCount,
				mentionUnread.UnreadCount,
				pinUnread.UnreadCount,
			)
		}
		time.Sleep(100 * time.Millisecond)
	}

	inbox, err := queries.ListInbox(ctx, application.AppMessageInboxQuery{
		UserID: "recipient-api-1", Limit: 10,
	})
	if err != nil {
		t.Fatalf("list inbox: %v", err)
	}
	if len(inbox.Items) != 5 {
		t.Fatalf("inbox items=%d want=5 (replay must not duplicate)", len(inbox.Items))
	}
	foundReport := false
	foundHomepageClaim := false
	foundHomepageStatus := false
	for _, item := range inbox.Items {
		if item.Target.TargetType == "report" &&
			item.Target.TargetID == "report-api-1" {
			foundReport = true
		}
		if item.Source == "homepage_claim_result" &&
			item.Target.TargetType == "homepage" &&
			item.Target.TargetID == "homepage-api-1" {
			foundHomepageClaim = true
		}
		if item.Source == "homepage_status_result" &&
			item.Target.TargetType == "homepage" &&
			item.Target.TargetID == "homepage-api-1" {
			foundHomepageStatus = true
		}
	}
	if !foundReport {
		t.Fatalf("report result notification missing: %+v", inbox.Items)
	}
	if !foundHomepageClaim || !foundHomepageStatus {
		t.Fatalf("homepage governance result notifications missing: %+v", inbox.Items)
	}
	commentFanout := []struct {
		userID   string
		source   string
		sourceID string
	}{
		{
			userID:   "recipient-api-reply",
			source:   "comment",
			sourceID: "cmt-api-reply-1",
		},
		{
			userID:   "recipient-api-mention",
			source:   "comment_mention",
			sourceID: "cmt-api-reply-1",
		},
		{
			userID:   "recipient-api-pin",
			source:   "comment_pin",
			sourceID: "cmt-api-pin-1",
		},
	}
	for _, expected := range commentFanout {
		fanoutInbox, err := queries.ListInbox(ctx, application.AppMessageInboxQuery{
			UserID: expected.userID,
			Limit:  10,
		})
		if err != nil {
			t.Fatalf("list %s Comment notification inbox: %v", expected.userID, err)
		}
		if len(fanoutInbox.Items) != 1 {
			t.Fatalf(
				"%s Comment notification count=%d want=1",
				expected.userID,
				len(fanoutInbox.Items),
			)
		}
		item := fanoutInbox.Items[0]
		if item.Source != expected.source ||
			item.SourceID != expected.sourceID ||
			item.Target.TargetType != "post" ||
			item.Target.TargetID != "post-api-1" {
			t.Fatalf(
				"%s Comment deep-link identity drifted: %+v",
				expected.userID,
				item,
			)
		}
	}

	first := inbox.Items[0]
	if _, err := commands.MarkRead(ctx, "recipient-api-1", first.MessageID); err != nil {
		t.Fatalf("mark read: %v", err)
	}
	unread, err := queries.GetUnreadCount(ctx, "recipient-api-1")
	if err != nil {
		t.Fatalf("unread after read: %v", err)
	}
	if unread.UnreadCount != 4 {
		t.Fatalf("unread after read=%d want=4", unread.UnreadCount)
	}

	// 其他用户的 inbox 保持隔离。
	otherInbox, err := queries.ListInbox(ctx, application.AppMessageInboxQuery{
		UserID: "actor-api-1", Limit: 10,
	})
	if err != nil {
		t.Fatalf("actor inbox: %v", err)
	}
	if len(otherInbox.Items) != 0 {
		t.Fatalf("actor must not receive self-interaction notifications: %d", len(otherInbox.Items))
	}
}
