// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
//
// api-edge 错误契约语义双向锁：errors.yaml 中每个声明码的 HTTP status 与
// recovery_action 是对调用方（App error mapper、网关降级恢复动作）的行为
// 承诺；本表是契约的第二签名，YAML 侧任何清单增删或语义改动都必须同步
// 这里，防止无评审漂移。
package local_contract

import (
	"bufio"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"testing"
)

type gatewayErrorSemantics struct {
	httpStatus     int
	recoveryAction string
}

func TestGatewayErrorContractSemanticsMatchDeclaredCatalog(t *testing.T) {
	t.Parallel()

	expected := map[string]map[string]gatewayErrorSemantics{
		"edge_security/rate_limit_bucket": {
			"GATEWAY.USER.rate_limited":                       {429, "retry"},
			"GATEWAY.MIDDLEWARE.rate_limit_state_unavailable": {503, "retry"},
			"GATEWAY.MIDDLEWARE.upstream_timeout":             {504, "retry"},
			"GATEWAY.MIDDLEWARE.upstream_unavailable":         {503, "retry"},
		},
		"edge_security/rollout_assignment": {
			"GATEWAY.MIDDLEWARE.rollout_state_unavailable": {503, "retry"},
			"GATEWAY.USER.client_upgrade_required":         {426, "surface"},
		},
		"graphql_read/persisted_query_execution": {
			"GATEWAY.USER.graphql_request_invalid":         {400, "surface"},
			"GATEWAY.USER.persisted_query_unknown":         {400, "surface"},
			"GATEWAY.USER.graphql_query_forbidden":         {403, "surface"},
			"GATEWAY.MIDDLEWARE.graphql_owner_unavailable": {503, "retry"},
		},
	}

	serviceRoot := gatewayErrorsServiceRoot(t)
	for objectPath, expectedCodes := range expected {
		path := filepath.Join(serviceRoot, "contracts", objectPath, "errors.yaml")
		actual := parseGatewayErrorSemantics(t, path)
		if len(actual) != len(expectedCodes) {
			t.Fatalf(
				"%s error inventory changed: got %d codes, want %d",
				objectPath, len(actual), len(expectedCodes),
			)
		}
		for code, want := range expectedCodes {
			got, exists := actual[code]
			if !exists {
				t.Fatalf("%s: declared code %s missing from errors.yaml", objectPath, code)
			}
			if got != want {
				t.Fatalf(
					"%s: %s semantics drifted: yaml={status:%d recovery:%s} test-lock={status:%d recovery:%s}",
					objectPath, code, got.httpStatus, got.recoveryAction, want.httpStatus, want.recoveryAction,
				)
			}
		}
	}
}

var gatewayErrorCodeRe = regexp.MustCompile(`^-\s+(?:\{)?code:\s*([A-Z_]+\.[A-Z_]+\.[a-z_]+)`)

func parseGatewayErrorSemantics(t *testing.T, path string) map[string]gatewayErrorSemantics {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer file.Close()

	result := map[string]gatewayErrorSemantics{}
	current := ""
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if match := gatewayErrorCodeRe.FindStringSubmatch(line); match != nil {
			current = match[1]
			result[current] = gatewayErrorSemantics{}
			continue
		}
		if current == "" {
			continue
		}
		entry := result[current]
		if value, ok := strings.CutPrefix(line, "http_status:"); ok {
			status, err := strconv.Atoi(strings.TrimSpace(value))
			if err != nil {
				t.Fatalf("%s: bad http_status for %s: %v", path, current, err)
			}
			entry.httpStatus = status
		}
		if value, ok := strings.CutPrefix(line, "recovery_action:"); ok {
			entry.recoveryAction = strings.TrimSpace(value)
		}
		result[current] = entry
	}
	if err := scanner.Err(); err != nil {
		t.Fatalf("scan %s: %v", path, err)
	}
	return result
}

func gatewayErrorsServiceRoot(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve gateway error contract test path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(filename), "../../../.."))
}
