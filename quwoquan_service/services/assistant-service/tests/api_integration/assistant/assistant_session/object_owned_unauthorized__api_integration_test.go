// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
package api_integration

import (
	"net/http"
	"strings"
	"testing"
)

func TestAssistantPublicObjectsEmitOnlyTheirOwnedUnauthorizedCode(t *testing.T) {
	handler := assistantHTTPHandlerWithTurnView(newIntegrationAssistantService())
	tests := []struct {
		name string
		path string
		code string
	}{
		{name: "session", path: "/assistant/sessions", code: "ASSISTANT.USER.session_unauthorized"},
		{name: "run", path: "/assistant/runs/missing", code: "ASSISTANT.USER.run_unauthorized"},
		{name: "preference", path: "/assistant/preferences", code: "ASSISTANT.USER.preference_unauthorized"},
		{name: "subscription", path: "/assistant/skill-subscriptions", code: "ASSISTANT.USER.subscription_unauthorized"},
		{name: "turn view", path: "/assistant/sessions/missing/turns", code: "ASSISTANT.USER.turn_view_unauthorized"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			response := assistantAPIRequest(
				t,
				handler,
				http.MethodGet,
				test.path,
				"",
				nil,
			)
			if response.Code != http.StatusUnauthorized ||
				!strings.Contains(response.Body.String(), test.code) {
				t.Fatalf(
					"anonymous %s status=%d body=%s, want 401 %s",
					test.name,
					response.Code,
					response.Body.String(),
					test.code,
				)
			}
		})
	}
}
