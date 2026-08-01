package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestSendMessageSeqAssignment(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"seq test","initialMemberIds":["user_test_002"]}`)
	convId := conv["id"].(string)

	msg1 := sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"uuid-1"}`)
	msg2 := sendMessage(t, convId, `{"type":"text","content":"world","clientMsgId":"uuid-2"}`)

	seq1 := int64(msg1["seq"].(float64))
	seq2 := int64(msg2["seq"].(float64))

	if seq2 <= seq1 {
		t.Errorf("seq should be monotonically increasing: seq1=%d, seq2=%d", seq1, seq2)
	}

	if msg1["messageId"] == nil {
		t.Error("response missing messageId")
	}
	if msg1["timestamp"] == nil {
		t.Error("response missing timestamp")
	}
}

func TestSendMessageClientMsgIdDedup(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"dedup test","initialMemberIds":["user_test_002"]}`)
	convId := conv["id"].(string)

	msg1 := sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"dedup-uuid-1"}`)
	msg2 := sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"dedup-uuid-1"}`)

	if msg1["messageId"] != msg2["messageId"] {
		t.Errorf("dedup failed: different messageId returned for same clientMsgId: %v vs %v",
			msg1["messageId"], msg2["messageId"])
	}

	seq1 := int64(msg1["seq"].(float64))
	seq2 := int64(msg2["seq"].(float64))
	if seq1 != seq2 {
		t.Errorf("dedup failed: different seq returned: %d vs %d", seq1, seq2)
	}

	messageID := msg1["messageId"].(string)
	assertCollectionCount(t, "messages", bson.M{"_id": messageID}, 1)
	assertCollectionCount(t, "messages_command_receipts", bson.M{"messageId": messageID}, 1)
	assertCollectionCount(t, "messages_outbox", bson.M{"aggregateId": messageID}, 1)
	waitForExactCollectionCount(t, "messages_outbox", bson.M{
		"aggregateId": messageID,
		"status":      "dispatched",
	}, 1)
	waitForExactCollectionCount(t, "messages_projection_checkpoints", bson.M{
		"_id": "message:chat-api-integration",
	}, 1)
}

func TestSendMessageClientMsgIdConflict(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"conflict test","initialMemberIds":["user_test_002"]}`)
	convID := conv["id"].(string)
	first := sendMessage(t, convID, `{"type":"text","content":"first","clientMsgId":"conflict-uuid-1"}`)
	conflict := doPost(
		t,
		"/chat/conversations/"+convID+"/messages",
		`{"type":"text","content":"different","clientMsgId":"conflict-uuid-1"}`,
		"user_test_001",
		http.StatusConflict,
	)
	if conflict["code"] != "CHAT.USER.message_idempotency_conflict" {
		t.Fatalf("expected stable idempotency conflict, got %#v", conflict)
	}
	assertCollectionCount(t, "messages", bson.M{
		"conversationId": convID,
		"senderId":       "user_test_001",
		"clientMsgId":    "conflict-uuid-1",
	}, 1)
	assertCollectionCount(t, "messages_command_receipts", bson.M{"messageId": first["messageId"]}, 1)
	assertSequenceValue(t, "messages_sequences", convID, 1)
	assertSequenceValue(t, "messages_outbox_sequences", "Message", 1)
}

func TestSendMessageTypedCardRejectsRemovedMapAndRoundTrips(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	conv := createConversation(t, `{"type":"group","title":"typed card"}`)
	convID := conv["id"].(string)

	removed := doPost(
		t,
		"/chat/conversations/"+convID+"/messages",
		`{"type":"card","content":"removed","clientMsgId":"removed-card","cardPayload":{"title":"removed"}}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if removed["code"] != "CHAT.USER.message_invalid" {
		t.Fatalf("removed cardPayload must be rejected: %#v", removed)
	}
	for _, legacyKind := range []string{"profileQr", "post", "userProfile", "entityProfile"} {
		legacy := doPost(
			t,
			"/chat/conversations/"+convID+"/messages",
			fmt.Sprintf(
				`{"type":"card","clientMsgId":"legacy-%s","card":{"kind":%q,"title":"legacy"}}`,
				legacyKind,
				legacyKind,
			),
			"user_test_001",
			http.StatusBadRequest,
		)
		if legacy["code"] != "CHAT.USER.message_invalid" {
			t.Fatalf("legacy card kind %q must be rejected: %#v", legacyKind, legacy)
		}
	}

	created := sendMessage(t, convID, `{
		"type":"card",
		"content":"查看分享",
		"clientMsgId":"typed-card",
		"card":{
			"kind":"content_post",
			"title":"城市漫步",
			"subtitle":"周末路线",
			"objectRef":{"objectTypeRef":"post","objectId":"post_001","routeId":"contentDetail"},
			"attributes":[{"name":"postId","value":"post_001"}]
		}
	}`)
	if created["messageId"] == nil {
		t.Fatalf("typed card response missing messageId: %#v", created)
	}

	code, listed := doGet(t, "/chat/conversations/"+convID+"/messages?limit=10", "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("list typed card: status=%d body=%#v", code, listed)
	}
	items := listed["items"].([]any)
	card := items[0].(map[string]any)["card"].(map[string]any)
	if card["kind"] != "content_post" || card["title"] != "城市漫步" {
		t.Fatalf("typed card projection mismatch: %#v", card)
	}
	objectRef := card["objectRef"].(map[string]any)
	if objectRef["objectTypeRef"] != "post" || objectRef["objectId"] != "post_001" ||
		objectRef["routeId"] != "contentDetail" {
		t.Fatalf("typed card objectRef mismatch: %#v", objectRef)
	}
	attributes := card["attributes"].([]any)
	if len(attributes) != 1 || attributes[0].(map[string]any)["name"] != "postId" {
		t.Fatalf("typed card attributes mismatch: %#v", attributes)
	}

	invalid := doPost(
		t,
		"/chat/conversations/"+convID+"/messages",
		`{"type":"text","content":"invalid","clientMsgId":"text-with-card","card":{"kind":"content_post","title":"x","attributes":[]}}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if invalid["code"] != "CHAT.USER.message_invalid" {
		t.Fatalf("non-card message carrying card must be rejected: %#v", invalid)
	}

	missingObjectRef := doPost(
		t,
		"/chat/conversations/"+convID+"/messages",
		`{"type":"card","clientMsgId":"card-without-object-ref","card":{"kind":"content_post","title":"x","attributes":[]}}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if missingObjectRef["code"] != "CHAT.USER.message_invalid" {
		t.Fatalf("actionable card without objectRef must be rejected: %#v", missingObjectRef)
	}
}

func assertCollectionCount(t *testing.T, collection string, filter bson.M, want int64) {
	t.Helper()
	got, err := requireMongoDB(t).Collection(collection).CountDocuments(context.Background(), filter)
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	if got != want {
		t.Fatalf("%s count = %d, want %d (filter=%v)", collection, got, want, filter)
	}
}

func assertSequenceValue(t *testing.T, collection string, id string, want int64) {
	t.Helper()
	var document struct {
		Seq int64 `bson:"seq"`
	}
	if err := requireMongoDB(t).Collection(collection).FindOne(
		context.Background(),
		bson.M{"_id": id},
	).Decode(&document); err != nil {
		t.Fatalf("read %s sequence: %v", collection, err)
	}
	if document.Seq != want {
		t.Fatalf("%s sequence = %d, want %d", collection, document.Seq, want)
	}
}

func TestListMessages(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"list test"}`)
	convId := conv["id"].(string)

	for i := 0; i < 5; i++ {
		sendMessage(t, convId, fmt.Sprintf(`{"type":"text","content":"msg %d","clientMsgId":"list-uuid-%d"}`, i, i))
	}

	code, result := doGet(t, "/chat/conversations/"+convId+"/messages?limit=10", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items array")
	}
	if len(items) != 5 {
		t.Errorf("expected 5 messages, got %d", len(items))
	}
	first, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("message item must be object, got %T", items[0])
	}
	if _, exists := first["senderDisplayNameSnapshot"]; exists {
		t.Fatalf("wire must not leak storage snapshot field names: %#v", first)
	}
	if _, exists := first["senderAvatarUrlSnapshot"]; exists {
		t.Fatalf("wire must not leak storage snapshot field names: %#v", first)
	}
	if _, ok := first["senderName"].(string); !ok {
		t.Fatalf("wire must expose canonical senderName: %#v", first)
	}
	if _, ok := first["senderAvatar"].(string); !ok {
		t.Fatalf("wire must expose canonical senderAvatar: %#v", first)
	}

	code, firstPage := doGet(
		t,
		"/chat/conversations/"+convId+"/messages?limit=2",
		"user_test_001",
	)
	if code != http.StatusOK {
		t.Fatalf("first message page status=%d body=%#v", code, firstPage)
	}
	nextBeforeSeq, ok := firstPage["nextBeforeSeq"].(float64)
	if !ok || nextBeforeSeq <= 0 {
		t.Fatalf("first message page must expose nextBeforeSeq: %#v", firstPage)
	}
	if _, legacyCursorPresent := firstPage["cursor"]; legacyCursorPresent {
		t.Fatalf("message page must not emit retired cursor: %#v", firstPage)
	}
	code, secondPage := doGet(
		t,
		fmt.Sprintf(
			"/chat/conversations/%s/messages?limit=2&beforeSeq=%d",
			convId,
			int64(nextBeforeSeq),
		),
		"user_test_001",
	)
	if code != http.StatusOK {
		t.Fatalf("second message page status=%d body=%#v", code, secondPage)
	}
	secondItems, ok := secondPage["items"].([]any)
	if !ok || len(secondItems) != 2 {
		t.Fatalf("second message page must contain two items: %#v", secondPage)
	}
}

func TestMessageOperationsDenyNonMemberPersona(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	conv := createConversation(t, `{"type":"direct","title":"BOLA contract","initialMemberIds":["user_test_002"]}`)
	convID := conv["id"].(string)
	message := sendMessage(t, convID, `{"type":"text","content":"owner message","clientMsgId":"owner-message"}`)
	messageID := message["messageId"].(string)

	sendFailure := doPost(
		t,
		"/chat/conversations/"+convID+"/messages",
		`{"type":"text","content":"intrusion","clientMsgId":"intruder-send"}`,
		"persona_intruder",
		http.StatusForbidden,
	)
	if sendFailure["code"] != "CHAT.USER.blocked" {
		t.Fatalf("non-member send must fail closed: %#v", sendFailure)
	}

	listStatus, listFailure := doGet(
		t,
		"/chat/conversations/"+convID+"/messages?limit=10",
		"persona_intruder",
	)
	if listStatus != http.StatusForbidden || listFailure["code"] != "CHAT.USER.blocked" {
		t.Fatalf("non-member list must fail closed: status=%d body=%#v", listStatus, listFailure)
	}

	syncFailure := doPost(
		t,
		"/chat/conversations/"+convID+"/sync",
		`{"lastSeq":0,"limit":10}`,
		"persona_intruder",
		http.StatusForbidden,
	)
	if syncFailure["code"] != "CHAT.USER.blocked" {
		t.Fatalf("non-member sync must fail closed: %#v", syncFailure)
	}

	for operation, path := range map[string]string{
		"recall":   "/chat/conversations/" + convID + "/messages/" + messageID + "/recall",
		"markRead": "/chat/conversations/" + convID + "/messages/" + messageID + "/read",
	} {
		failure := doPost(t, path, `{}`, "persona_intruder", http.StatusForbidden)
		if failure["code"] != "CHAT.USER.blocked" {
			t.Fatalf("non-member %s must fail closed: %#v", operation, failure)
		}
	}
	receiptStatus, receiptFailure := doGet(
		t,
		"/chat/conversations/"+convID+"/messages/"+messageID+"/receipts",
		"persona_intruder",
	)
	if receiptStatus != http.StatusForbidden || receiptFailure["code"] != "CHAT.USER.blocked" {
		t.Fatalf("non-member receipts must fail closed: status=%d body=%#v", receiptStatus, receiptFailure)
	}
	assertCollectionCount(t, "messages", bson.M{"conversationId": convID}, 1)
}

func TestMessageOperationsRejectCrossConversationMessageReference(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	first := createConversation(t, `{"type":"group","title":"first"}`)
	second := createConversation(t, `{"type":"group","title":"second"}`)
	firstID := first["id"].(string)
	secondID := second["id"].(string)
	message := sendMessage(t, firstID, `{"type":"text","content":"first only","clientMsgId":"cross-conversation"}`)
	messageID := message["messageId"].(string)

	for operation, path := range map[string]string{
		"recall":   "/chat/conversations/" + secondID + "/messages/" + messageID + "/recall",
		"markRead": "/chat/conversations/" + secondID + "/messages/" + messageID + "/read",
	} {
		failure := doPost(t, path, `{}`, "user_test_001", http.StatusNotFound)
		if failure["code"] != "CHAT.USER.message_not_found" {
			t.Fatalf("cross-conversation %s must hide target: %#v", operation, failure)
		}
	}
	receiptStatus, receiptFailure := doGet(
		t,
		"/chat/conversations/"+secondID+"/messages/"+messageID+"/receipts",
		"user_test_001",
	)
	if receiptStatus != http.StatusNotFound || receiptFailure["code"] != "CHAT.USER.message_not_found" {
		t.Fatalf("cross-conversation receipts must hide target: status=%d body=%#v", receiptStatus, receiptFailure)
	}
}

func TestRecallMessageWithinTimeLimit(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"recall test","initialMemberIds":["user_test_002"]}`)
	convId := conv["id"].(string)

	msg := sendMessage(t, convId, `{"type":"text","content":"to recall","clientMsgId":"recall-uuid-1"}`)
	msgId := msg["messageId"].(string)

	result := doPost(t, "/chat/conversations/"+convId+"/messages/"+msgId+"/recall",
		`{}`, "user_test_001", 200)

	if result["status"] != "recalled" {
		t.Errorf("expected status=recalled, got %v", result["status"])
	}
}
