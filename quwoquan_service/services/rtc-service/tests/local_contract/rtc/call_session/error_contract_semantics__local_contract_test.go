// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
//
// rtc 服务错误契约语义双向锁：errors.yaml 中每个声明码的 HTTP status 与
// recovery_action 是对调用方（App error mapper、通话恢复动作）的行为承诺；
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

type rtcErrorSemantics struct {
	httpStatus     int
	recoveryAction string
}

func TestRTCErrorContractSemanticsMatchDeclaredCatalog(t *testing.T) {
	t.Parallel()

	expected := map[string]rtcErrorSemantics{
		"RTC.USER.invalid_argument":               {400, "surface"},
		"RTC.USER.call_not_found":                 {404, "surface"},
		"RTC.USER.unauthorized":                   {401, "surface"},
		"RTC.USER.account_security_denied":        {401, "surface"},
		"RTC.USER.already_in_call":                {409, "surface"},
		"RTC.USER.call_full":                      {409, "surface"},
		"RTC.USER.call_ended":                     {410, "surface"},
		"RTC.USER.not_participant":                {403, "surface"},
		"RTC.USER.not_mutual":                     {403, "surface"},
		"RTC.USER.blocked":                        {403, "surface"},
		"RTC.USER.cannot_answer":                  {409, "surface"},
		"RTC.USER.invalid_call_action":            {409, "surface"},
		"RTC.USER.screen_share_conflict":          {409, "surface"},
		"RTC.USER.idempotency_conflict":           {409, "surface"},
		"RTC.SYSTEM.media_transport_unavailable":  {503, "retry"},
		"RTC.SYSTEM.account_security_unavailable": {503, "retry"},
		"RTC.SYSTEM.internal_error":               {500, "surface"},
	}

	path := filepath.Join(
		rtcErrorsServiceRoot(t), "contracts", "rtc", "call_session", "errors.yaml",
	)
	actual := parseRTCErrorSemantics(t, path)
	if len(actual) != len(expected) {
		t.Fatalf(
			"call_session error inventory changed: got %d codes, want %d",
			len(actual), len(expected),
		)
	}
	for code, want := range expected {
		got, exists := actual[code]
		if !exists {
			t.Fatalf("declared code %s missing from errors.yaml", code)
		}
		if got != want {
			t.Fatalf(
				"%s semantics drifted: yaml={status:%d recovery:%s} test-lock={status:%d recovery:%s}",
				code, got.httpStatus, got.recoveryAction, want.httpStatus, want.recoveryAction,
			)
		}
	}
}

var rtcErrorCodeRe = regexp.MustCompile(`^-\s+(?:\{)?code:\s*([A-Z_]+\.[A-Z_]+\.[a-z_]+)`)

func parseRTCErrorSemantics(t *testing.T, path string) map[string]rtcErrorSemantics {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer file.Close()

	result := map[string]rtcErrorSemantics{}
	current := ""
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if match := rtcErrorCodeRe.FindStringSubmatch(line); match != nil {
			current = match[1]
			result[current] = rtcErrorSemantics{}
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

func rtcErrorsServiceRoot(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve rtc error contract test path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(filename), "../../../.."))
}
