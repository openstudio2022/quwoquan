// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/toolaccess"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/connectorgateway"
)

type connectorGatewayAuthorization struct{}

func (connectorGatewayAuthorization) AuthorizationHeaderForAccount(
	_ context.Context,
	accountID string,
) (string, error) {
	if accountID != "account-1" {
		return "", fmt.Errorf("unexpected account %q", accountID)
	}
	return "Bearer service-token", nil
}

func TestConnectorCapabilityGatewayUsesServiceScopeAndRedactedDecision(t *testing.T) {
	var received map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Method != http.MethodPost ||
			request.URL.Path != "/internal/integrations/connector-capability-grants:resolve" ||
			request.Header.Get("Authorization") != "Bearer service-token" {
			t.Fatalf("unexpected request: %s %s auth=%q", request.Method, request.URL.Path, request.Header.Get("Authorization"))
		}
		if err := json.NewDecoder(request.Body).Decode(&received); err != nil {
			t.Fatal(err)
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"allowed":true,"capabilityKey":"calendar.event.create","surfaceKind":"personal","connectionId":"connection-1","connectorId":"system_calendar","freshnessAt":"2026-08-03T10:00:00Z","reason":"allowed"}`))
	}))
	defer server.Close()

	client, err := connectorgateway.New(server.URL, server.Client(), connectorGatewayAuthorization{})
	if err != nil {
		t.Fatal(err)
	}
	decision, err := client.ResolveCapability(context.Background(), toolaccess.ConnectorGrantRequest{
		AccountID: "account-1", CapabilityKey: "calendar.event.create",
		SurfaceKind: "personal", ConnectionRefs: []string{"connection-1"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !decision.Allowed || decision.ConnectionID != "connection-1" || decision.ConnectorID != "system_calendar" {
		t.Fatalf("decision=%+v", decision)
	}
	if _, exists := received["accountId"]; exists ||
		received["capabilityKey"] != "calendar.event.create" {
		t.Fatalf("request=%#v", received)
	}
	if _, exists := received["credentialRef"]; exists {
		t.Fatalf("credential material entered Assistant request: %#v", received)
	}
	scope, err := connectorgateway.RequiredScope()
	if err != nil || scope != "integration.connector_grant.read" {
		t.Fatalf("scope=%q err=%v", scope, err)
	}
}
