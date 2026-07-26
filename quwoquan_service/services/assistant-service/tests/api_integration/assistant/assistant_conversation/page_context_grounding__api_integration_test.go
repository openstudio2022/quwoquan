// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

func TestPageContextCrossesHTTPRedisAndTurnBoundary(t *testing.T) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	userID := "page-context-owner"
	now := time.Now().UTC()

	report := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/page-context",
		userID,
		map[string]any{
			"contextSnapshot": map[string]any{
				"capturedAt": now.Format(time.RFC3339Nano),
				"pageType":   "content_detail",
				"pageObjects": []map[string]any{{
					"objectTypeRef": "content.post",
					"objectId":      "post-grounding-api",
				}},
				"userActions": []map[string]any{{
					"action":        "open_assistant_entry",
					"objectTypeRef": "content.post",
					"objectId":      "post-grounding-api",
					"occurredAt":    now.Format(time.RFC3339Nano),
				}},
				"consentMatrix": map[string]any{
					"canReadCurrentPage": true,
				},
			},
		},
	)
	if report.Code != http.StatusOK {
		t.Fatalf("report page context status=%d body=%s", report.Code, report.Body.String())
	}
	var ack assistant.PageContextAck
	if err := json.Unmarshal(report.Body.Bytes(), &ack); err != nil {
		t.Fatalf("decode page context ack: %v", err)
	}
	if !ack.Accepted || ack.ContextKey != "page_ctx:"+userID || ack.ExpiresAt == nil {
		t.Fatalf("page context ack=%+v", ack)
	}
	legacy := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/page-context",
		userID,
		map[string]any{
			"pageType":        "content_detail",
			"businessObjects": []map[string]any{},
		},
	)
	if legacy.Code != http.StatusBadRequest {
		t.Fatalf(
			"legacy page context status=%d body=%s",
			legacy.Code,
			legacy.Body.String(),
		)
	}

	ctx := context.Background()
	stored, err := integrationRedisClient.Get(ctx, ack.ContextKey)
	if err != nil {
		t.Fatalf("read stored page context: %v", err)
	}
	var storedSnapshot assistant.AssistantContextSnapshot
	if err := json.Unmarshal([]byte(stored), &storedSnapshot); err != nil {
		t.Fatalf("decode stored page context: %v", err)
	}
	if storedSnapshot.PageType != "content_detail" ||
		len(storedSnapshot.PageObjects) != 1 ||
		storedSnapshot.PageObjects[0].ObjectID != "post-grounding-api" {
		t.Fatalf("stored page context=%+v", storedSnapshot)
	}
	ttl, err := integrationRedisServer.TTL(ctx, 1, ack.ContextKey)
	if err != nil {
		t.Fatalf("read page context TTL: %v", err)
	}
	if ttl <= 4*time.Minute || ttl > 5*time.Minute {
		t.Fatalf("page context TTL=%s, want (4m, 5m]", ttl)
	}

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations",
		userID,
		map[string]any{
			"summary": "页面上下文对话", "clientRequestId": "page-context-conversation",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create conversation status=%d body=%s", create.Code, create.Body.String())
	}
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}

	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		userID,
		map[string]any{
			"input":           map[string]any{"text": "介绍当前内容"},
			"clientRequestId": "page-context-run-api",
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", start.Code, start.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(start.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode run envelope: %v", err)
	}
	if _, leaked := envelope["pageContext"]; leaked {
		t.Fatalf("run envelope leaked internal page context: %#v", envelope)
	}
	turnID, _ := envelope["turnId"].(string)
	turn, found, err := integrationConversationRunStore.GetTurn(t.Context(), turnID)
	if err != nil || !found {
		t.Fatalf("load persisted turn found=%v err=%v", found, err)
	}
	if turn.PageContext == nil ||
		turn.PageContext.PageType != "content_detail" ||
		len(turn.PageContext.UserActions) != 1 ||
		turn.PageContext.UserActions[0].Action != "open_assistant_entry" {
		t.Fatalf("turn page context=%+v", turn.PageContext)
	}
}
