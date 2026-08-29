// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package bootstrap

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"
	operationsecurity "quwoquan_service/generated/operationsecurity"
)

func TestSearchBudgetHierarchyIsClosedAcrossEveryEnvironment(t *testing.T) {
	const ownerHTTPClientTimeoutMS = 2000
	contractRaw, err := os.ReadFile(filepath.Join(
		"..", "..", "contracts", "graphql_read", "persisted_query_execution", "operations.yaml",
	))
	if err != nil {
		t.Fatalf("read GraphQL operations contract: %v", err)
	}
	var contract struct {
		APIRoutes []struct {
			Path        string `yaml:"path"`
			Reliability struct {
				TimeoutMS int `yaml:"timeout_ms"`
			} `yaml:"reliability"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(contractRaw, &contract); err != nil {
		t.Fatalf("parse GraphQL operations contract: %v", err)
	}
	graphQLTimeoutMS := 0
	for _, route := range contract.APIRoutes {
		if route.Path == "/graphql" {
			graphQLTimeoutMS = route.Reliability.TimeoutMS
			break
		}
	}
	if graphQLTimeoutMS != 3000 || graphQLTimeoutMS <= ownerHTTPClientTimeoutMS {
		t.Fatalf(
			"GraphQL/client hierarchy drifted: graphql=%dms ownerClient=%dms",
			graphQLTimeoutMS,
			ownerHTTPClientTimeoutMS,
		)
	}

	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		raw, err := os.ReadFile(filepath.Join(
			"..", "..", "environments", environment, "config.yaml",
		))
		if err != nil {
			t.Fatalf("read %s config: %v", environment, err)
		}
		if !strings.Contains(
			string(raw),
			"sys.api-edge.graphql_read.owner_timeout_ms: 2000",
		) {
			t.Fatalf("%s GraphQL owner HTTP client timeout is not 2000ms", environment)
		}
	}

	searchTimeoutMS := 0
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID == "search.search_index_view.Search" {
			searchTimeoutMS = descriptor.TimeoutMilliseconds
			break
		}
	}
	if searchTimeoutMS != 1500 {
		t.Fatalf("Search operation timeout = %dms, want 1500ms", searchTimeoutMS)
	}
	if ownerProxyBudgetAllowance != 500*time.Millisecond {
		t.Fatalf("owner proxy allowance = %s, want 500ms", ownerProxyBudgetAllowance)
	}
	if searchTimeoutMS+int(ownerProxyBudgetAllowance/time.Millisecond) != ownerHTTPClientTimeoutMS {
		t.Fatalf(
			"direct Search proxy budget is not 2000ms: owner=%dms allowance=%s",
			searchTimeoutMS,
			ownerProxyBudgetAllowance,
		)
	}
}
