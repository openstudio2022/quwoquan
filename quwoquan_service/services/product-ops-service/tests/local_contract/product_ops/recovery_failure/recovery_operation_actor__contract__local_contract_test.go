// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
package local_contract

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"

	httpadapter "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/adapters/inbound/http"
	recoveryfailure "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
)

func TestReportRecoveryFailureNeedsNoSyntheticDeviceActor(t *testing.T) {
	t.Parallel()

	var document struct {
		APIRoutes []struct {
			Operation   string `yaml:"operation"`
			Actor       string `yaml:"actor"`
			Application struct {
				Kind string `yaml:"kind"`
			} `yaml:"application"`
			Authorization struct {
				Principal       string `yaml:"principal"`
				OwnershipPolicy string `yaml:"ownership_policy"`
			} `yaml:"authorization"`
			Security struct {
				AuthMode        string `yaml:"auth_mode"`
				Principal       string `yaml:"principal"`
				TokenTransport  string `yaml:"token_transport"`
				AnonymousPolicy string `yaml:"anonymous_policy"`
				Visibility      string `yaml:"visibility"`
			} `yaml:"security"`
		} `yaml:"api_routes"`
	}
	payload, err := os.ReadFile(recoveryFailureOperationsSource(t))
	if err != nil {
		t.Fatalf("read RecoveryFailure operations: %v", err)
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatalf("parse RecoveryFailure operations: %v", err)
	}
	if len(document.APIRoutes) != 1 {
		t.Fatalf("RecoveryFailure routes=%d, want 1", len(document.APIRoutes))
	}
	route := document.APIRoutes[0]
	if route.Operation != "ReportRecoveryFailure" ||
		route.Actor != "none" ||
		route.Application.Kind != "command" ||
		route.Authorization.Principal != "public" ||
		route.Authorization.OwnershipPolicy != "anonymous_recovery_write" ||
		route.Security.AuthMode != "optional" ||
		route.Security.Principal != "public" ||
		route.Security.TokenTransport != "none" ||
		route.Security.AnonymousPolicy != "allow" ||
		route.Security.Visibility != "public" {
		t.Fatalf("ReportRecoveryFailure anonymous/network admission contract drifted: %+v", route)
	}
}

// 匿名来源的权威准入已上收 api-edge 共享 admission
// （rate_limit.operation.ops_recovery_failure_report，subject=network IP，
// 跨副本 Redis 裁决）；inbound adapter 退回只做载荷校验。进程内窗口的
// 每副本配额语义已退役，同一来源连续上报在服务侧不再被本地窗口拒绝——
// 本用例锁定该职责边界，防止进程内 limiter 回归成伪准入。
func TestReportRecoveryFailureDelegatesSourceAdmissionToEdge(t *testing.T) {
	handler := httpadapter.NewHandler(
		recoveryfailure.NewService(&captureRecoveryReporter{}),
		writeTestError,
	)
	mux := http.NewServeMux()
	handler.Register(mux)

	for attempt := 1; attempt <= 25; attempt++ {
		response := postRecoveryFailureFrom(t, mux, "192.0.2.10:1234")
		if response.Code != http.StatusNoContent {
			t.Fatalf(
				"same-IP attempt %d must pass payload validation only, status=%d body=%s",
				attempt, response.Code, response.Body.String(),
			)
		}
	}
	independent := postRecoveryFailureFrom(t, mux, "198.51.100.20:1234")
	if independent.Code != http.StatusNoContent {
		t.Fatalf("different-IP attempt status=%d body=%s", independent.Code, independent.Body.String())
	}
}

func postRecoveryFailureFrom(
	t *testing.T,
	handler http.Handler,
	remoteAddress string,
) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(recoveryPayload())
	if err != nil {
		t.Fatalf("marshal recovery payload: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/recovery-failures",
		bytes.NewReader(body),
	)
	request.RemoteAddr = remoteAddress
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func recoveryFailureOperationsSource(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Clean(filepath.Join(
		filepath.Dir(file),
		"..", "..", "..", "..",
		"contracts", "product_ops", "recovery_failure", "operations.yaml",
	))
}
