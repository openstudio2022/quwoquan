// spec_ref: specs/feature-tree/runtime/runtime-assistant/proactive-subscription-delivery/spec.md#gwt-001
package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/generated/serviceclients"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
)

type deliveryPolicyAuthorization struct{}

func (deliveryPolicyAuthorization) AuthorizationHeader(
	context.Context,
) (string, error) {
	return "Bearer assistant-policy-token", nil
}

func TestUserDeliveryPolicyClientUsesGeneratedPathAndStrongPolicy(
	t *testing.T,
) {
	server := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			expectedPath := serviceclients.
				UserResolveAssistantDeliveryPolicyPath(
					"account-policy",
				)
			if request.URL.Path != expectedPath ||
				request.Header.Get("Authorization") !=
					"Bearer assistant-policy-token" {
				t.Fatalf(
					"unexpected policy request path=%s authorization=%s",
					request.URL.Path,
					request.Header.Get("Authorization"),
				)
			}
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(
				`{"userId":"account-policy","assistantEnabled":true,` +
					`"quietHoursStart":"22:30","quietHoursEnd":"07:00",` +
					`"version":4,"updatedAt":"2026-07-24T08:00:00Z"}`,
			))
		},
	))
	defer server.Close()

	client, err := orchestration.NewUserDeliveryPolicyClient(
		server.URL,
		deliveryPolicyAuthorization{},
		server.Client(),
	)
	if err != nil {
		t.Fatal(err)
	}
	policy, err := client.ResolveAssistantDeliveryPolicy(
		t.Context(),
		"account-policy",
	)
	if err != nil {
		t.Fatal(err)
	}
	if policy.UserID != "account-policy" ||
		!policy.AssistantEnabled ||
		policy.QuietHoursStart == nil ||
		*policy.QuietHoursStart != 22*time.Hour+30*time.Minute ||
		policy.QuietHoursEnd == nil ||
		*policy.QuietHoursEnd != 7*time.Hour ||
		policy.Version != 4 {
		t.Fatalf("typed delivery policy drifted: %+v", policy)
	}
}

func TestUserDeliveryPolicyClientRejectsUntrustedPolicyResponses(
	t *testing.T,
) {
	cases := map[string]string{
		"incomplete": `{"userId":"account-policy","version":1}`,
		"wrong owner": `{"userId":"another-account",` +
			`"assistantEnabled":true,"version":1,` +
			`"updatedAt":"2026-07-24T08:00:00Z"}`,
		"unknown field": `{"userId":"account-policy",` +
			`"assistantEnabled":true,"version":1,` +
			`"updatedAt":"2026-07-24T08:00:00Z","legacy":true}`,
		"trailing json": `{"userId":"account-policy",` +
			`"assistantEnabled":true,"version":1,` +
			`"updatedAt":"2026-07-24T08:00:00Z"}{}`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(
				func(writer http.ResponseWriter, _ *http.Request) {
					writer.Header().Set("Content-Type", "application/json")
					_, _ = writer.Write([]byte(body))
				},
			))
			defer server.Close()
			client, err := orchestration.NewUserDeliveryPolicyClient(
				server.URL,
				deliveryPolicyAuthorization{},
				server.Client(),
			)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := client.ResolveAssistantDeliveryPolicy(
				t.Context(),
				"account-policy",
			); err == nil {
				t.Fatal("untrusted policy response must fail closed")
			}
		})
	}
}
