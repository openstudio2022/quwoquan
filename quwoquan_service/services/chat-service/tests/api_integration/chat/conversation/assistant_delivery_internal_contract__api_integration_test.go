// spec_ref: specs/feature-tree/runtime/runtime-assistant/proactive-subscription-delivery/spec.md#gwt-001
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"quwoquan_service/generated/serviceclients"
)

type assistantDeliveryMembershipResponse struct {
	CreatorMember        bool `json:"creatorMember"`
	AssistantSkillMember bool `json:"assistantSkillMember"`
}

type assistantDeliveryMessageResponse struct {
	MessageID string `json:"messageId"`
	Seq       int64  `json:"seq"`
	Timestamp string `json:"timestamp"`
}

func TestAssistantDeliveryInternalContractUsesExactMembershipAndIdempotency(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	conversation := createConversation(
		t,
		`{"type":"group","title":"assistant delivery"}`,
	)
	conversationID := conversation["id"].(string)
	doPost(
		t,
		"/chat/conversations/"+conversationID+"/assistant",
		`{"skillId":"general"}`,
		"user_test_001",
		http.StatusOK,
	)
	sendMessage(
		t,
		conversationID,
		`{"type":"text","content":"请总结今天的行程",`+
			`"clientMsgId":"assistant-grounding-source-1"}`,
	)

	query := url.Values{
		"creatorPersonaId": {"user_test_001"},
		"assistantSkillId": {"general"},
	}
	membershipPath :=
		serviceclients.ChatResolveAssistantDeliveryMembershipPath(
			conversationID,
		) + "?" + query.Encode()
	var membership assistantDeliveryMembershipResponse
	internalAssistantRequest(
		t,
		http.MethodGet,
		membershipPath,
		"",
		http.StatusOK,
		&membership,
	)
	if !membership.CreatorMember || !membership.AssistantSkillMember {
		t.Fatalf("有效成员授权切片漂移: %+v", membership)
	}

	groundingPath :=
		serviceclients.ChatListAssistantGroundingMessagesPath(
			conversationID,
		) + "?" + query.Encode()
	var grounding struct {
		Items []struct {
			Content string `json:"content"`
		} `json:"items"`
	}
	internalAssistantRequest(
		t,
		http.MethodGet,
		groundingPath,
		"",
		http.StatusOK,
		&grounding,
	)
	if len(grounding.Items) == 0 ||
		grounding.Items[0].Content == "" {
		t.Fatalf("助手 grounding 消息为空: %+v", grounding)
	}

	sendPath := serviceclients.ChatSendAssistantDeliveryMessagePath(
		conversationID,
	) + "?" + query.Encode()
	const body = `{"type":"text","content":"这是小趣的总结",` +
		`"clientMsgId":"assistant-delivery-stable-1"}`
	var first assistantDeliveryMessageResponse
	internalAssistantRequest(
		t,
		http.MethodPost,
		sendPath,
		body,
		http.StatusCreated,
		&first,
	)
	var replay assistantDeliveryMessageResponse
	internalAssistantRequest(
		t,
		http.MethodPost,
		sendPath,
		body,
		http.StatusCreated,
		&replay,
	)
	if first.MessageID == "" ||
		replay.MessageID != first.MessageID ||
		replay.Seq != first.Seq {
		t.Fatalf("助手投递幂等坐标漂移: first=%+v replay=%+v", first, replay)
	}

	status, _ := doDelete(
		t,
		"/chat/conversations/"+conversationID+"/assistant",
		"user_test_001",
	)
	if status != http.StatusOK {
		t.Fatalf("移除助手失败: status=%d", status)
	}
	membership = assistantDeliveryMembershipResponse{}
	internalAssistantRequest(
		t,
		http.MethodGet,
		membershipPath,
		"",
		http.StatusOK,
		&membership,
	)
	if membership.AssistantSkillMember {
		t.Fatalf("已移除助手仍被授权: %+v", membership)
	}
	internalAssistantRequest(
		t,
		http.MethodPost,
		sendPath,
		`{"type":"text","content":"不得发送",`+
			`"clientMsgId":"assistant-delivery-denied-1"}`,
		http.StatusForbidden,
		nil,
	)
}

func internalAssistantRequest(
	t *testing.T,
	method string,
	path string,
	body string,
	wantStatus int,
	response any,
) {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	if body != "" {
		request.Header.Set("Content-Type", "application/json")
	}
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != wantStatus {
		t.Fatalf(
			"%s %s status=%d want=%d body=%s",
			method,
			path,
			recorder.Code,
			wantStatus,
			recorder.Body.String(),
		)
	}
	if response != nil {
		if err := json.Unmarshal(recorder.Body.Bytes(), response); err != nil {
			t.Fatalf("decode %s %s response: %v", method, path, err)
		}
	}
}
