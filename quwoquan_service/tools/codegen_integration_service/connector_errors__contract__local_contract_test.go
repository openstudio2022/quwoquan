package main

import (
	"strings"
	"testing"
)

func TestIntegrationErrorGenerationOwnsCanonicalObjects(t *testing.T) {
	want := map[string]string{
		"capability_grant":        "integration/external_integration/capability_grant/errors.yaml",
		"connector_authorization": "integration/external_integration/connector_authorization/errors.yaml",
		"connector_definition":    "integration/external_integration/connector_definition/errors.yaml",
		"connector_connection":    "integration/external_integration/connector_connection/errors.yaml",
		"connector_invocation":    "integration/external_integration/connector_invocation/errors.yaml",
	}
	found := map[string]string{}
	for _, source := range integrationErrorSources {
		if _, exists := want[source.Object]; exists {
			found[source.Object] = source.SourcePath
		}
	}
	for object, sourcePath := range want {
		if found[object] != sourcePath {
			t.Fatalf(
				"integration error generator owner %s source=%q, want %q",
				object,
				found[object],
				sourcePath,
			)
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
