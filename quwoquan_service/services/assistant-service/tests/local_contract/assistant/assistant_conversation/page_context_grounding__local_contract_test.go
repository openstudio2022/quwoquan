// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
package local_contract

import (
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

func TestReportedPageContextEntersTheNextTurnPrompt(t *testing.T) {
	cache := rtredis.NewMemoryClient()
	service := orchestration.NewAssistantService(
		nil,
		cache,
		orchestration.WithConversationRunStore(
			persistence.NewMemoryConversationRunStore(),
		),
		testFrozenPolicyOption(),
	)
	ctx := t.Context()
	_, err := service.ReportPageContext(
		ctx,
		"persona-page-context",
		assistant.PageContextInput{
			ContextSnapshot: assistant.AssistantContextSnapshot{
				CapturedAt: time.Now().UTC(),
				PageType:   "article",
				PageObjects: []assistant.AssistantPageObjectRef{{
					ObjectTypeRef: "content.post",
					ObjectID:      "post-1",
				}},
				UserActions: []assistant.AssistantPageUserAction{{
					Action:        "open_assistant_entry",
					ObjectTypeRef: "content.post",
					ObjectID:      "post-1",
				}},
				ConsentMatrix: &assistant.AssistantContextConsent{
					CanReadCurrentPage: true,
				},
			},
		},
	)
	if err != nil {
		t.Fatalf("ReportPageContext() error = %v", err)
	}
	conversation, err := service.CreateConversation(
		ctx,
		"persona-page-context",
		assistant.CreateConversationInput{
			ClientRequestID: "page-context-conversation",
		},
	)
	if err != nil {
		t.Fatalf("CreateConversation() error = %v", err)
	}
	turn, err := service.CreateTurn(
		ctx,
		"persona-page-context",
		conversation.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "结合当前页面回答"},
			ClientRequestID: "page-context-turn",
			RequestContext:  testRunRequestContext("persona-page-context"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn() error = %v", err)
	}
	if turn.PageContext == nil ||
		turn.PageContext.PageType != "article" ||
		len(turn.PageContext.PageObjects) != 1 {
		t.Fatalf("turn page context = %#v", turn.PageContext)
	}
	prompt := orchestration.FormatPageContextForPrompt(turn.PageContext)
	if !strings.Contains(prompt, "content.post:post-1") ||
		!strings.Contains(prompt, "open_assistant_entry") {
		t.Fatalf("page context prompt = %q", prompt)
	}
}

func TestReportPageContextFailsClosedForUnknownObjectsAndMissingCache(
	t *testing.T,
) {
	input := assistant.PageContextInput{
		ContextSnapshot: assistant.AssistantContextSnapshot{
			CapturedAt: time.Now().UTC(),
			PageType:   "article",
			PageObjects: []assistant.AssistantPageObjectRef{{
				ObjectTypeRef: "unknown.object",
				ObjectID:      "object-1",
			}},
			ConsentMatrix: &assistant.AssistantContextConsent{
				CanReadCurrentPage: true,
			},
		},
	}
	service := orchestration.NewAssistantService(nil, rtredis.NewMemoryClient())
	_, err := service.ReportPageContext(
		t.Context(),
		"persona-page-context",
		input,
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("unknown page object error = %v", err)
	}

	input.ContextSnapshot.PageObjects = nil
	input.ContextSnapshot.IntersectionEvidenceRefs = []assistant.AssistantIntersectionEvidenceRef{{
		IntersectionID: "intersection-page-context",
		EvidenceID:     "evidence-page-context",
		SourceRef:      "same_school",
		ObjectTypeRef:  "content.post",
		ObjectID:       "post-page-context",
	}}
	_, err = service.ReportPageContext(
		t.Context(),
		"persona-page-context",
		input,
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("page context intersection evidence error = %v", err)
	}

	input.ContextSnapshot.IntersectionEvidenceRefs = nil
	input.ContextSnapshot.UserActions = make(
		[]assistant.AssistantPageUserAction,
		21,
	)
	for index := range input.ContextSnapshot.UserActions {
		input.ContextSnapshot.UserActions[index].Action = "open_assistant_entry"
	}
	_, err = service.ReportPageContext(
		t.Context(),
		"persona-page-context",
		input,
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("oversized page context actions error = %v", err)
	}

	input.ContextSnapshot.UserActions = nil
	service = orchestration.NewAssistantService(nil, nil)
	_, err = service.ReportPageContext(
		t.Context(),
		"persona-page-context",
		input,
	)
	if err == nil ||
		!strings.Contains(err.Error(), "ASSISTANT.SYSTEM.page_context_unavailable") {
		t.Fatalf("missing page context cache error = %v", err)
	}
}

func TestMissingOrStalePageContextCannotEnterPrompt(t *testing.T) {
	cache := rtredis.NewMemoryClient()
	service := orchestration.NewAssistantService(
		nil,
		cache,
		orchestration.WithConversationRunStore(
			persistence.NewMemoryConversationRunStore(),
		),
		testFrozenPolicyOption(),
	)
	ctx := t.Context()
	conversation, err := service.CreateConversation(
		ctx,
		"persona-without-page-context",
		assistant.CreateConversationInput{
			ClientRequestID: "missing-page-context-conversation",
		},
	)
	if err != nil {
		t.Fatalf("CreateConversation() error = %v", err)
	}
	turn, err := service.CreateTurn(
		ctx,
		"persona-without-page-context",
		conversation.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "回答问题"},
			ClientRequestID: "missing-page-context-turn",
			RequestContext: testRunRequestContext(
				"persona-without-page-context",
			),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn() error = %v", err)
	}
	if turn.PageContext != nil || orchestration.FormatPageContextForPrompt(turn.PageContext) != "" {
		t.Fatalf("missing page context entered prompt: %#v", turn.PageContext)
	}

	_, err = service.ReportPageContext(
		ctx,
		"persona-with-stale-page-context",
		assistant.PageContextInput{
			ContextSnapshot: assistant.AssistantContextSnapshot{
				CapturedAt: time.Now().UTC().Add(-6 * time.Minute),
				PageType:   "article",
				ConsentMatrix: &assistant.AssistantContextConsent{
					CanReadCurrentPage: true,
				},
			},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("stale page context error = %v", err)
	}

	_, err = service.ReportPageContext(
		ctx,
		"persona-with-unknown-page-context",
		assistant.PageContextInput{
			ContextSnapshot: assistant.AssistantContextSnapshot{
				CapturedAt: time.Now().UTC(),
				PageType:   "content_detail",
				ConsentMatrix: &assistant.AssistantContextConsent{
					CanReadCurrentPage: true,
				},
			},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("unknown page context error = %v", err)
	}
}
