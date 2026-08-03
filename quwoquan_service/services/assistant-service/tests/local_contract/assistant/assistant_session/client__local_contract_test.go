package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/generated/serviceclients"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/chatclient"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

func TestClientReadsGroundingAndSendsAssistantMessage(t *testing.T) {
	var sentAuthorization string
	var sentBody struct {
		Type        string `json:"type"`
		Content     string `json:"content"`
		ClientMsgID string `json:"clientMsgId"`
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer assistant-policy-token" {
			http.Error(w, "missing service authorization", http.StatusUnauthorized)
			return
		}
		switch r.URL.Path {
		case serviceclients.ChatResolveAssistantDeliveryMembershipPath(
			"conv-1",
		):
			_ = json.NewEncoder(w).Encode(struct {
				CreatorMember   bool `json:"creatorMember"`
				AssistantMember bool `json:"assistantMember"`
			}{CreatorMember: true, AssistantMember: true})
			return
		case serviceclients.ChatListAssistantGroundingMessagesPath("conv-1"):
			if r.URL.Query().Get("beforeSeq") != "12" {
				t.Fatalf("beforeSeq=%s, want 12", r.URL.Query().Get("beforeSeq"))
			}
			_ = json.NewEncoder(w).Encode(struct {
				Items []map[string]any `json:"items"`
			}{Items: []map[string]any{{
				"id":                        "msg-1",
				"seq":                       11,
				"senderId":                  "user-a",
				"senderDisplayNameSnapshot": "小明",
				"type":                      "text",
				"content":                   "我们周末去哪里？",
				"mentions":                  []string{"assistant"},
				"timestamp":                 "2026-07-26T08:00:00Z",
			}},
			})
			return
		case serviceclients.ChatSendAssistantDeliveryMessagePath("conv-1"):
			sentAuthorization = r.Header.Get("Authorization")
			if err := json.NewDecoder(r.Body).Decode(&sentBody); err != nil {
				t.Fatalf("decode send body: %v", err)
			}
			w.WriteHeader(http.StatusCreated)
			return
		}
		assistantSessionClientWriteRuntimeNotFound(w, r, "unexpected "+r.Method+" "+r.URL.Path)
	}))
	defer server.Close()

	client, err := NewClient(
		server.Client(),
		server.URL,
		deliveryPolicyAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	current, err := client.ResolveAssistantDeliveryMembership(
		ctx,
		"conv-1",
		"user-a",
		"assistant",
	)
	if err != nil || !current {
		t.Fatalf("ResolveAssistantDeliveryMembership current=%t err=%v", current, err)
	}
	messages, err := client.ListMessages(
		ctx,
		"conv-1",
		"user-a",
		12,
		20,
	)
	if err != nil {
		t.Fatalf("ListMessages: %v", err)
	}
	if len(messages) != 1 || messages[0].Content != "我们周末去哪里？" {
		t.Fatalf("messages=%#v", messages)
	}
	err = client.SendMessage(ctx, ports.ChatGroundingSendMessageRequest{
		ChatConversationID: "conv-1",
		CreatorPersonaID:   "user-a",
		Type:               "text",
		Content:            "可以去川西。",
		ClientMsgID:        "assistant-turn-1",
	})
	if err != nil {
		t.Fatalf("SendMessage: %v", err)
	}
	if sentAuthorization != "Bearer assistant-policy-token" {
		t.Fatalf("sent authorization=%s", sentAuthorization)
	}
	if sentBody.Content != "可以去川西。" ||
		sentBody.ClientMsgID != "assistant-turn-1" {
		t.Fatalf("sent body=%#v", sentBody)
	}
}

func assistantSessionClientWriteRuntimeNotFound(w http.ResponseWriter, r *http.Request, debugMessage string) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "not_found"), "聊天资源不存在", debugMessage),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
