// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
//
// tag 服务错误契约语义双向锁：errors.yaml 中每个声明码的 HTTP status 与
// recovery_action 是对调用方（App error mapper、恢复动作）的行为承诺；
// 本表是契约的第二签名，YAML 侧任何清单增删或语义改动都必须同步这里，
// 防止无评审漂移。
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

type tagErrorSemantics struct {
	httpStatus     int
	recoveryAction string
}

func TestTagErrorContractSemanticsMatchDeclaredCatalog(t *testing.T) {
	t.Parallel()

	expected := map[string]map[string]tagErrorSemantics{
		"tag_node_view": {
			"TAG.USER.invalid_argument":      {400, "surface"},
			"TAG.USER.tag_not_found":         {404, "surface"},
			"TAG.SYSTEM.storage_read_failed": {500, "retry"},
		},
		"tag_feedback_fact": {
			"TAG.USER.feedback_invalid_action":       {400, "surface"},
			"TAG.USER.feedback_idempotency_conflict": {409, "retry"},
			"TAG.SYSTEM.feedback_storage_failed":     {500, "retry"},
		},
		"tag_taxonomy_release": {
			"TAG.USER.release_not_found":            {404, "surface"},
			"TAG.USER.release_invalid_argument":     {400, "surface"},
			"TAG.USER.release_invalid_transition":   {409, "retry"},
			"TAG.USER.release_snapshot_incomplete":  {409, "retry"},
			"TAG.USER.release_version_conflict":     {409, "retry"},
			"TAG.USER.release_idempotency_conflict": {409, "retry"},
			"TAG.SYSTEM.release_storage_failed":     {500, "retry"},
		},
	}

	serviceRoot := tagErrorsServiceRoot(t)
	for objectName, expectedCodes := range expected {
		path := filepath.Join(serviceRoot, "contracts", "tag", objectName, "errors.yaml")
		actual := parseTagErrorSemantics(t, path)
		if len(actual) != len(expectedCodes) {
			t.Fatalf(
				"%s error inventory changed: got %d codes %v, want %d",
				objectName, len(actual), sortedTagCodes(actual), len(expectedCodes),
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

var tagErrorCodeRe = regexp.MustCompile(`^-\s+(?:\{)?code:\s*([A-Z_]+\.[A-Z_]+\.[a-z_]+)`)

func parseTagErrorSemantics(t *testing.T, path string) map[string]tagErrorSemantics {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer file.Close()

	result := map[string]tagErrorSemantics{}
	current := ""
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if match := tagErrorCodeRe.FindStringSubmatch(line); match != nil {
			current = match[1]
			result[current] = tagErrorSemantics{}
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

func sortedTagCodes(entries map[string]tagErrorSemantics) []string {
	codes := make([]string, 0, len(entries))
	for code := range entries {
		codes = append(codes, code)
	}
	return codes
}

func tagErrorsServiceRoot(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve tag error contract test path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(filename), "../../../.."))
}
