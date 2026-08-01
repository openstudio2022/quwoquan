// spec_ref: specs/feature-tree/runtime/runtime-assistant/spec.md#sit-001
package local_contract

import (
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

func TestSuggestedActionsCoverEightCanonicalPageTypes(
	t *testing.T,
) {
	service := orchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
	)
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
			reportSuggestedActionsPageContext(
				t,
				service,
				"user-suggested-actions",
				pageType,
				"object-"+pageType,
			)
			first, err := service.GetSuggestedActions(
				t.Context(),
				"user-suggested-actions",
				pageType,
				"object-"+pageType,
			)
			if err != nil {
				t.Fatal(err)
			}
			assertSuggestedActionPageContract(
				t,
				first.Items,
				pageType,
				actionID,
			)

			// 第二次必须走缓存后仍完整保留执行所需 payload，不能退化成
			// 只含 label 的展示数据。
			cached, err := service.GetSuggestedActions(
				t.Context(),
				"user-suggested-actions",
				pageType,
				"object-"+pageType,
			)
			if err != nil {
				t.Fatal(err)
			}
			assertSuggestedActionPageContract(
				t,
				cached.Items,
				pageType,
				actionID,
			)
		})
	}
}

func TestSuggestedActionsRejectUnknownPageType(
	t *testing.T,
) {
	service := orchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
	)
	reportSuggestedActionsPageContext(
		t,
		service,
		"user-suggested-actions",
		"discovery",
		"object-discovery",
	)
	if _, err := service.GetSuggestedActions(
		t.Context(),
		"user-suggested-actions",
		"untrusted-page-type",
		"object-unknown",
	); err == nil {
		t.Fatal("未知 pageType 不能回落为通用建议动作")
	}
}

func TestSuggestedActionsRequireMatchingFreshPageContext(
	t *testing.T,
) {
	service := orchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
	)
	if _, err := service.GetSuggestedActions(
		t.Context(),
		"user-suggested-actions",
		"discovery",
		"object-discovery",
	); err == nil {
		t.Fatal("缺少页面上下文时不得返回伪造的建议动作")
	}

	reportSuggestedActionsPageContext(
		t,
		service,
		"user-suggested-actions",
		"discovery",
		"object-discovery",
	)
	if _, err := service.GetSuggestedActions(
		t.Context(),
		"user-suggested-actions",
		"article",
		"object-discovery",
	); err == nil {
		t.Fatal("查询 pageType 与已核验页面上下文不匹配时必须拒绝")
	}
	if _, err := service.GetSuggestedActions(
		t.Context(),
		"user-suggested-actions",
		"discovery",
		"object-not-in-context",
	); err == nil {
		t.Fatal("查询 objectId 不在已核验页面上下文时必须拒绝")
	}
}

func reportSuggestedActionsPageContext(
	t *testing.T,
	service *orchestration.AssistantService,
	userID string,
	pageType string,
	objectID string,
) {
	t.Helper()
	if _, err := service.ReportPageContext(
		t.Context(),
		userID,
		assistant.PageContextInput{
			ContextSnapshot: assistant.AssistantContextSnapshot{
				CapturedAt: time.Now().UTC(),
				PageType:   pageType,
				PageObjects: []assistant.AssistantPageObjectRef{{
					ObjectTypeRef: "content.post",
					ObjectID:      objectID,
				}},
				ConsentMatrix: &assistant.AssistantContextConsent{
					CanReadCurrentPage: true,
				},
			},
		},
	); err != nil {
		t.Fatal(err)
	}
}

func assertSuggestedActionPageContract(
	t *testing.T,
	items []assistant.SuggestedAction,
	pageType string,
	expectedActionID string,
) {
	t.Helper()
	if len(items) < 3 {
		t.Fatalf("page=%s actions=%+v，必须包含基础动作与两个页面专属动作", pageType, items)
	}
	found := false
	for _, item := range items {
		if item.ActionID == expectedActionID {
			found = true
			if item.Label == "" || item.Type == "" {
				t.Fatalf("页面专属动作缺少可执行字段: %+v", item)
			}
			if item.Payload["pageType"] != pageType ||
				item.Payload["objectId"] != "object-"+pageType {
				t.Fatalf("页面专属动作 payload 漂移: %+v", item)
			}
		}
	}
	if !found {
		t.Fatalf("page=%s 缺少专属动作 %s: %+v", pageType, expectedActionID, items)
	}
}
