package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/application"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

func TestUserAccountClosedProjectionDeletesPrivateStateAndAnonymizesAudit(
	t *testing.T,
) {
	cleanAll(t)
	ctx := context.Background()
	db := requireMongoDB(t)
	redis := redisRouter.Scene("general")
	projection := persistence.NewMongoUserAccountClosedProjection(db, redis)
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure UserAccountClosed indexes: %v", err)
	}

	const (
		accountID      = "account-close-private"
		personaA       = "persona-close-a"
		personaB       = "persona-close-b"
		otherUser      = "persona-still-active"
		conversationID = "conversation-close-audit"
	)
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	insertClosureDocument(t, "conversations", bson.M{
		"_id":                   conversationID,
		"creatorId":             personaA,
		"announcementUpdatedBy": personaA,
		"memberCount":           3,
		"membersRosterRevision": int64(4),
		"avatarUrl":             "https://private.example/avatar.png",
		"groupAvatarAssetId":    "private-avatar-asset",
		"groupAvatarSourceHash": "private-source-hash",
		"updatedAt":             now,
	})
	for _, member := range []bson.M{
		{
			"_id": "member-close-a", "conversationId": conversationID,
			"userId": personaA, "displayName": "隐私甲", "avatarUrl": "private-a",
			"invitedBy": personaA,
		},
		{
			"_id": "member-close-b", "conversationId": conversationID,
			"userId": personaB, "displayName": "隐私乙", "avatarUrl": "private-b",
			"invitedBy": personaA,
		},
		{
			"_id": "member-active", "conversationId": conversationID,
			"userId": otherUser, "displayName": "保留用户",
			"invitedBy": personaA,
		},
	} {
		insertClosureDocument(t, "conversation_memberships", member)
	}
	for _, state := range []bson.M{
		{
			"_id": "state-close-a", "conversationId": conversationID,
			"userId": personaA, "readSeq": int64(2), "muted": true,
		},
		{
			"_id": "state-close-b", "conversationId": conversationID,
			"userId": personaB, "readSeq": int64(1), "pinned": true,
		},
		{
			"_id": "state-active", "conversationId": conversationID,
			"userId": otherUser, "readSeq": int64(3),
		},
	} {
		insertClosureDocument(t, "conversation_user_states", state)
	}
	for _, message := range []bson.M{
		{
			"_id": "message-close-a", "conversationId": conversationID,
			"seq": int64(1), "clientMsgId": "client-close-a",
			"senderId": personaA, "senderDisplayNameSnapshot": "隐私甲",
			"senderAvatarUrlSnapshot": "private-a", "personaContextVersion": int64(9),
			"mentions": []string{personaB, otherUser}, "timestamp": now,
		},
		{
			"_id": "message-close-b", "conversationId": conversationID,
			"seq": int64(2), "clientMsgId": "client-close-b",
			"senderId": personaB, "senderDisplayNameSnapshot": "隐私乙",
			"senderAvatarUrlSnapshot": "private-b", "personaContextVersion": int64(3),
			"mentions": []string{personaA}, "timestamp": now.Add(time.Second),
		},
		{
			"_id": "message-active", "conversationId": conversationID,
			"seq": int64(3), "clientMsgId": "client-active",
			"senderId": otherUser, "mentions": []string{personaA, personaB},
			"timestamp": now.Add(2 * time.Second),
		},
	} {
		message["type"] = "text"
		message["content"] = "必须保留的消息审计"
		message["status"] = "sent"
		message["version"] = int64(1)
		insertClosureDocument(t, "messages", message)
	}
	insertClosureDocument(t, "message_receipts", bson.M{
		"_id": "receipt-close", "messageId": "message-active",
		"conversationId": conversationID, "userId": personaA, "readAt": now,
	})
	insertClosureDocument(t, "message_receipts", bson.M{
		"_id": "receipt-active", "messageId": "message-active",
		"conversationId": conversationID, "userId": otherUser, "readAt": now,
	})
	insertClosureDocument(t, "messages_command_receipts", bson.M{
		"_id": "message-command-close", "messageId": "message-close-a",
		"commandDigest": "private-command-digest",
		"result": bson.M{
			"senderId": personaA, "senderDisplayNameSnapshot": "隐私甲",
		},
		"createdAt": now,
	})
	insertClosureDocument(t, "messages_command_receipts", bson.M{
		"_id": "message-command-active", "messageId": "message-active",
		"commandDigest": "active-command-digest",
		"result": bson.M{
			"senderId": otherUser,
			"mentions": []string{personaA, personaB, otherUser},
		},
		"createdAt": now,
	})
	insertClosureDocument(t, "conversations_command_receipts", bson.M{
		"_id":           "conversation-command-close",
		"aggregateId":   conversationID,
		"commandName":   "UpdateAnnouncement",
		"commandDigest": "conversation-command-digest",
		"resultJson": []byte(`{
			"id":"conversation-close-audit",
			"creatorId":"persona-close-a",
			"announcementUpdatedBy":"persona-close-a",
			"avatarUrl":"private-conversation-avatar",
			"groupAvatarAssetId":"private-conversation-asset",
			"groupAvatarSourceHash":"private-conversation-source"
		}`),
		"createdAt": now, "expiresAt": now.Add(time.Hour),
	})
	insertClosureDocument(t, "conversation_user_states_command_receipts", bson.M{
		"_id": "user-state-command-close", "aggregateId": "state-close-a",
		"commandName": "MarkAsRead", "commandDigest": "private",
		"createdAt": now, "expiresAt": now.Add(time.Hour),
	})
	insertClosureDocument(t, "messages_outbox", bson.M{
		"_id": "message-outbox-close", "outboxSequence": int64(101),
		"aggregateId": "message-close-a", "aggregateVersion": int64(1),
		"eventType": "MessageSent", "conversationId": conversationID,
		"actorId": personaA, "payload": bson.M{
			"senderId": personaA, "senderDisplayNameSnapshot": "隐私甲",
			"senderAvatarUrlSnapshot": "private-a",
			"personaContextVersion":   int64(9),
			"mentions":                []string{personaB},
		},
		"status": "pending", "createdAt": now,
	})
	insertClosureDocument(t, "conversations_outbox", bson.M{
		"_id": "conversation-outbox-close", "outboxSequence": int64(201),
		"aggregateId": conversationID, "eventType": "ConversationCreated",
		"conversationId": conversationID, "actorId": personaA,
		"payload": bson.M{"creatorId": personaA}, "status": "pending",
		"createdAt": now,
	})
	insertClosureDocument(t, "conversation_memberships_outbox", bson.M{
		"_id": "membership-outbox-close", "outboxSequence": int64(301),
		"aggregateId": "member-close-b", "eventType": "MemberAdded",
		"conversationId": conversationID, "actorId": personaA,
		"payload": bson.M{
			"userId": personaB, "displayName": "隐私乙",
			"avatarUrl": "private-b", "invitedBy": personaA,
		},
		"status": "pending", "createdAt": now,
	})
	insertClosureDocument(t, "conversation_user_states_outbox", bson.M{
		"_id": "user-state-outbox-close", "outboxSequence": int64(401),
		"aggregateId": "state-close-a", "eventType": "ConversationReadWatermarkAdvanced",
		"conversationId": conversationID, "actorId": personaA,
		"payload": bson.M{"userId": personaA, "readSeq": int64(2)},
		"status":  "pending", "createdAt": now,
	})
	for _, task := range []struct {
		collection string
		id         string
		actor      string
	}{
		{"reliable_task_outbox", "task-outbox-close", personaA},
		{"reliable_async_task", "async-task-close", personaB},
	} {
		insertClosureDocument(t, task.collection, bson.M{
			"_id": task.id, "payload": bson.M{"actorID": task.actor},
		})
	}
	insertClosureDocument(t, "notification_outbox", bson.M{
		"_id": "notification-close", "payload": bson.M{"actorID": personaA},
		"recipientIds": []string{personaA, otherUser},
	})
	insertClosureDocument(t, "notification_delivery_ledger", bson.M{
		"_id": "ledger-close", "notificationId": "notification-close",
		"recipientId": personaA,
	})
	insertClosureDocument(t, "notification_delivery_ledger", bson.M{
		"_id": "ledger-active", "notificationId": "notification-close",
		"recipientId": otherUser,
	})
	if err := redis.Set(
		ctx,
		"sync:user:"+personaA+":latest",
		"2",
		0,
	); err != nil {
		t.Fatal(err)
	}
	for sequence := 1; sequence <= 2; sequence++ {
		if err := redis.Set(
			ctx,
			"sync:user:"+personaA+":patch:"+strconv.Itoa(sequence),
			"private-sync-patch",
			time.Hour,
		); err != nil {
			t.Fatal(err)
		}
	}

	event := application.UserAccountClosedEvent{
		EventID:        "event-close-chat-1",
		EventName:      application.UserAccountClosedEventName,
		AccountID:      accountID,
		AccountVersion: 7,
		UserID:         accountID,
		PersonaIDs:     []string{personaB, personaA},
		AccountState:   "closed",
		UpdatedAt:      now,
		OccurredAt:     now,
	}
	result, err := projection.ApplyUserAccountClosed(ctx, event)
	if err != nil {
		t.Fatalf("apply UserAccountClosed: %v", err)
	}
	if result.Replayed {
		t.Fatal("first application must not report replay")
	}

	messageA := closureDocument(t, "messages", "message-close-a")
	messageB := closureDocument(t, "messages", "message-close-b")
	messageActive := closureDocument(t, "messages", "message-active")
	anonymousA, _ := messageA["senderId"].(string)
	anonymousB, _ := messageB["senderId"].(string)
	if !strings.HasPrefix(anonymousA, "deleted_") ||
		!strings.HasPrefix(anonymousB, "deleted_") ||
		anonymousA == anonymousB ||
		anonymousA == personaA ||
		anonymousB == personaB {
		t.Fatalf(
			"personas must get distinct irreversible identities: a=%q b=%q",
			anonymousA,
			anonymousB,
		)
	}
	if messageA["senderDisplayNameSnapshot"] != "已注销用户" ||
		messageA["senderAvatarUrlSnapshot"] != "" ||
		messageA["personaContextVersion"] != int64(0) {
		t.Fatalf("message sender snapshot was not anonymized: %#v", messageA)
	}
	if containsClosureString(messageA["mentions"], personaB) ||
		containsClosureString(messageB["mentions"], personaA) ||
		containsClosureString(messageActive["mentions"], personaA) ||
		containsClosureString(messageActive["mentions"], personaB) {
		t.Fatal("closed identities must be removed from message mentions")
	}
	if messageActive["senderId"] != otherUser {
		t.Fatalf("unrelated sender was rebound: %#v", messageActive)
	}
	conversation := closureDocument(t, "conversations", conversationID)
	if conversation["creatorId"] != anonymousA ||
		conversation["announcementUpdatedBy"] != anonymousA ||
		closureInteger(conversation["memberCount"]) != 1 {
		t.Fatalf("conversation audit/roster mismatch: %#v", conversation)
	}
	activeMember := closureDocument(t, "conversation_memberships", "member-active")
	if activeMember["userId"] != otherUser ||
		activeMember["invitedBy"] != anonymousA {
		t.Fatalf("remaining membership was rebound incorrectly: %#v", activeMember)
	}
	var conversationReceipt struct {
		ResultJSON []byte `bson:"resultJson"`
	}
	if err := db.Collection("conversations_command_receipts").FindOne(
		ctx,
		bson.M{"_id": "conversation-command-close"},
	).Decode(&conversationReceipt); err != nil {
		t.Fatalf("read anonymized conversation receipt: %v", err)
	}
	var conversationReceiptResult struct {
		CreatorID             string `json:"creatorId"`
		AnnouncementUpdatedBy string `json:"announcementUpdatedBy"`
		AvatarURL             string `json:"avatarUrl"`
		GroupAvatarAssetID    string `json:"groupAvatarAssetId"`
		GroupAvatarSourceHash string `json:"groupAvatarSourceHash"`
	}
	if err := json.Unmarshal(
		conversationReceipt.ResultJSON,
		&conversationReceiptResult,
	); err != nil {
		t.Fatalf("decode anonymized conversation receipt: %v", err)
	}
	if conversationReceiptResult.CreatorID != anonymousA ||
		conversationReceiptResult.AnnouncementUpdatedBy != anonymousA ||
		conversationReceiptResult.AvatarURL != "" ||
		conversationReceiptResult.GroupAvatarAssetID != "" ||
		conversationReceiptResult.GroupAvatarSourceHash != "" {
		t.Fatalf(
			"conversation command receipt was not anonymized: %#v",
			conversationReceiptResult,
		)
	}

	assertClosureCount(t, "conversation_memberships", bson.M{
		"userId": bson.M{"$in": []string{accountID, personaA, personaB}},
	}, 0)
	assertClosureCount(t, "conversation_user_states", bson.M{
		"userId": bson.M{"$in": []string{accountID, personaA, personaB}},
	}, 0)
	assertClosureCount(t, "message_receipts", bson.M{"userId": personaA}, 0)
	assertClosureCount(t, "message_receipts", bson.M{"userId": otherUser}, 1)
	assertClosureCount(t, "messages_command_receipts", bson.M{
		"result.senderId": personaA,
	}, 0)
	activeMessageReceipt := closureDocument(
		t,
		"messages_command_receipts",
		"message-command-active",
	)
	if containsClosureString(
		closureNestedValue(activeMessageReceipt["result"], "mentions"),
		personaA,
	) || containsClosureString(
		closureNestedValue(activeMessageReceipt["result"], "mentions"),
		personaB,
	) {
		t.Fatalf(
			"active message receipt retained closed mentions: %#v",
			activeMessageReceipt,
		)
	}
	assertClosureCount(t, "conversation_user_states_command_receipts", bson.M{
		"aggregateId": "state-close-a",
	}, 0)
	assertClosureCount(t, "conversation_user_states_outbox", bson.M{}, 0)
	assertClosureCount(t, "messages", bson.M{"conversationId": conversationID}, 3)
	assertClosureCount(t, "conversations", bson.M{"_id": conversationID}, 1)
	assertClosureCount(t, "notification_delivery_ledger", bson.M{
		"recipientId": personaA,
	}, 0)
	assertClosureCount(t, "notification_delivery_ledger", bson.M{
		"recipientId": otherUser,
	}, 1)

	notification := closureDocument(t, "notification_outbox", "notification-close")
	if containsClosureString(notification["recipientIds"], personaA) ||
		!containsClosureString(notification["recipientIds"], otherUser) {
		t.Fatalf("notification recipients were not cleaned: %#v", notification)
	}
	for _, task := range []struct {
		collection string
		id         string
		wantActor  string
	}{
		{"reliable_task_outbox", "task-outbox-close", anonymousA},
		{"reliable_async_task", "async-task-close", anonymousB},
		{"notification_outbox", "notification-close", anonymousA},
	} {
		document := closureDocument(t, task.collection, task.id)
		if closureNestedString(document["payload"], "actorID") != task.wantActor {
			t.Fatalf("%s actor was not anonymized: %#v", task.collection, document)
		}
	}
	for _, key := range []string{
		"sync:user:" + personaA + ":latest",
		"sync:user:" + personaA + ":patch:1",
		"sync:user:" + personaA + ":patch:2",
	} {
		if _, err := redis.Get(ctx, key); !errors.Is(err, rtredis.ErrKeyNotFound) {
			t.Fatalf("private sync state %q must be deleted, err=%v", key, err)
		}
	}

	inbox := closureDocument(t, "chat_user_account_closed_inbox", event.EventID)
	if _, found := inbox["accountId"]; found {
		t.Fatalf("inbox must not persist account identity: %#v", inbox)
	}
	if _, found := inbox["affectedConversationIds"]; found {
		t.Fatalf("completed inbox must not retain conversation linkage: %#v", inbox)
	}
	if inbox["eventDigest"] == "" || inbox["completedAt"] == nil {
		t.Fatalf("inbox lacks replay evidence: %#v", inbox)
	}

	replay, err := projection.ApplyUserAccountClosed(ctx, event)
	if err != nil || !replay.Replayed {
		t.Fatalf("replay must be idempotent: result=%+v err=%v", replay, err)
	}
	if got := closureDocument(t, "messages", "message-close-a")["senderId"]; got != anonymousA {
		t.Fatalf("replay changed anonymous identity: got=%v want=%s", got, anonymousA)
	}

	insertClosureDocument(t, "conversation_user_states", bson.M{
		"_id": "state-conflict", "conversationId": conversationID,
		"userId": "persona-conflict",
	})
	conflict := event
	conflict.PersonaIDs = append(
		append([]string(nil), event.PersonaIDs...),
		"persona-conflict",
	)
	if _, err := projection.ApplyUserAccountClosed(ctx, conflict); err == nil {
		t.Fatal("same eventId with different data must fail closed")
	}
	assertClosureCount(t, "conversation_user_states", bson.M{
		"userId": "persona-conflict",
	}, 1)
}

func insertClosureDocument(t *testing.T, collection string, document bson.M) {
	t.Helper()
	if _, err := requireMongoDB(t).Collection(collection).InsertOne(
		context.Background(),
		document,
	); err != nil {
		t.Fatalf("insert %s document: %v", collection, err)
	}
}

func closureDocument(t *testing.T, collection string, id string) bson.M {
	t.Helper()
	var document bson.M
	if err := requireMongoDB(t).Collection(collection).FindOne(
		context.Background(),
		bson.M{"_id": id},
	).Decode(&document); err != nil {
		t.Fatalf("read %s/%s: %v", collection, id, err)
	}
	return document
}

func assertClosureCount(
	t *testing.T,
	collection string,
	filter bson.M,
	want int64,
) {
	t.Helper()
	got, err := requireMongoDB(t).Collection(collection).CountDocuments(
		context.Background(),
		filter,
	)
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	if got != want {
		t.Fatalf("%s count=%d want=%d filter=%#v", collection, got, want, filter)
	}
}

func containsClosureString(value any, target string) bool {
	switch values := value.(type) {
	case bson.A:
		for _, value := range values {
			if value == target {
				return true
			}
		}
	case []string:
		for _, value := range values {
			if value == target {
				return true
			}
		}
	}
	return false
}

func closureInteger(value any) int64 {
	switch number := value.(type) {
	case int:
		return int64(number)
	case int32:
		return int64(number)
	case int64:
		return number
	default:
		return -1
	}
}

func closureNestedString(value any, key string) string {
	result, _ := closureNestedValue(value, key).(string)
	return result
}

func closureNestedValue(value any, key string) any {
	switch document := value.(type) {
	case bson.M:
		return document[key]
	case bson.D:
		for _, element := range document {
			if element.Key == key {
				return element.Value
			}
		}
	}
	return nil
}
