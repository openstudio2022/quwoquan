package main

import (
	"strings"
	"testing"
)

func TestIntegrationErrorGenerationOwnsConnectorObjects(t *testing.T) {
	want := map[string]bool{
		"connector_authorization": false,
		"connector_definition":    false,
		"connector_connection":    false,
		"connector_invocation":    false,
	}
	for _, source := range integrationErrorSources {
		if _, exists := want[source.Object]; exists {
			want[source.Object] = true
		}
	}
	for object, found := range want {
		if !found {
			t.Fatalf("integration error generator does not own %s", object)
		}
	}
}

func TestConnectorCapabilityResolutionUsesCanonicalInternalRoute(t *testing.T) {
	routes := serviceRoutesFile{APIRoutes: []apiRoute{{
		Method:    "POST",
		Path:      "/internal/integrations/connector-capability-grants:resolve",
		Operation: "ResolveConnectorCapabilityGrant",
		Authorization: struct {
			Scopes []string `yaml:"scopes"`
		}{Scopes: []string{"integration.connector_grant.read"}},
	}}}
	route := requiredRoute(
		"connector_connection/operations.yaml",
		routes.APIRoutes,
		"ResolveConnectorCapabilityGrant",
		"POST",
	)
	requireExactRoutePath(
		"connector_connection/operations.yaml",
		route,
		"/internal/integrations/connector-capability-grants:resolve",
	)
	if !strings.HasPrefix(route.Path, "/internal/") {
		t.Fatalf("capability resolution must remain internal, got %q", route.Path)
	}
	if scope := requiredSingleScope("connector_connection/operations.yaml", route); scope != "integration.connector_grant.read" {
		t.Fatalf("unexpected capability resolution scope %q", scope)
	}
}
