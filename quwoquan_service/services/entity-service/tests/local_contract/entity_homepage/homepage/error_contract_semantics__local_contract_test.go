// spec_ref: specs/feature-tree/object-homepage-network/spec.md#dom-002
//
// entity 服务错误契约语义双向锁：errors.yaml 中每个声明码的 HTTP status 与
// recovery_action 是对调用方（App error mapper、主页认领恢复动作）的行为
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

type entityErrorSemantics struct {
	httpStatus     int
	recoveryAction string
}

func TestEntityErrorContractSemanticsMatchDeclaredCatalog(t *testing.T) {
	t.Parallel()

	expected := map[string]map[string]entityErrorSemantics{
		"homepage": {
			"ENTITY.USER.invalid_argument":      {400, "surface"},
			"ENTITY.USER.homepage_not_found":    {404, "surface"},
			"ENTITY.USER.homepage_offline":      {410, "surface"},
			"ENTITY.USER.invalid_homepage_type": {400, "surface"},
			"ENTITY.USER.permission_denied":     {403, "surface"},
			"ENTITY.USER.version_conflict":      {409, "retry"},
			"ENTITY.USER.idempotency_conflict":  {409, "surface"},
			"ENTITY.SYSTEM.internal_error":      {500, "surface"},
		},
		"homepage_claim_request": {
			"ENTITY.USER.claim_material_missing":     {400, "surface"},
			"ENTITY.USER.already_claimed":            {409, "surface"},
			"ENTITY.USER.claim_not_found":            {404, "surface"},
			"ENTITY.USER.duplicate_pending_claim":    {409, "surface"},
			"ENTITY.USER.invalid_claim_material_url": {400, "surface"},
		},
		"homepage_review": {
			"ENTITY.USER.review_not_found": {404, "surface"},
		},
		"homepage_status_report": {
			"ENTITY.USER.status_report_not_found":            {404, "surface"},
			"ENTITY.USER.invalid_status_report_evidence_url": {400, "surface"},
		},
	}

	serviceRoot := entityErrorsServiceRoot(t)
	for objectName, expectedCodes := range expected {
		path := filepath.Join(
			serviceRoot, "contracts", "entity_homepage", objectName, "errors.yaml",
		)
		actual := parseEntityErrorSemantics(t, path)
		if len(actual) != len(expectedCodes) {
			t.Fatalf(
				"%s error inventory changed: got %d codes, want %d",
				objectName, len(actual), len(expectedCodes),
			)
		}
		for code, want := range expectedCodes {
			got, exists := actual[code]
			if !exists {
				t.Fatalf("%s: declared code %s missing from errors.yaml", objectName, code)
			}
			if got != want {
				t.Fatalf(
					"%s: %s semantics drifted: yaml={status:%d recovery:%s} test-lock={status:%d recovery:%s}",
					objectName, code, got.httpStatus, got.recoveryAction, want.httpStatus, want.recoveryAction,
				)
			}
		}
	}
}

var entityErrorCodeRe = regexp.MustCompile(`^-\s+(?:\{)?code:\s*([A-Z_]+\.[A-Z_]+\.[a-z_]+)`)

func parseEntityErrorSemantics(t *testing.T, path string) map[string]entityErrorSemantics {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer file.Close()

	result := map[string]entityErrorSemantics{}
	current := ""
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if match := entityErrorCodeRe.FindStringSubmatch(line); match != nil {
			current = match[1]
			result[current] = entityErrorSemantics{}
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

func entityErrorsServiceRoot(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve entity error contract test path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(filename), "../../../.."))
}
