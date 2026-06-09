package chatclient

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/assistant-service/internal/application"
)

func TestClientReadsGroundingAndSendsAssistantMessage(t *testing.T) {
	var sentActor string
	var sentBody map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/chat/conversations/conv-1/messages":
			if r.Method == http.MethodGet {
				if r.URL.Query().Get("beforeSeq") != "12" {
					t.Fatalf("beforeSeq=%s, want 12", r.URL.Query().Get("beforeSeq"))
				}
				_ = json.NewEncoder(w).Encode(map[string]any{"items": []map[string]any{{
					"id":                        "msg-1",
					"seq":                       11,
					"senderId":                  "user-a",
					"senderDisplayNameSnapshot": "小明",
					"type":                      "text",
					"content":                   "我们周末去哪里？",
					"mentions":                  []string{"assistant"},
				}}})
				return
			}
			if r.Method == http.MethodPost {
				sentActor = r.Header.Get("X-Client-Sub-Account-Id")
				if err := json.NewDecoder(r.Body).Decode(&sentBody); err != nil {
					t.Fatalf("decode send body: %v", err)
				}
				w.WriteHeader(http.StatusCreated)
				_ = json.NewEncoder(w).Encode(map[string]any{"messageId": "reply-1", "seq": 12})
				return
			}
		case "/v1/chat/conversations/conv-1/members":
			_ = json.NewEncoder(w).Encode(map[string]any{"items": []map[string]any{{
				"userId": "assistant", "displayName": "小趣", "memberType": "assistant", "assistantSkillId": "general",
			}}})
			return
		}
		http.NotFound(w, r)
	}))
	defer server.Close()

	client := NewClient(server.Client(), server.URL)
	ctx := context.Background()
	messages, err := client.ListMessages(ctx, "conv-1", 12, 20)
	if err != nil {
		t.Fatalf("ListMessages: %v", err)
	}
	if len(messages) != 1 || messages[0].Content != "我们周末去哪里？" {
		t.Fatalf("messages=%#v", messages)
	}
	members, err := client.ListMembers(ctx, "conv-1", 100)
	if err != nil {
		t.Fatalf("ListMembers: %v", err)
	}
	if len(members) != 1 || members[0].MemberType != "assistant" {
		t.Fatalf("members=%#v", members)
	}
	err = client.SendMessage(ctx, application.ChatGroundingSendMessageRequest{
		ConversationID: "conv-1",
		SenderID:       "assistant",
		Type:           "text",
		Content:        "可以去川西。",
		ClientMsgID:    "assistant-turn-1",
	})
	if err != nil {
		t.Fatalf("SendMessage: %v", err)
	}
	if sentActor != "assistant" {
		t.Fatalf("sent actor=%s, want assistant", sentActor)
	}
	if sentBody["content"] != "可以去川西。" {
		t.Fatalf("sent body=%#v", sentBody)
	}
}
