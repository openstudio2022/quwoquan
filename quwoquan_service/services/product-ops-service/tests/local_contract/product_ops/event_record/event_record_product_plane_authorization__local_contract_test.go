// Ensures ReportEventBatch / GetEventSummary stay registered on the product
// control plane under RequireGeneratedOperationAuthorization, and remain
// commercial.ready so package/codegen cannot silently drop /ops/events* auth.
package local_contract

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
)

func TestEventRecordTelemetryStaysOnProductControlPlane(t *testing.T) {
	t.Parallel()

	yamlPath := repoPath(t, "quwoquan_service", "contracts", "metadata", "_control_plane", "product", "control_plane.yaml")
	raw, err := os.ReadFile(yamlPath)
	if err != nil {
		t.Fatalf("read product control_plane.yaml: %v", err)
	}
	text := string(raw)
	for _, needle := range []string{
		"object_type: event_record_telemetry",
		"operation_id: ops.event_record.ReportEventBatch",
		"operation_id: ops.event_record.GetEventSummary",
	} {
		if !strings.Contains(text, needle) {
			t.Fatalf("product control_plane.yaml missing %q (source for next package codegen)", needle)
		}
	}
}

func TestProductOpsGeneratedAuthorizationIncludesEventRecordTelemetry(t *testing.T) {
	t.Parallel()

	cases := []struct {
		operationID string
		method      string
		path        string
		principal   string
		scope       string
	}{
		{
			operationID: "ops.event_record.ReportEventBatch",
			method:      http.MethodPost,
			path:        "/ops/events",
			principal:   "public",
		},
		{
			operationID: "ops.event_record.GetEventSummary",
			method:      http.MethodGet,
			path:        "/ops/events/summary",
			principal:   "account",
			scope:       "ops.telemetry.read",
		},
	}

	graphCommercial := loadContractGraphCommercialStatus(t)

	for _, tc := range cases {
		tc := tc
		t.Run(tc.operationID, func(t *testing.T) {
			t.Parallel()

			descriptor, ok := findProductPlaneDescriptor(tc.operationID)
			if !ok {
				t.Fatalf("%s absent from ProductOperationSecurityDescriptors; next package would 404 /ops/events* as route_not_found", tc.operationID)
			}
			if descriptor.Method != tc.method ||
				descriptor.PathTemplate != tc.path ||
				descriptor.Principal != tc.principal ||
				descriptor.CommercialStatus != "ready" {
				t.Fatalf("unexpected %s product-plane authorization: %+v", tc.operationID, descriptor)
			}
			if tc.scope != "" && !slices.Contains(descriptor.Scopes, tc.scope) {
				t.Fatalf("%s missing scope %q: %+v", tc.operationID, tc.scope, descriptor)
			}

			opsDescriptor, ok := findOpsSecurityDescriptor(tc.operationID)
			if !ok {
				t.Fatalf("%s missing from operationsecurity descriptors", tc.operationID)
			}
			if opsDescriptor.CommercialStatus != "ready" {
				t.Fatalf("%s commercial status = %q, want ready", tc.operationID, opsDescriptor.CommercialStatus)
			}
			if opsDescriptor.ContractGraphSHA256 != operationsecurity.ContractGraphSHA256 {
				t.Fatalf("%s ContractGraphSHA256 drift: descriptor=%s package=%s",
					tc.operationID, opsDescriptor.ContractGraphSHA256, operationsecurity.ContractGraphSHA256)
			}
			if status := graphCommercial[tc.operationID]; status != "ready" {
				t.Fatalf("%s contract_graph.json commercial.status = %q, want ready (codegen drift)", tc.operationID, status)
			}
		})
	}
}

func findProductPlaneDescriptor(operationID string) (auth.OperationSecurityDescriptor, bool) {
	for _, descriptor := range generatedcontrolplane.ProductOperationSecurityDescriptors {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor, true
		}
	}
	return auth.OperationSecurityDescriptor{}, false
}

func findOpsSecurityDescriptor(operationID string) (auth.OperationSecurityDescriptor, bool) {
	for _, descriptor := range operationsecurity.ForDomain("ops") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor, true
		}
	}
	return auth.OperationSecurityDescriptor{}, false
}

func loadContractGraphCommercialStatus(t *testing.T) map[string]string {
	t.Helper()
	raw, err := os.ReadFile(repoPath(t, "quwoquan_service", "generated", "contract_graph.json"))
	if err != nil {
		t.Fatalf("read contract_graph.json: %v", err)
	}
	var graph struct {
		Operations []struct {
			ID         string `json:"id"`
			Commercial struct {
				Status string `json:"status"`
			} `json:"commercial"`
		} `json:"operations"`
	}
	if err := json.Unmarshal(raw, &graph); err != nil {
		t.Fatalf("parse contract_graph.json: %v", err)
	}
	out := make(map[string]string, len(graph.Operations))
	for _, operation := range graph.Operations {
		out[operation.ID] = operation.Commercial.Status
	}
	return out
}

func repoPath(t *testing.T, parts ...string) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	// .../services/product-ops-service/tests/local_contract/product_ops/event_record/<this>
	repoRoot := filepath.Clean(filepath.Join(filepath.Dir(file), "../../../../../../.."))
	return filepath.Join(append([]string{repoRoot}, parts...)...)
}
