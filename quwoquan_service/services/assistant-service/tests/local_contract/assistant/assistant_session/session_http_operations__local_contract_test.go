// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// readiness_case: create-assistant-session-local
// readiness_case: list-assistant-sessions-local
// readiness_case: get-assistant-session-local
package local_contract

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	sessionhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	sessionorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	sessionmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

func TestAssistantSessionHTTPOperationsUseCanonicalStore(t *testing.T) {
	service := sessionorchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		nil,
		sessionorchestration.WithSessionStore(persistence.NewMemorySessionStore()),
	)
	handler := sessionhttp.NewHandler(service).Routes()

	create := httptest.NewRequest(
		http.MethodPost,
		"/assistant/sessions",
		bytes.NewBufferString(`{"summary":"闭合会话","clientRequestId":"session-http-local"}`),
	)
	create.Header.Set("Content-Type", "application/json")
	create.Header.Set("X-Client-User-Id", "session-http-user")
	create.Header.Set("Idempotency-Key", "session-http-local")
	createdResponse := httptest.NewRecorder()
	handler.ServeHTTP(createdResponse, create)
	if createdResponse.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", createdResponse.Code, createdResponse.Body.String())
	}
	var created sessionmodel.AssistantSession
	if err := json.Unmarshal(createdResponse.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode created session: %v", err)
	}

	get := httptest.NewRequest(http.MethodGet, "/assistant/sessions/"+created.SessionID, nil)
	get.Header.Set("X-Client-User-Id", "session-http-user")
	getResponse := httptest.NewRecorder()
	handler.ServeHTTP(getResponse, get)
	if getResponse.Code != http.StatusOK {
		t.Fatalf("get status=%d body=%s", getResponse.Code, getResponse.Body.String())
	}

	list := httptest.NewRequest(http.MethodGet, "/assistant/sessions?limit=10", nil)
	list.Header.Set("X-Client-User-Id", "session-http-user")
	listResponse := httptest.NewRecorder()
	handler.ServeHTTP(listResponse, list)
	if listResponse.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listResponse.Code, listResponse.Body.String())
	}
	var page sessionmodel.AssistantSessionListView
	if err := json.Unmarshal(listResponse.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode session list: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].SessionID != created.SessionID {
		t.Fatalf("session list=%+v", page)
	}
}
