// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	pagehttp "quwoquan_service/services/assistant-service/internal/assistant/page_context/adapters/inbound/http"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagemodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
	pagepersistence "quwoquan_service/services/assistant-service/internal/assistant/page_context/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/tests/support/assistantingress"
)

func TestPageContextCrossesObjectHTTPRedisAndTurnBoundary(t *testing.T) {
	resetIntegrationState(t)
	pages := pageapplication.NewFacade(
		pagepersistence.NewRedisStore(integrationRedisClient),
		func() time.Time { return time.Now().UTC() },
	)
	mux := http.NewServeMux()
	pagehttp.NewHandler(pages).RegisterRoutes(mux)

	accountID := "page-context-owner"
	now := time.Now().UTC()
	report := assistantAPIRequest(t, mux, http.MethodPost, "/assistant/page-context", accountID, map[string]any{
		"contextSnapshot": map[string]any{
			"capturedAt": now.Format(time.RFC3339Nano),
			"pageType":   "article",
			"pageObjects": []map[string]any{{
				"objectTypeRef": "content.Post",
				"objectId":      "post-grounding-api",
			}},
			"userActions": []map[string]any{{
				"actionType":    "open_assistant_entry",
				"objectTypeRef": "content.Post",
				"objectId":      "post-grounding-api",
			}},
			"consentGranted": true,
		},
	})
	if report.Code != http.StatusOK {
		t.Fatalf("report status=%d body=%s", report.Code, report.Body.String())
	}
	var receipt pagemodel.Receipt
	if err := json.Unmarshal(report.Body.Bytes(), &receipt); err != nil {
		t.Fatal(err)
	}
	if !receipt.Accepted || receipt.ContextKey != pagemodel.StorageKey(accountID) {
		t.Fatalf("receipt=%+v", receipt)
	}
	ttl, err := integrationRedisServer.TTL(t.Context(), 1, receipt.ContextKey)
	if err != nil || ttl <= 4*time.Minute || ttl > 5*time.Minute {
		t.Fatalf("ttl=%s err=%v", ttl, err)
	}
	current, err := pages.Current(t.Context(), accountID)
	if err != nil || current == nil || current.Snapshot.PageObjects[0].ObjectID != "post-grounding-api" {
		t.Fatalf("current=%+v err=%v", current, err)
	}

	service := newIntegrationAssistantService()
	runContext := runapplication.NewContextResolver(
		runapplication.CurrentPageContextReaderFunc(func(
			ctx context.Context,
			owner string,
		) (map[string]any, bool, error) {
			current, readErr := pages.Current(ctx, owner)
			if readErr != nil || current == nil {
				return nil, false, readErr
			}
			return map[string]any{
				"capturedAt": current.CapturedAt,
				"pageType":   current.Snapshot.PageType,
				"pageObjects": []any{map[string]any{
					"objectTypeRef": current.Snapshot.PageObjects[0].ObjectTypeRef,
					"objectId":      current.Snapshot.PageObjects[0].ObjectID,
				}},
				"userActions": []any{map[string]any{
					"action":        current.Snapshot.UserActions[0].ActionType,
					"objectTypeRef": current.Snapshot.UserActions[0].ObjectTypeRef,
					"objectId":      current.Snapshot.UserActions[0].ObjectID,
				}},
				"consentMatrix": map[string]any{"canReadCurrentPage": true},
			}, true, nil
		}),
		nil,
	)
	runHandler := assistantingress.Routes(
		service,
		assistantingress.WithRunContextResolver(runContext),
	)
	create := assistantAPIRequest(t, runHandler, http.MethodPost, "/assistant/sessions", accountID, map[string]any{
		"clientRequestId": "page-context-session",
	})
	if create.Code != http.StatusCreated {
		t.Fatalf("create session status=%d body=%s", create.Code, create.Body.String())
	}
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatal(err)
	}
	start := assistantAPIRequest(t, runHandler, http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs", accountID, map[string]any{
			"clientRequestId": "page-context-run",
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "介绍当前内容"},
			},
		})
	if start.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", start.Code, start.Body.String())
	}
	var envelope struct {
		RunID string `json:"runId"`
	}
	if err := json.Unmarshal(start.Body.Bytes(), &envelope); err != nil {
		t.Fatal(err)
	}
	run, err := integrationRunRepository.Load(t.Context(), envelope.RunID)
	if err != nil {
		t.Fatal(err)
	}
	encodedContext, err := json.Marshal(run.ContextSnapshot)
	if err != nil {
		t.Fatal(err)
	}
	var persistedContext struct {
		PageObjects []struct {
			ObjectID string `json:"objectId"`
		} `json:"pageObjects"`
	}
	if err := json.Unmarshal(encodedContext, &persistedContext); err != nil {
		t.Fatal(err)
	}
	if len(persistedContext.PageObjects) != 1 ||
		persistedContext.PageObjects[0].ObjectID != "post-grounding-api" {
		t.Fatalf("run context=%+v", run.ContextSnapshot)
	}

	legacy := assistantAPIRequest(t, mux, http.MethodPost, "/assistant/page-context", accountID, map[string]any{
		"pageType": "article",
	})
	if legacy.Code != http.StatusBadRequest {
		t.Fatalf("legacy payload status=%d body=%s", legacy.Code, legacy.Body.String())
	}
}
