// spec_ref: specs/feature-tree/runtime/runtime-assistant/spec.md#sit-001
package api_integration

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

func TestSuggestedActionsPageMatrixCrossesHTTPAndRedis(
	t *testing.T,
) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	cases := map[string]string{
		"discovery": "assistant.find_similar_content",
		"circles":   "assistant.summarize_circle_discussion",
		"article":   "assistant.summarize_article",
		"profile":   "assistant.explain_profile",
		"chat":      "assistant.summarize_conversation",
		"create":    "assistant.improve_creation_draft",
		"search":    "assistant.refine_search_query",
		"home":      "assistant.suggest_next_step",
	}
	for pageType, actionID := range cases {
		t.Run(pageType, func(t *testing.T) {
			reportSuggestedActionsHTTPPageContext(
				t,
				handler,
				"suggested-actions-owner",
				pageType,
				"object-"+pageType,
			)
			path := "/assistant/suggested-actions?pageType=" + pageType +
				"&objectId=object-" + pageType
			first := assistantAPIRequest(
				t,
				handler,
				http.MethodGet,
				path,
				"suggested-actions-owner",
				nil,
			)
			if first.Code != http.StatusOK {
				t.Fatalf(
					"first suggested-actions status=%d body=%s",
					first.Code,
					first.Body.String(),
				)
			}
			assertSuggestedActionsAPIResponse(
				t,
				first.Body.Bytes(),
				pageType,
				actionID,
			)

			cached := assistantAPIRequest(
				t,
				handler,
				http.MethodGet,
				path,
				"suggested-actions-owner",
				nil,
			)
			if cached.Code != http.StatusOK {
				t.Fatalf(
					"cached suggested-actions status=%d body=%s",
					cached.Code,
					cached.Body.String(),
				)
			}
			assertSuggestedActionsAPIResponse(
				t,
				cached.Body.Bytes(),
				pageType,
				actionID,
			)
		})
	}
}

func TestSuggestedActionsAPIRequiresMatchingPageContext(
	t *testing.T,
) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	missing := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/suggested-actions?pageType=discovery&objectId=object-discovery",
		"suggested-actions-owner",
		nil,
	)
	if missing.Code != http.StatusBadRequest {
		t.Fatalf(
			"missing page context status=%d body=%s",
			missing.Code,
			missing.Body.String(),
		)
	}
	if !strings.Contains(
		missing.Body.String(),
		"ASSISTANT.USER.run_invalid_argument",
	) {
		t.Fatalf(
			"missing page context must return canonical run_invalid_argument: %s",
			missing.Body.String(),
		)
	}
	reportSuggestedActionsHTTPPageContext(
		t,
		handler,
		"suggested-actions-owner",
		"discovery",
		"object-discovery",
	)
	mismatch := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/suggested-actions?pageType=article&objectId=object-discovery",
		"suggested-actions-owner",
		nil,
	)
	if mismatch.Code != http.StatusBadRequest {
		t.Fatalf(
			"mismatched page context status=%d body=%s",
			mismatch.Code,
			mismatch.Body.String(),
		)
	}
	if !strings.Contains(
		mismatch.Body.String(),
		"ASSISTANT.USER.run_invalid_argument",
	) {
		t.Fatalf(
			"mismatched page context must return canonical run_invalid_argument: %s",
			mismatch.Body.String(),
		)
	}
}

func TestSuggestedActionsAPIRejectsUnknownPageType(
	t *testing.T,
) {
	resetIntegrationState(t)
	handler := assistanthttp.NewHandler(newIntegrationAssistantService()).Routes()
	response := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/suggested-actions?pageType=untrusted-page-type",
		"suggested-actions-owner",
		nil,
	)
	if response.Code != http.StatusBadRequest {
		t.Fatalf(
			"unknown pageType status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
	if !strings.Contains(
		response.Body.String(),
		"ASSISTANT.USER.run_invalid_argument",
	) {
		t.Fatalf(
			"unknown page type must return canonical run_invalid_argument: %s",
			response.Body.String(),
		)
	}
}

func reportSuggestedActionsHTTPPageContext(
	t *testing.T,
	handler http.Handler,
	userID string,
	pageType string,
	objectID string,
) {
	t.Helper()
	response := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/page-context",
		userID,
		map[string]any{
			"contextSnapshot": map[string]any{
				"capturedAt": time.Now().UTC().Format(time.RFC3339Nano),
				"pageType":   pageType,
				"pageObjects": []map[string]any{{
					"objectTypeRef": "content.post",
					"objectId":      objectID,
				}},
				"consentMatrix": map[string]any{
					"canReadCurrentPage": true,
				},
			},
		},
	)
	if response.Code != http.StatusOK {
		t.Fatalf(
			"report page context status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
}

func assertSuggestedActionsAPIResponse(
	t *testing.T,
	body []byte,
	pageType string,
	expectedActionID string,
) {
	t.Helper()
	var view assistant.SuggestedActionListView
	if err := json.Unmarshal(body, &view); err != nil {
		t.Fatalf("decode suggested actions: %v", err)
	}
	if len(view.Items) < 3 {
		t.Fatalf("page=%s actions=%+v", pageType, view.Items)
	}
	for _, item := range view.Items {
		if item.ActionID != expectedActionID {
			continue
		}
		if item.Label == "" || item.Type == "" {
			t.Fatalf("page action is not actionable: %+v", item)
		}
		if item.Payload["pageType"] != pageType ||
			item.Payload["objectId"] != "object-"+pageType {
			t.Fatalf("page action payload=%+v", item.Payload)
		}
		return
	}
	t.Fatalf("page=%s missing action=%s: %+v", pageType, expectedActionID, view.Items)
}
