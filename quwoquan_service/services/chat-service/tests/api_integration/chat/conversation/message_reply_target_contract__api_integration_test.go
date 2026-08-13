// replyToMessageId 的 HTTP→Mongo→outbox 一致性与重放幂等：
// 引用同会话已存在消息成功落库并进入事件 payload；不存在或跨会话引用
// 返回 canonical MessageInvalid；同 clientMsgId 重放不产生第二条消息。
//
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/message-interaction-polish/spec.md#gwt-004
package api_integration

import (
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestReplyTargetPersistsAndReplaysIdempotently(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"reply target"}`)
	convID := conv["id"].(string)
	origin := sendMessage(t, convID, `{"type":"text","content":"原始消息","clientMsgId":"reply-origin"}`)
	originID := origin["messageId"].(string)

	reply := sendMessage(
		t,
		convID,
		`{"type":"text","content":"引用回复","clientMsgId":"reply-once","replyToMessageId":"`+originID+`"}`,
	)
	replyID := reply["messageId"].(string)

	// Mongo 持久一致：消息文档携带引用。
	assertCollectionCount(t, "messages", bson.M{
		"_id":              replyID,
		"replyToMessageId": originID,
	}, 1)
	// outbox 事件 payload 同源携带引用（MessageSent 单事件）。
	assertCollectionCount(t, "messages_outbox", bson.M{
		"aggregateId":              replyID,
		"payload.replyToMessageId": originID,
	}, 1)

	// 重放幂等：同 clientMsgId 返回同一 messageId，且不产生第二条消息。
	replayed := sendMessage(
		t,
		convID,
		`{"type":"text","content":"引用回复","clientMsgId":"reply-once","replyToMessageId":"`+originID+`"}`,
	)
	if replayed["messageId"] != replyID {
		t.Fatalf("replay must return the same message, got %v", replayed["messageId"])
	}
	assertCollectionCount(t, "messages", bson.M{"replyToMessageId": originID}, 1)
}

func TestReplyTargetRejectsMissingAndCrossConversationReference(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	first := createConversation(t, `{"type":"group","title":"reply first"}`)
	second := createConversation(t, `{"type":"group","title":"reply second"}`)
	firstID := first["id"].(string)
	secondID := second["id"].(string)
	foreign := sendMessage(t, firstID, `{"type":"text","content":"别的会话","clientMsgId":"reply-foreign"}`)
	foreignID := foreign["messageId"].(string)

	for name, payload := range map[string]string{
		"missing": `{"type":"text","content":"引用幽灵","clientMsgId":"reply-ghost","replyToMessageId":"msg-not-exists"}`,
		"cross":   `{"type":"text","content":"跨会话引用","clientMsgId":"reply-cross","replyToMessageId":"` + foreignID + `"}`,
	} {
		failure := doPost(
			t,
			"/chat/conversations/"+secondID+"/messages",
			payload,
			"user_test_001",
			http.StatusBadRequest,
		)
		if failure["code"] != "CHAT.USER.message_invalid" {
			t.Fatalf("%s reply target must map to canonical invalid: %#v", name, failure)
		}
	}
	// 失败不得写入任何成功事实。
	assertCollectionCount(t, "messages", bson.M{"conversationId": secondID}, 0)
}
