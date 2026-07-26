// spec_ref: specs/feature-tree/runtime/runtime-assistant/assistant-mentioned-consumer/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/generated/serviceclients"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/messaging"
)

func TestAssistantMentionedConsumerGroundsAndRepliesThroughChatHTTP(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	var sentAuthorization string
	var sentBody struct {
		Type        string `json:"type"`
		Content     string `json:"content"`
		ClientMsgID string `json:"clientMsgId"`
	}
	assistantPresent := true
	messageWindowReads := 0
	messageWrites := 0

	chatHTTP := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer chat-token" {
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
			}{
				CreatorMember:        true,
				AssistantSkillMember: assistantPresent,
			})
			return
		case serviceclients.ChatListAssistantGroundingMessagesPath(
			"conv-e2e",
		):
			messageWindowReads++
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
			messageWrites++
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

	chatGrounding, err := chatclient.NewClient(
		chatHTTP.Client(),
		chatHTTP.URL,
		integrationServiceCredentials("chat-token"),
	)
	if err != nil {
		t.Fatal(err)
	}
	service := newIntegrationAssistantService(
		application.WithAgentLoop(application.NewAgentLoop(
			integrationChatMentionSkillRuntime{},
			application.ReactRuntime{
				Model: application.DeterministicModelProvider{},
			},
			nil,
		)),
		application.WithChatGroundingClient(chatGrounding),
	)
	consumer := messaging.NewAssistantMentionedConsumerWithTransport(
		newIntegrationMessageTransport(),
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
	if sentAuthorization != "Bearer chat-token" {
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

	assistantPresent = false
	if _, err := integrationRedisClient.XAdd(ctx, messaging.AssistantMentionedStream, map[string]string{
		"conversationId":    "conv-e2e",
		"messageId":         "msg-13",
		"seq":               "13",
		"senderId":          "user-a",
		"content":           "@小趣 这条不应回复",
		"assistantMemberId": "assistant",
		"assistantSkillId":  "general",
	}); err != nil {
		t.Fatalf("XAdd removed-member event: %v", err)
	}
	processed, err = consumer.ProcessOnce(ctx)
	if err != nil {
		t.Fatalf("ProcessOnce removed-member event: %v", err)
	}
	if processed != 1 {
		t.Fatalf("removed-member processed=%d, want acked 1", processed)
	}
	if messageWindowReads != 1 || messageWrites != 1 {
		t.Fatalf(
			"removed-member event crossed reply boundary: reads=%d writes=%d",
			messageWindowReads,
			messageWrites,
		)
	}
}

type integrationChatMentionSkillRuntime struct{}

func (integrationChatMentionSkillRuntime) SelectSkill(
	context.Context,
	assistant.AssistantTurn,
) (application.SkillSelection, error) {
	return application.SkillSelection{
		SkillID:  "general",
		DomainID: "assistant",
	}, nil
}

func writeRuntimeNotFound(w http.ResponseWriter, r *http.Request, debugMessage string) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "not_found"), "聊天资源不存在", debugMessage),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
