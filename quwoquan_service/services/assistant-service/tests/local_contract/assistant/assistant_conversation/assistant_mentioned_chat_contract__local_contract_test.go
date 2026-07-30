package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/generated/serviceclients"
	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

func TestAssistantMentionedConsumerGroundsAndRepliesThroughChatHTTP(t *testing.T) {
	ctx := context.Background()
	var sentAuthorization string
	var sentBody struct {
		Type        string `json:"type"`
		Content     string `json:"content"`
		ClientMsgID string `json:"clientMsgId"`
	}

	chatHTTP := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer assistant-policy-token" {
			http.Error(w, "missing service authorization", http.StatusUnauthorized)
			return
		}
		switch r.URL.Path {
		case serviceclients.ChatResolveAssistantDeliveryMembershipPath(
			"conv-e2e",
		):
			_ = json.NewEncoder(w).Encode(struct {
				CreatorMember        bool `json:"creatorMember"`
				AssistantSkillMember bool `json:"assistantSkillMember"`
			}{CreatorMember: true, AssistantSkillMember: true})
			return
		case serviceclients.ChatListAssistantGroundingMessagesPath(
			"conv-e2e",
		):
			if r.URL.Query().Get("beforeSeq") != "12" {
				t.Fatalf("beforeSeq=%s, want 12", r.URL.Query().Get("beforeSeq"))
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"items": []map[string]any{
				{
					"id":                        "msg-10",
					"messageId":                 "msg-10",
					"seq":                       10,
					"senderId":                  "user-a",
					"senderDisplayNameSnapshot": "小明",
					"type":                      "text",
					"content":                   "周末去川西怎么样？",
				},
				{
					"id":                        "msg-11",
					"messageId":                 "msg-11",
					"seq":                       11,
					"senderId":                  "user-b",
					"senderDisplayNameSnapshot": "小红",
					"type":                      "text",
					"content":                   "我想知道自驾路线和住宿。",
				},
			},
			})
			return
		case serviceclients.ChatSendAssistantDeliveryMessagePath(
			"conv-e2e",
		):
			sentAuthorization = r.Header.Get("Authorization")
			if err := json.NewDecoder(r.Body).Decode(&sentBody); err != nil {
				t.Fatalf("decode send body: %v", err)
			}
			w.WriteHeader(http.StatusCreated)
			return
		}
		writeRuntimeNotFound(w, r, "unexpected "+r.Method+" "+r.URL.Path)
	}))
	defer chatHTTP.Close()

	redis := rtredis.NewMemoryClient()
	chatGrounding, err := chatclient.NewClient(
		chatHTTP.Client(),
		chatHTTP.URL,
		deliveryPolicyAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	service := orchestration.NewAssistantService(
		persistence.NewMemoryConsentStore(),
		redis,
		orchestration.WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		orchestration.WithAgentLoop(orchestration.NewAgentLoop(
			proactiveSkillRuntime{},
			orchestration.ReactRuntime{Model: proactiveFinalModel{}},
			nil,
		)),
		orchestration.WithChatGroundingClient(chatGrounding),
		testFrozenPolicyOption(),
	)
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"assistant-service-local-contract",
		runtimemessaging.RedisMessageTransportFixture,
		redis,
		redis,
	)
	if err != nil {
		t.Fatalf("NewRedisMessageTransportForRoot() error = %v", err)
	}
	consumer := messaging.NewAssistantMentionedConsumerWithTransport(
		transport,
		service,
		"e2e-worker",
		nil,
	)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := redis.XAdd(ctx, messaging.AssistantMentionedStream, map[string]string{
		"conversationId":    "conv-e2e",
		"messageId":         "msg-12",
		"seq":               "12",
		"senderId":          "user-a",
		"content":           "@小趣 总结一下这段路线讨论",
		"assistantMemberId": "assistant",
		"assistantSkillId":  "general",
	}); err != nil {
		t.Fatalf("XAdd: %v", err)
	}

	processed, err := consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("ProcessOnce: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d, want 1", processed)
	}
	if sentAuthorization != "Bearer assistant-policy-token" {
		t.Fatalf("sentAuthorization=%s", sentAuthorization)
	}
	if sentBody.Type != "text" {
		t.Fatalf("sent body type=%v", sentBody.Type)
	}
	if sentBody.Content == "" {
		t.Fatalf("assistant reply content empty: %#v", sentBody)
	}
	clientMsgID := sentBody.ClientMsgID
	if len(clientMsgID) < len("assistant-") || clientMsgID[:len("assistant-")] != "assistant-" {
		t.Fatalf("clientMsgId=%q, want assistant-*", clientMsgID)
	}
	pending, err := redis.XReadGroup(ctx, messaging.AssistantMentionedConsumerGroup, "e2e-worker", map[string]string{messaging.AssistantMentionedStream: "0"}, 10, 0)
	if err != nil {
		t.Fatalf("read pending: %v", err)
	}
	if len(pending) != 0 {
		t.Fatalf("pending=%d, want 0", len(pending))
	}
}

func writeRuntimeNotFound(w http.ResponseWriter, r *http.Request, debugMessage string) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "not_found"), "聊天资源不存在", debugMessage),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
