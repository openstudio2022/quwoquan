package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/infrastructure/messaging"
)

func TestAssistantMentionedConsumerGroundsAndRepliesThroughChatHTTP(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	var sentActor string
	var sentBody map[string]any

	chatHTTP := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/chat/conversations/conv-e2e/messages":
			if r.Method == http.MethodGet {
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
				}})
				return
			}
			if r.Method == http.MethodPost {
				sentActor = r.Header.Get("X-Client-Sub-Account-Id")
				if err := json.NewDecoder(r.Body).Decode(&sentBody); err != nil {
					t.Fatalf("decode send body: %v", err)
				}
				w.WriteHeader(http.StatusCreated)
				_ = json.NewEncoder(w).Encode(map[string]any{"messageId": "assistant-reply-1", "seq": 13})
				return
			}
		case "/v1/chat/conversations/conv-e2e/members":
			_ = json.NewEncoder(w).Encode(map[string]any{"items": []map[string]any{
				{
					"userId":      "user-a",
					"displayName": "小明",
					"memberType":  "user",
				},
				{
					"userId":           "assistant",
					"displayName":      "小趣",
					"memberType":       "assistant",
					"assistantSkillId": "general",
				},
			}})
			return
		}
		writeRuntimeNotFound(w, r, "unexpected "+r.Method+" "+r.URL.Path)
	}))
	defer chatHTTP.Close()

	service := newIntegrationAssistantService(
		application.WithChatGroundingClient(chatclient.NewClient(chatHTTP.Client(), chatHTTP.URL)),
	)
	consumer := messaging.NewAssistantMentionedConsumer(
		integrationRedisClient,
		service,
		"e2e-worker",
		nil,
	)
	if err := consumer.EnsureGroup(ctx); err != nil {
		t.Fatalf("EnsureGroup: %v", err)
	}
	if _, err := integrationRedisClient.XAdd(ctx, messaging.AssistantMentionedStream, map[string]string{
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
	if sentActor != "assistant" {
		t.Fatalf("sentActor=%s, want assistant", sentActor)
	}
	if sentBody["type"] != "text" {
		t.Fatalf("sent body type=%v", sentBody["type"])
	}
	content, _ := sentBody["content"].(string)
	if content == "" {
		t.Fatalf("assistant reply content empty: %#v", sentBody)
	}
	clientMsgID, _ := sentBody["clientMsgId"].(string)
	if len(clientMsgID) < len("assistant-") || clientMsgID[:len("assistant-")] != "assistant-" {
		t.Fatalf("clientMsgId=%q, want assistant-*", clientMsgID)
	}
	pending, err := integrationRedisClient.XReadGroup(
		ctx,
		messaging.AssistantMentionedConsumerGroup,
		"e2e-worker",
		map[string]string{messaging.AssistantMentionedStream: "0"},
		10,
		0,
	)
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
